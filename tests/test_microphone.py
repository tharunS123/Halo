"""Microphones coming and going, against a fake audio layer.

The promises: a chosen microphone that is missing falls back to the system
default with a warning instead of failing; one plugged in after Halo started
is found without a restart; and one that disappears mid-recording costs
nothing you had already said -- the engine notices, sends what it heard, and
the next recording just works.
"""
import contextlib
import io
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))
os.environ["HALO_CONFIG_DIR"] = str(FIXTURES)
os.environ["HALO_DATA_DIR"] = tempfile.mkdtemp(prefix="halo-mic-")
os.environ["HALO_OVERLAY"] = "0"

import numpy as np  # noqa: E402

import audio  # noqa: E402
import config  # noqa: E402

ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


class FakeStream:
    """Delivers a 0.1s buffer of tone every call to pump() -- until unplugged."""

    def __init__(self, sd, device, callback, **kw):
        if device is not None and sd.devices[device]["name"] in sd.broken:
            raise sd.PortAudioError("Error opening InputStream")
        self.sd, self.device, self.callback = sd, device, callback
        self.alive = True
        sd.opened.append(device)
        sd.stream = self

    def start(self):
        pass

    def pump(self, n=1):
        t = np.arange(1600) / 16000
        for _ in range(n):
            if self.alive:
                self.callback((0.3 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
                              .reshape(-1, 1), 1600, None, None)

    def stop(self):
        if not self.alive:
            raise self.sd.PortAudioError("Internal PortAudio error [-9986]")

    def close(self):
        if not self.alive:
            raise self.sd.PortAudioError("device gone")


class FakeSD:
    class PortAudioError(Exception):
        pass

    def __init__(self):
        self.devices = [{"name": "MacBook Pro Microphone", "max_input_channels": 1},
                        {"name": "MacBook Pro Speakers", "max_input_channels": 0}]
        self.visible = list(self.devices)   # what PortAudio's stale list shows
        self.broken = set()
        self.opened = []
        self.stream = None
        self.refreshes = 0
        self.default = type("D", (), {"device": [0, 1]})()

    def query_devices(self):
        return self.visible

    def _terminate(self):
        pass

    def _initialize(self):
        self.refreshes += 1
        self.visible = list(self.devices)

    def InputStream(self, device=None, callback=None, **kw):  # noqa: N802
        return FakeStream(self, device, callback, **kw)

    def plug(self, name):
        self.devices.append({"name": name, "max_input_channels": 1})


sd = FakeSD()
audio.sd = sd
audio._devices_at = time.time()          # the list is "fresh": no refresh yet

print("=== choosing a microphone ===")
config.MIC_DEVICE = ""
check("System Default needs no device index", audio.resolve("") == (None, ""))
r = audio.Recorder()
r.start()
check("...and opens the default", sd.opened[-1] is None and r.device_warning == "")
r.stop()

sd.plug("AirPods Pro")                   # plugged in after Halo started
config.MIC_DEVICE = "AirPods Pro"
r.start()
check("a mic plugged in after start is found, no restart",
      sd.opened[-1] == 2 and r.device_warning == "", (sd.opened, r.device_warning))
check("...by refreshing the device list once", sd.refreshes == 1, sd.refreshes)
r.stop()

config.MIC_DEVICE = "Blue Yeti"          # chosen, but not connected
r.start()
check("a missing mic falls back to the system default", sd.opened[-1] is None)
check("...and says so", r.device_warning == "Blue Yeti not found", r.device_warning)
r.stop()

sd.plug("Scarlett 2i2")
sd.broken.add("Scarlett 2i2")            # listed, but will not open
config.MIC_DEVICE = "Scarlett 2i2"
r.start()
check("a mic that will not open falls back too", sd.opened[-1] is None
      and r.device_warning == "Scarlett 2i2 failed to open", r.device_warning)
r.stop()

names = [d["name"] for d in audio.input_devices()]
check("outputs are not offered as microphones", "MacBook Pro Speakers" not in names, names)

print("\n=== unplugged mid-recording ===")
config.MIC_DEVICE = "AirPods Pro"
r.start()
sd.stream.pump(8)                        # 0.8s of speech...
check("not stalled while audio arrives", not r.stalled())
sd.stream.alive = False                  # ...then the AirPods go in the case
r._last_audio -= audio.STALL_SEC + 0.1
check("the stall is noticed", r.stalled())
wav, dur = r.stop()
check("stop() does not raise when the device is gone", wav is not None)
check("...and what was said before it went is kept", wav and abs(dur - 0.8) < 0.05, dur)
check("the problem is counted, not printed from the audio thread", r.stream_problems >= 1)
os.unlink(wav)

print("\n=== ...and the engine sends what it heard ===")
import halo  # noqa: E402
import overlay  # noqa: E402


class UI(overlay.NullOverlay):
    def __init__(self):
        self.events = []

    def flash(self, m): self.events.append(f"flash:{m}")
    def error(self, m): self.events.append(f"error:{m}")
    def level(self, v): pass


h = halo.Halo(ui=UI())
finished = threading.Event()
h.finish = finished.set
config.OVERLAY_LEVEL_INTERVAL = 0.01
with contextlib.redirect_stdout(io.StringIO()):
    h.held = True
    h.recorder.start()
    sd.stream.pump(3)
    h._start_level_pump()
    sd.stream.alive = False
    h.recorder._last_audio -= audio.STALL_SEC + 0.1
    finished.wait(2)
check("the dictation is sent without waiting for the key", finished.is_set())
check("the orb says why", "flash:Microphone disconnected" in h.ui.events, h.ui.events)
check("releasing the key afterwards does not send it twice", h.held is False)

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
