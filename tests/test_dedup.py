"""STEP 3a TEST: dedup + wrapper stripping, offline (no API key needed)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

from cleanup import deduplicate, _strip_wrappers, _looks_wrong

S = "I need to refactor the parser before Friday."
CASES = [
    ("no repeat",        S, S),
    ("blank-line echo",  f"{S}\n\n{S}", S),
    ("newline echo",     f"{S}\n{S}", S),
    ("space echo",       f"{S} {S}", S),
    ("punct-drift echo", f"{S}\n\nI need to refactor the parser before Friday", S),
    ("triple echo",      f"{S}\n\n{S}\n\n{S}", S),
    ("two sentences",    "First thing. Second thing.", "First thing. Second thing."),
    ("2-sent echoed",    "First thing. Second thing. First thing. Second thing.",
                         "First thing. Second thing."),
]
print("=== deduplicate ===")
ok = True
for name, inp, want in CASES:
    got = deduplicate(inp)
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {name}")
    if not good:
        print(f"         want: {want!r}\n         got : {got!r}")

print("\n=== _strip_wrappers ===")
W = [
    ("Here is the cleaned transcript: " + S, S),
    ("Here's the cleaned-up text:\n" + S, S),
    (f'"{S}"', S),
    (f"```\n{S}\n```", S),
    ("Output: " + S, S),
    (S, S),
]
for inp, want in W:
    got = _strip_wrappers(inp)
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {inp[:42]!r}")
    if not good:
        print(f"         want: {want!r}\n         got : {got!r}")

print("\n=== _looks_wrong (reject bad model output) ===")
raw = "um so i need to uh refactor the parser before friday"
R = [
    ("good cleanup",  S, False),
    ("empty",         "", True),
    ("commentary",    S + " " + "Let me explain why this matters. " * 12, True),
    ("answered it",   "You should use a recursive descent parser with lookahead.", True),
]
for name, cand, should_reject in R:
    reason = _looks_wrong(raw, cand)
    good = bool(reason) == should_reject
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {name}: {reason or 'accepted'}")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
