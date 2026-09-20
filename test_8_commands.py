"""FEATURE 4 TEST: voice command detection."""
import sys
from commands import Commands

c = Commands()
ok = True

print("=== fixed commands ===")
HITS = [
    ("scratch that",          "undo"),
    ("Scratch that.",         "undo"),
    ("delete that",           "undo"),
    ("strike that",           "undo"),
    ("new line",              "newline"),
    ("newline",               "newline"),
    ("new paragraph",         "paragraph"),
    ("privacy on",            "privacy_on"),
    ("privacy mode on",       "privacy_on"),
    ("go private",            "privacy_on"),
    ("privacy off",           "privacy_off"),
]
for said, expect in HITS:
    d = c.detect(said)
    good = d is not None and d.action == expect
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {said!r} -> {d}")

print("\n=== AI commands ('hey halo, ...') ===")
AI = [
    ("hey halo make that more formal",            "make that more formal"),
    ("Hey Halo, summarize the last paragraph.",   "summarize the last paragraph"),
    ("hey halo turn that into bullet points",      "turn that into bullet points"),
    ("hey halo rewrite that shorter",             "rewrite that shorter"),
]
for said, expect_arg in AI:
    d = c.detect(said)
    good = d is not None and d.action == "ai" and d.argument == expect_arg
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {said!r}")
    print(f"         -> {d}")

print("\n=== ordinary dictation must NOT trigger ===")
MISS = [
    "i had to scratch that idea because it did not work out",
    "lets start a new line of business next quarter",
    "the privacy policy needs updating before launch",
    "delete that file when you get a chance please",
    "we should go private with the company",
    "new paragraph styles are defined in the stylesheet",
    "hello there how are you doing today",
]
for said in MISS:
    d = c.detect(said)
    good = d is None
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {said!r}" + ("" if good else f" -> {d}"))

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
