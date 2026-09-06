"""Microphone capture -> 16 kHz mono WAV for whisper.cpp."""
import queue
import sys
import tempfile
import wave

import numpy as np
import sounddevice as sd

import config


class LevelMeter:
    """Turns raw mic RMS into a lively 0..1 bar level.

    A fixed gain cannot serve both a whisper and a loud voice: it either pins
    at maximum or barely twitches. So this tracks the noise floor and a
    decaying peak, normalises between them, and applies compressor-style
    attack/release -- instant rise, smooth fall -- which is what makes a meter
    read as responsive rather than laggy.
    """

    def __init__(self):
        self.floor = config.AUDIO_NOISE_FLOOR_INIT
        self.peak = config.AUDIO_PEAK_INIT
        self.value = 0.0

    def reset(self):
        self.floor = config.AUDIO_NOISE_FLOOR_INIT
        self.peak = config.AUDIO_PEAK_INIT
        self.value = 0.0

    def push(self, rms: float) -> float:
        # Noise floor: falls quickly toward quiet, creeps up slowly, so a
        # sudden silence re-baselines fast but speech never raises the floor.
        if rms < self.floor:
            self.floor += (rms - self.floor) * 0.25
        else:
            self.floor += (rms - self.floor) * 0.0015

        # Peak: jumps to any new maximum, then decays so the meter re-scales
        # after you stop shouting.
        self.peak = max(rms, self.peak * config.AUDIO_PEAK_DECAY,
                        config.AUDIO_PEAK_MIN)

        # Absolute gate: below this there is no real signal, and normalising
        # would just amplify room noise into a full-height waveform.
        if rms < config.AUDIO_ABS_GATE:
            target = 0.0
        else:
            span = max(self.peak - self.floor, 1e-5)
            target = (rms - self.floor) / span
            target = max(0.0, min(1.0, target))
            # Expand the low end so ordinary speech uses most of the range.
            target = target ** config.AUDIO_LEVEL_CURVE

        # Fast attack, slow release.
        if target > self.value:
            self.value += (target - self.value) * config.AUDIO_ATTACK
        else:
            self.value += (target - self.value) * config.AUDIO_RELEASE
        return self.value


class Recorder:
    """Push-to-talk recorder. start() begins capture, stop() returns a WAV path."""

    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        self._stream = None
        self.recording = False
        # Latest mic level, 0..1, for the overlay waveform. Written on the
        # audio thread, read by the UI pump. Deliberately just a float: no
        # I/O and no locking happens on the audio thread.
        self.last_level = 0.0
        self._meter = LevelMeter()

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"[audio] stream status: {status}", file=sys.stderr)
        self._q.put(indata.copy())
        try:
            rms = float(np.sqrt(np.mean(np.square(indata))))
            self.last_level = self._meter.push(rms)
        except (ValueError, FloatingPointError):
            pass

    def start(self):
        if self.recording:
            return
        self.last_level = 0.0
        while not self._q.empty():
            self._q.get_nowait()
        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype=config.DTYPE,
            callback=self._callback,
            blocksize=0,
        )
        self._stream.start()
        self.recording = True

    def stop(self):
        """Stop capture. Returns (wav_path, duration_sec) or (None, duration)."""
        if not self.recording:
            return None, 0.0
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self.recording = False

        chunks = []
        while not self._q.empty():
            chunks.append(self._q.get_nowait())
        if not chunks:
            return None, 0.0

        audio = np.concatenate(chunks, axis=0).flatten()
        duration = len(audio) / config.SAMPLE_RATE
        if duration < config.MIN_RECORDING_SEC:
            return None, duration

        return self._write_wav(audio), duration

    @staticmethod
    def _write_wav(audio: np.ndarray) -> str:
        """float32 [-1,1] -> 16-bit PCM WAV, the format whisper-cli wants."""
        pcm16 = np.clip(audio, -1.0, 1.0)
        pcm16 = (pcm16 * 32767).astype(np.int16)
        fd = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        with wave.open(fd, "wb") as w:
            w.setnchannels(config.CHANNELS)
            w.setsampwidth(2)
            w.setframerate(config.SAMPLE_RATE)
            w.writeframes(pcm16.tobytes())
        return fd.name

    @staticmethod
    def peak_level(wav_path: str) -> float:
        """Peak amplitude 0..1, for sanity-checking the mic actually heard you."""
        with wave.open(wav_path, "rb") as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return float(np.abs(data).max() / 32767) if len(data) else 0.0
