"""Failed dictation recovery, and surviving an engine crash.

The promise: whatever breaks -- whisper, the cleanup rules, the insertion, or
the engine process itself -- what you said is not lost. The clip and the
words are kept for Retry Transcription / Retry Cleanup / Retry Insertion /
Copy / Discard, Privacy Mode keeps no audio, and a crash mid-dictation is
recovered by the next engine.

Offline and hermetic: whisper is a stand-in, typing is captured, and the
"crash" is a real child process killed with os._exit mid-transcription.
"""
import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

DATA = tempfile.mkdtemp(prefix="halo-recovery-")
os.environ["HALO_CONFIG_DIR"] = str(FIXTURES)
os.environ["HALO_DATA_DIR"] = DATA
os.environ["HALO_OVERLAY"] = "0"

import numpy as np  # noqa: E402

import clipboard  # noqa: E402
import config  # noqa: E402
import failed as failed_mod  # noqa: E402
import halo  # noqa: E402
import insertion  # noqa: E402
import netguard  # noqa: E402
import overlay  # noqa: E402
import paths  # noqa: E402
import pipeline  # noqa: E402
import transcribe  # noqa: E402
from audio import Recorder  # noqa: E402

netguard.install()
ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


INSERTED, CLIPBOARD = [], []
INSERT_OK = [True]


def fake_insert(text, target=None, ax=None, pb=None):
    if not INSERT_OK[0]:
        return insertion.Result(False, reason="you switched apps")
    INSERTED.append(text)
    return insertion.Result(True, "ax", range=(0, len(text)))


insertion.insert = fake_insert
clipboard.put_text_for_user = lambda text, pb=None: CLIPBOARD.append(text)
halo.context_mod.capture = lambda *a, **k: None       # retry insertion: "what has focus"


class UI(overlay.NullOverlay):
    def __init__(self):
        self.events = []

    def error(self, m):   self.events.append(f"error:{m}")
    def flash(self, m):   self.events.append(f"flash:{m}")
    def failed(self, on): self.events.append(f"failed:{on}")


def clip() -> str:
    t = np.arange(int(config.SAMPLE_RATE * 1.0)) / config.SAMPLE_RATE
    return Recorder._write_wav((0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32))


def whisper(text=None, error=None):
    def fake(path, language=None, **kw):
        if error is not None:
            raise error
        return transcribe.TranscriptResult(text, "en", "stand-in")
    transcribe.transcribe = fake


f = halo.Halo(ui=UI())
f.privacy.set(False)
LOG = io.StringIO()


def dictate():
    f.recorder.stop = (lambda w: lambda: (w, 1.0))(clip())
    f._pending = None
    f.ui.events.clear()
    with contextlib.redirect_stdout(LOG):
        f.finish()


def op(name, **req):
    with contextlib.redirect_stdout(LOG):
        return f.control_handlers()[name](req)


FAILED_WAV = paths.RECOVERY_DIR / "failed.wav"

print("=== whisper fails: the recording is kept, nothing is typed ===")
whisper(error=transcribe.TranscriptionError("whisper-cli exited 134"))
dictate()
item = f.failed.current()
check("kept as a failed transcription", item is not None and item.stage == "transcription", item)
check("the orb says so, in words", "error:Transcription failed" in f.ui.events, f.ui.events)
check("the app is told there is something to retry", "failed:True" in f.ui.events)
check("the audio is kept", FAILED_WAV.exists())
check("...privately (0600, in a 0700 folder)",
      stat.S_IMODE(FAILED_WAV.stat().st_mode) == 0o600
      and stat.S_IMODE(paths.RECOVERY_DIR.stat().st_mode) == 0o700)
check("nothing was typed", INSERTED == [])
check("health names the failure, not the words",
      op("health")["failed"] == "transcription: Transcription failed")

print("\n=== Retry Transcription, Retry Cleanup, Copy, Retry Insertion ===")
check("Retry Cleanup needs a transcript first", not op("failed.retry_cleanup")["ok"])
whisper("send the the report to the team on friday")
r = op("failed.retry_transcription")
check("Retry Transcription works once whisper does", r["ok"] and r["text"] ==
      "Send the report to the team on Friday.", r)
check("...and does not type it on its own", INSERTED == [])
r = op("failed.retry_cleanup", mode="verbatim")
check("Retry Cleanup runs the pipeline again", r["ok"] and r["text"].startswith("send the the"), r)
check("Copy puts it on the clipboard", op("failed.copy")["ok"] and CLIPBOARD[-1] == r["text"])
check("the words are in the Settings reply, which shows them to you",
      op("failed.get")["failed"]["raw"] == "send the the report to the team on friday")
r = op("failed.retry_insertion")
check("Retry Insertion types it", r["ok"] and INSERTED == [CLIPBOARD[-1]], r)
check("...and lets it go, audio and all", f.failed.current() is None and not FAILED_WAV.exists())
check("the app is told it is gone", "failed:False" in f.ui.events)
check("a stale id is refused", not op("failed.retry_insertion", id="nope")["ok"])

print("\n=== the target moved: kept with its text ===")
INSERT_OK[0] = False
whisper("quarterly numbers look strong")
dictate()
item = f.failed.current()
check("kept as a failed insertion, with the words and the audio",
      item and item.stage == "insertion" and item.text.startswith("Quarterly")
      and item.audio and FAILED_WAV.exists(), item)
check("repr never shows the words", "quarterly" not in repr(item).lower())
INSERT_OK[0] = True
check("Discard throws it away", op("failed.discard")["ok"] and f.failed.current() is None
      and not FAILED_WAV.exists())

print("\n=== the cleanup rules crash: typed as heard, kept for Retry Cleanup ===")
saved = pipeline.process
pipeline.process = lambda *a, **k: 1 / 0
INSERTED.clear()
whisper("um the budget is fine")
dictate()
pipeline.process = saved
item = f.failed.current()
check("what whisper heard is still typed", INSERTED == ["um the budget is fine"], INSERTED)
check("...and kept as a failed cleanup", item and item.stage == "cleanup")
r = op("failed.retry_cleanup")
check("Retry Cleanup gives the cleaned text", r["ok"] and r["text"] == "The budget is fine.", r)
op("failed.discard")

print("\n=== Privacy Mode: the words for a retry, never the audio ===")
f.privacy.set(True)
whisper(error=transcribe.TranscriptionError("boom"))
dictate()
item = f.failed.current()
check("a failure is still offered", item is not None)
check("...with no audio on disk", item and item.audio is None and not FAILED_WAV.exists())
f.privacy.set(False)
op("failed.discard")

print("\n=== Escape is not a failure ===")
whisper(error=transcribe.Cancelled())
dictate()
check("a cancelled dictation is not kept", f.failed.current() is None)

print("\n=== 30 minutes, then it goes ===")
whisper(error=transcribe.TranscriptionError("boom"))
dictate()
f.failed.current().at -= failed_mod.MAX_AGE + 1
f.ui.events.clear()
check("expired", f.failed.current() is None and not FAILED_WAV.exists())
check("...and the menu bar is told", f.ui.events == ["failed:False"], f.ui.events)

print("\n=== a restart keeps what a failed dictation left ===")
whisper(error=transcribe.TranscriptionError("boom"))
dictate()
again = failed_mod.Keeper().restore()
check("a new engine finds the audio", again is not None and again.audio and Path(again.audio).exists())
check("...and where it failed", again and again.stage == "transcription"
      and again.reason == "Transcription failed")
check("...but never any words: they were only in memory",
      again and again.raw == "" and again.text == "")
meta = json.loads((paths.RECOVERY_DIR / "failed.json").read_text())
check("the metadata file holds no text", set(meta) == {"stage", "reason", "at", "language",
                                                       "app", "duration"}, sorted(meta))
op("failed.discard")

print("\n=== the engine crashes mid-transcription (a real process, killed) ===")
child = f"""
import os, sys
sys.path.insert(0, {str(ROOT)!r})
import numpy as np, transcribe, halo, config, overlay
from audio import Recorder
t = np.arange(16000) / 16000
wav = Recorder._write_wav((0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32))
transcribe.transcribe = lambda *a, **k: os._exit(9)     # dies inside whisper
h = halo.Halo(ui=overlay.NullOverlay())
h.recorder.stop = lambda: (wav, 1.0)
h.finish()
"""
p = subprocess.run([sys.executable, "-c", child], env=dict(os.environ), capture_output=True,
                   text=True, timeout=60)
check("the engine really died, mid-dictation", p.returncode == 9, p.stderr[-300:])
check("its clip survived the crash", (paths.RECOVERY_DIR / "pending.wav").exists())

CLIPBOARD.clear()
whisper("remember to call the dentist")
f2 = halo.Halo(ui=UI())
with contextlib.redirect_stdout(LOG):
    f2.recover()
check("the next engine transcribes it and puts it on the clipboard",
      CLIPBOARD == ["Remember to call the dentist."], CLIPBOARD)
check("...says so on the orb", any("Recovered" in e for e in f2.ui.events), f2.ui.events)
check("...and keeps it for Retry Insertion", f2.failed.current() is not None
      and f2.failed.current().stage == "recovered")
check("the crash copy itself is cleaned up", not (paths.RECOVERY_DIR / "pending.wav").exists())

print("\n=== ...and when whisper fails that time too ===")
p = subprocess.run([sys.executable, "-c", child], env=dict(os.environ), capture_output=True,
                   text=True, timeout=60)
whisper(error=transcribe.TranscriptionError("still broken"))
f3 = halo.Halo(ui=UI())
with contextlib.redirect_stdout(LOG):
    f3.recover()
item = f3.failed.current()
check("the audio is kept for a later retry", item and item.stage == "transcription"
      and item.audio and Path(item.audio).exists(), item)

print("\n=== nothing said reached the log, nothing left the Mac ===")
text = LOG.getvalue()
check("no dictated words in the log", not any(w in text for w in
                                              ("quarterly", "dentist", "budget", "priya")))
check("zero connection attempts off this Mac", netguard.attempts == [], netguard.attempts)

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
