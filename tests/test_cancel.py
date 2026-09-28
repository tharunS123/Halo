"""Escape cancels anything: recording, transcription, cleanup, or text that
is about to be typed. Nothing is typed afterwards, nothing is kept as a
"failure" (you meant it), the clip is deleted, and whisper is killed rather
than waited out.
"""
import contextlib
import io
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="halo-cancel-"))
os.environ["HALO_CONFIG_DIR"] = str(FIXTURES)
os.environ["HALO_DATA_DIR"] = str(TMP / "data")
os.environ["HALO_OVERLAY"] = "0"

import numpy as np  # noqa: E402

import clipboard  # noqa: E402
import config  # noqa: E402
import halo  # noqa: E402
import insertion  # noqa: E402
import overlay  # noqa: E402
import pipeline  # noqa: E402
import transcribe  # noqa: E402
from audio import Recorder  # noqa: E402

ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


TYPED, CLIPBOARD = [], []
insertion.insert = lambda text, target=None, ax=None, pb=None: (
    TYPED.append(text), insertion.Result(True, "ax"))[1]
clipboard.put_text_for_user = lambda text, pb=None: CLIPBOARD.append(text)


class UI(overlay.NullOverlay):
    def __init__(self):
        self.events = []
        self.on_inserting = None

    def flash(self, m): self.events.append(f"flash:{m}")
    def error(self, m): self.events.append(f"error:{m}")

    def inserting(self):
        if self.on_inserting:
            self.on_inserting()


f = halo.Halo(ui=UI())


def clip() -> str:
    t = np.arange(16000) / 16000
    return Recorder._write_wav((0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32))


def dictate(transcriber):
    wav = clip()
    f.recorder.stop = lambda: (wav, 1.0)
    f._cancel.clear()
    f.ui.events.clear()
    TYPED.clear()
    transcribe_saved = transcribe.transcribe
    transcribe.transcribe = transcriber
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            f.finish()
    finally:
        transcribe.transcribe = transcribe_saved
    return wav


def heard(text):
    return lambda path, language=None, **kw: transcribe.TranscriptResult(text, "en", "x")


def cancelled(wav, what):
    check(f"{what}: nothing is typed", TYPED == [], TYPED)
    check(f"{what}: the orb says Cancelled", "flash:Cancelled" in f.ui.events, f.ui.events)
    check(f"{what}: not kept as a failure", f.failed.current() is None)
    check(f"{what}: the clip is deleted", not os.path.exists(wav))
    check(f"{what}: Halo is idle again", f.stage == "idle" and not f.busy.locked())


print("=== during recording ===")
f.recorder.start = lambda: None
f.recorder.recording = True
f.stage = "recording"
wav = clip()
f.recorder.stop = lambda: (wav, 1.0)
with contextlib.redirect_stdout(io.StringIO()):
    f.escape()
check("recording: the microphone stops, the clip is deleted",
      not os.path.exists(wav) and f.stage == "idle")
check("recording: nothing is typed", TYPED == [])
f.recorder.recording = False

print("\n=== during transcription ===")


def escape_then(text):
    def run(path, language=None, cancel=None, **kw):
        f.escape()                      # the user presses Escape while whisper works
        return transcribe.TranscriptResult(text, "en", "x")
    return run


cancelled(dictate(escape_then("this should never be typed")), "transcription")

print("\n=== during cleanup ===")
saved = pipeline.process


def slow_cleanup(*a, **k):
    f.escape()
    return saved(*a, **k)


pipeline.process = slow_cleanup
cancelled(dictate(heard("this should never be typed either")), "cleanup")
pipeline.process = saved

print("\n=== with the text about to be typed ===")
f.ui.on_inserting = f.escape
cancelled(dictate(heard("nor this")), "pending insertion")
f.ui.on_inserting = None

print("\n=== and the next dictation is normal ===")
dictate(heard("this one is fine"))
check("typed", TYPED == ["This one is fine."], TYPED)

print("\n=== whisper itself is killed, not waited for ===")
slow = TMP / "whisper-cli"
slow.write_text("#!/bin/sh\nsleep 20\n")
slow.chmod(slow.stat().st_mode | stat.S_IXUSR)
model = TMP / "ggml-small.en.bin"
model.write_bytes(b"x")
config.WHISPER_BIN, config.WHISPER_MODEL_EN = slow, model
import threading  # noqa: E402

cancel = threading.Event()
threading.Timer(0.3, cancel.set).start()
t0 = time.monotonic()
try:
    transcribe.transcribe(clip(), "en", cancel=cancel)
    check("Escape stops whisper", False)
except transcribe.Cancelled:
    took = time.monotonic() - t0
    check("Escape stops a 20-second whisper run within a second", took < 1.0, f"{took:.2f}s")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
