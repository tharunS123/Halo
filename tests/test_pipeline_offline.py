"""FEATURES 1-5 TEST: the whole post-transcription pipeline, injection mocked.

Runs fully offline against the fixtures. Both env vars below must be set
before config is imported for the first time, or this test would read the
developer's real vocabulary and write their real Privacy Mode state.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

os.environ["HALO_CONFIG_DIR"] = str(FIXTURES)
os.environ["HALO_DATA_DIR"] = tempfile.mkdtemp(prefix="halo-test-")

import cleanup as cleanup_mod
import clipboard as clipboard_mod
import insertion as insertion_mod
import overlay as overlay_mod

# No network in a test: the cleanup pass is exercised by test_dedup.py, and
# here it only has to return something recognisable.
cleanup_mod.clean = lambda text, vocabulary=None, language="en": type(
    "R", (), {"text": text, "source": "llm", "detail": "stubbed"})()
# The AI command too: before 0.4 this test cleared `last_injected` to stop it,
# and when the engine moved to insertion records that stopped working -- the
# test made a real OpenRouter call with the developer's key. Stub it outright.
AI_CALLS = []
cleanup_mod.ai_command = lambda instruction, ctx, language="en": (
    AI_CALLS.append(instruction), cleanup_mod.CleanupResult("rewritten", "llm", "stub"))[1]

# --- capture instead of typing into whatever has focus ---
INJECTED, UNDOS, CLIPBOARD = [], [], []
INSERT_RESULT = [insertion_mod.Result(True, "paste")]


def fake_insert(text, target=None, ax=None, pb=None):
    INJECTED.append(text)
    return INSERT_RESULT[0]


insertion_mod.insert = fake_insert
insertion_mod.undo = lambda rec, ax=None, max_age=300: (
    UNDOS.append(True), insertion_mod.Result(True, "undo"))[1]
clipboard_mod.put_text_for_user = lambda text, pb=None: CLIPBOARD.append(text)

import halo

class FakeUI(overlay_mod.NullOverlay):
    def __init__(self): self.events = []
    def done(self):            self.events.append("done")
    def error(self, m):        self.events.append(f"error:{m}")
    def privacy(self, on):     self.events.append(f"privacy:{on}")
    def flash(self, m):        self.events.append(f"flash:{m}")

f = halo.Halo(ui=FakeUI())
f.privacy.set(False)
ok = True

def run(text, label):
    INJECTED.clear(); UNDOS.clear(); f.ui.events.clear()
    f.dispatch(text)
    return INJECTED[:], UNDOS[:], f.ui.events[:]

print("=== 1. dictionary applied before everything ===")
inj, _, _ = run("i used open router with whisper dot cpp", "dict")
good = inj and "OpenRouter" in inj[0] and "whisper.cpp" in inj[0]
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] {inj[0][:70]!r}" if inj else "  [FAIL] nothing injected")

print("\n=== 2. snippet: whole-utterance trigger, skips cleanup ===")
inj, _, _ = run("standup template", "snip")
good = bool(inj) and "**Yesterday**" in inj[0] and "\n" in inj[0]
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] injected {len(inj[0]) if inj else 0} chars, multi-line={bool(inj) and chr(10) in inj[0]}")

print("\n=== 4a. undo command -> Cmd+Z, injects nothing ===")
inj, und, ev = run("scratch that", "undo")
good = und == [True] and inj == []
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] undos={len(und)} injected={len(inj)} ui={ev}")

print("\n=== 4b. newline / paragraph ===")
inj, _, _ = run("new line", "nl");    good = inj == ["\n"];   ok &= good
print(f"  [{'PASS' if good else 'FAIL'}] new line -> {inj!r}")
inj, _, _ = run("new paragraph", "p"); good = inj == ["\n\n"]; ok &= good
print(f"  [{'PASS' if good else 'FAIL'}] new paragraph -> {inj!r}")

print("\n=== 5. privacy mode: voice toggle, then no network ===")
inj, _, ev = run("privacy on", "pon")
good = f.privacy.enabled and any("privacy:True" in e for e in ev)
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] enabled={f.privacy.enabled} ui={ev}")

# Privacy Mode skips the NETWORK, not the local polish. Before 0.3.2 it also
# skipped punctuation and capitalization, because the only thing providing
# them was the OpenRouter call -- so turning privacy on quietly downgraded you
# to a whisper dump. punctuate.py runs entirely on this machine, so it stays.
inj, _, _ = run("um so this should stay local comma and uncleaned", "raw")
good = inj == ["So this should stay local, and uncleaned."]
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] locally polished, never sent: "
                  f"{inj[0]!r}" if inj else "  [FAIL]")

print("\n=== 5b. AI command refused while private (would leave the machine) ===")
f.records = [insertion_mod.Record("some earlier text", "paste", 1, "x", None, None, None)]
inj, _, ev = run("hey halo make that more formal", "aiblock")
good = inj == [] and any("error" in e for e in ev)
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] injected={inj} ui={ev}")

inj, _, ev = run("privacy off", "poff")
good = not f.privacy.enabled
ok &= good; print(f"\n  [{'PASS' if good else 'FAIL'}] privacy back off: {f.privacy.enabled}")

print("\n=== 5c. privacy state written by another process is picked up ===")
# The menu bar item lives in the Swift app and cannot reach into the engine,
# so it writes state.json and the engine re-reads it on mtime. Without this,
# the lock badge and the actual behaviour could disagree -- a privacy
# indicator that lies is worse than no indicator.
import json as _json, time as _time
state = f.privacy.path
_time.sleep(0.01)                      # a distinct mtime, not the same second
state.write_text(_json.dumps({"privacy_mode": True}))
good = f.privacy.enabled is True
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] external ON seen: {f.privacy.enabled}")
_time.sleep(0.01)
state.write_text(_json.dumps({"privacy_mode": False}))
good = f.privacy.enabled is False
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] external OFF seen: {f.privacy.enabled}")

print("\n=== 4c. AI command with no prior dictation is refused ===")
f.records.clear()
inj, _, ev = run("hey halo summarize that", "noctx")
good = inj == [] and any("error" in e for e in ev)
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] ui={ev}")

print("\n=== ordinary dictation still reaches cleanup ===")
inj, _, _ = run("um so i think we should ship this on friday", "normal")
good = bool(inj) and len(inj[0]) > 10
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] {inj[0]!r}" if inj else "  [FAIL]")

print("\n=== Context Awareness through a whole dictation ===")
# finish() end to end: key-down capture, whisper, pipeline, paste, cleanup.
# The context holds a sentinel; it must reach nothing but the rules, and be
# gone afterwards.
import io, contextlib
import context as context_mod
import transcribe as transcribe_mod
from audio import Recorder

SECRET = "ZEBRA-SENTINEL-5150"
ctx = context_mod.Context(category="chat", before=f"the code is {SECRET}, and ",
                          after="", terms=("Priya",), text_read=True)


class FakePending:
    def get(self, timeout):
        return ctx

    def discard(self):
        pass


SENT, PROMPTS = [], []
saved = (cleanup_mod.clean, transcribe_mod.transcribe, Recorder.peak_level,
         f.recorder.stop)
cleanup_mod.clean = lambda text, **kw: (SENT.append((text, kw)) or type(
    "R", (), {"text": text, "source": "llm", "detail": "stub"})())
transcribe_mod.transcribe = lambda wav, lang, **kw: (PROMPTS.append(kw) or type(
    "T", (), {"text": "priya says sounds good", "language": "en", "confidence": 0.99})())
Recorder.peak_level = staticmethod(lambda wav: 0.5)
wav = Path(tempfile.mkstemp(suffix=".wav")[1])
f.recorder.stop = lambda: (str(wav), 1.2)
f.privacy.set(False)
INJECTED.clear()
f._pending = FakePending()
out = io.StringIO()
with contextlib.redirect_stdout(out):
    f.finish()
(cleanup_mod.clean, transcribe_mod.transcribe, Recorder.peak_level,
 f.recorder.stop) = saved
log_text = out.getvalue()

good = bool(INJECTED) and "Priya" in INJECTED[0]
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] dictated with context: {INJECTED!r}")
good = PROMPTS and PROMPTS[0].get("context_terms") == ("Priya",)
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] whisper is primed with terms only")
good = SECRET not in repr(PROMPTS)
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] ...never with the text around the cursor")
good = SECRET not in log_text and "chat" in log_text
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] the log names the app type, never the text")
good = SECRET not in repr(SENT)
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] nothing from the screen reaches OpenRouter")
good = f._context is None and f._pending is None and ctx.before is None and not ctx.terms
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] context cleared after the dictation")
good = not wav.exists()
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] the clip is deleted as before")

# Cancelling a toggled recording clears it too.
ctx2 = context_mod.Context(category="chat", before=SECRET)
f._context = ctx2
f.recorder.stop = lambda: (None, 0.0)
with contextlib.redirect_stdout(io.StringIO()):
    f.cancel_recording()
good = f._context is None and ctx2.before is None
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] cancelling clears it")

def say(label, good):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}")


def finish_with(transcript, pending=None, before_transcribe=None):
    """Run finish() end to end with whisper stubbed to return `transcript`."""
    wav = Path(tempfile.mkstemp(suffix=".wav")[1])
    saved = (transcribe_mod.transcribe, Recorder.peak_level, f.recorder.stop)

    def fake_transcribe(wav_path, lang, **kw):
        if before_transcribe:
            before_transcribe()
        return type("T", (), {"text": transcript, "language": "en", "confidence": 0.99})()
    transcribe_mod.transcribe = fake_transcribe
    Recorder.peak_level = staticmethod(lambda w: 0.5)
    f.recorder.stop = lambda: (str(wav), 1.2)
    f._pending = pending
    f._cancel.clear()
    INJECTED.clear(); CLIPBOARD.clear(); f.ui.events.clear()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        f.finish()
    transcribe_mod.transcribe, Recorder.peak_level, f.recorder.stop = saved
    return out.getvalue()


print("\n=== Escape cancels at every stage ===")
f.stage = "transcribing"
log_out = finish_with("this should never be typed", before_transcribe=f.escape)
say("Escape during transcription: nothing typed", INJECTED == [])
say("...the orb says so", "flash:Cancelled" in f.ui.events)
say("...and the engine is ready for the next dictation", f.stage == "idle" and not f.busy.locked())
saved_process = halo.pipeline.process


def slow_process(*a, **kw):
    f.escape()                       # pressed while the model was working
    return saved_process(*a, **kw)


halo.pipeline.process = slow_process
finish_with("also never typed")
halo.pipeline.process = saved_process
say("Escape during cleanup: nothing typed", INJECTED == [])
say("no recovery clip is left behind", not (halo.paths.RECOVERY_DIR / "pending.wav").exists())

print("\n=== the target is verified before anything is typed ===")
INSERT_RESULT[0] = insertion_mod.Result(False, reason="you switched apps")
finish_with("this was meant for slack")
INSERT_RESULT[0] = insertion_mod.Result(True, "paste")
say("switched apps: the orb says what happened", any("App changed" in e for e in f.ui.events))
say("...and the text waits on the clipboard", CLIPBOARD == ["This was meant for slack."])

print("\n=== scratch that removes only Halo's own insertion ===")
f.records.clear()
run("scratch that", "undo-none")
say("with nothing of Halo's to undo, nothing happens", UNDOS == [] and
    any("Nothing to undo" in e for e in f.ui.events))
run("send the report", "typed")
run("scratch that", "undo")
say("after an insertion, Halo removes it", UNDOS == [True] and not f.records)

print("\n=== language switching by voice ===")
SETS = []
saved_set = halo.settings_mod.current.set
halo.settings_mod.current.set = lambda key, value: SETS.append((key, value))
saved_reload = halo.config.reload
halo.config.reload = lambda: None
run("switch to Spanish", "lang")
say("'switch to Spanish' sets the language", SETS == [("language", "es")])
say("...and types nothing", INJECTED == [])
SETS.clear()
run("type in the password field", "not-lang")
say("'type in the password field' is dictation", SETS == [] and INJECTED)
halo.settings_mod.current.set, halo.config.reload = saved_set, saved_reload

print("\n=== Command Mode edits the selection ===")
REPLACED = []
saved_sel, saved_rep = f._selection, insertion_mod.replace_selection
f._selection = lambda target: ("Please ask John to review it.", True)
insertion_mod.replace_selection = lambda new, orig, target, ax=None, pb=None: (
    REPLACED.append((new, orig)), insertion_mod.Result(True, "ax", range=(0, len(new))))[1]
with contextlib.redirect_stdout(io.StringIO()):
    res = f.command_mode("Replace John with Sarah.", context_mod.Context())
say("a rule command runs with no model", res["ok"] and REPLACED == [
    ("Please ask Sarah to review it.", "Please ask John to review it.")])
say("...and is undoable: the original is kept", f.records[-1].original == "Please ask John to review it.")
f._selection = lambda target: ("", False)
f.ui.events.clear()
with contextlib.redirect_stdout(io.StringIO()):
    res = f.command_mode("make this shorter", context_mod.Context())
say("with nothing selected it asks for a selection", not res["ok"] and
    any("Select some text" in e for e in f.ui.events))
f._selection, insertion_mod.replace_selection = saved_sel, saved_rep

print("\n=== the log never holds what you said ===")
WORD = "ZEBRA-SENTINEL-8808"
log_out = finish_with(f"remember the code {WORD} please")
say("the transcript is typed", INJECTED and WORD in INJECTED[0])
say("...but only its length is logged", WORD not in log_out and "chars" in log_out)
halo.config.DEBUG_LOG_CONTENT = True
log_out = finish_with(f"remember the code {WORD} please")
halo.config.DEBUG_LOG_CONTENT = False
say("debug content logging, when switched on, does log it", WORD in log_out)

f.privacy.set(False)
print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
