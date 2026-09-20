"""FEATURE 2 TEST: snippet trigger matching."""
import sys
from snippets import Snippets

s = Snippets()
ok = True

print("=== should MATCH (trigger spoken alone) ===")
HITS = [
    ("my email signature",        "my email signature"),
    ("My email signature.",       "my email signature"),
    ("email sig",                 "my email signature"),
    ("my email sig",              "my email signature"),
    ("standup template",          "standup template"),
    ("stand up template",         "standup template"),
    ("Daily standup.",            "standup template"),
    ("meeting notes template",    "meeting notes template"),
    ("standup templates",         "standup template"),   # plural slip
]
for said, expect in HITS:
    m = s.match(said)
    good = m is not None and m[0].trigger == expect
    ok &= good
    got = f"{m[0].trigger!r} @{m[1]:.2f}" if m else "no match"
    print(f"  [{'PASS' if good else 'FAIL'}] {said!r} -> {got}")

print("\n=== should NOT match (ordinary dictation) ===")
MISS = [
    "i need to update my email signature before sending this to the team",
    "lets talk about the standup tomorrow morning",
    "can you send me the meeting notes",
    "my email is not working today",
    "the template looks good",
    "hello there how are you doing",
]
for said in MISS:
    m = s.match(said)
    good = m is None
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {said!r}"
          + ("" if good else f" -> WRONGLY matched {m[0].trigger!r} @{m[1]:.2f}"))

print("\n=== expansion content ===")
m = s.match("standup template")
if m:
    print(f"  lines: {len(m[0].text.splitlines())}")
    print("  " + m[0].text.replace("\n", "\n  "))
ok &= m is not None and "\n" in m[0].text

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
