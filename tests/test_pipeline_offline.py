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
import inject as inject_mod
import overlay as overlay_mod

# No network in a test: the cleanup pass is exercised by test_dedup.py, and
# here it only has to return something recognisable.
cleanup_mod.clean = lambda text, vocabulary=None, language="en": type(
    "R", (), {"text": text, "source": "llm", "detail": "stubbed"})()

# --- capture instead of typing into whatever has focus ---
INJECTED, UNDOS = [], []
inject_mod.inject = lambda text, restore_clipboard=True: INJECTED.append(text)
inject_mod.undo = lambda: UNDOS.append(True)
inject_mod.copy_only = lambda text: None

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
f.last_injected = "some earlier text"
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
f.last_injected = None
inj, _, ev = run("hey halo summarize that", "noctx")
good = inj == [] and any("error" in e for e in ev)
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] ui={ev}")

print("\n=== ordinary dictation still reaches cleanup ===")
inj, _, _ = run("um so i think we should ship this on friday", "normal")
good = bool(inj) and len(inj[0]) > 10
ok &= good; print(f"  [{'PASS' if good else 'FAIL'}] {inj[0]!r}" if inj else "  [FAIL]")

f.privacy.set(False)
print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
