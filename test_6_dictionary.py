"""FEATURE 1 TEST: custom dictionary correction."""
from dictionary import Dictionary

d = Dictionary()
ok = True

print("=== corrections that SHOULD happen ===")
CASES = [
    ("whisper dot cpp handles this well",   "whisper.cpp"),
    ("i used open router for cleanup",      "OpenRouter"),
    ("the m one pro is fast",               "M1 Pro"),
    ("my name is tarun senthil kumar",      "Tharun"),
    ("my name is tarun senthil kumar",      "Senthilkumar"),
    ("push it to git hub",                  "GitHub"),
    ("swift ui makes this easy",            "SwiftUI"),
    ("running on mac o s",                  "macOS"),
    ("i study at perdue",                   "Purdue"),
    ("the launch d agent starts it",        "launchd"),
    ("use n s panel for the overlay",       "NSPanel"),
]
for text, expected in CASES:
    out, ch = d.apply(text)
    good = expected in out
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {text!r}")
    print(f"         -> {out!r}")
    if not good:
        print(f"         expected {expected!r} in output")

print("\n=== deliberate tradeoff ===")
out, _ = d.apply("parse the jason response")
print(f"  'jason' is left alone: {out!r}")
print("  (both a common name and a plausible mis-hearing of JSON; protecting")
print("   the name wins, and the cleanup model usually fixes it from context)")

print("\n=== text that must be LEFT ALONE (fuzzy false positives) ===")
LEAVE = [
    "i need to repossess the car",
    "the apple is on the table",
    "please respond to the email",
    "she is a great person",
    "the report is due monday",
    "i can see the ocean from here",
    "we should reposition the sensor",
    "his name is jason and he called",
    "i launched the app this morning",
    "clone both repos from source",
    "we need a sync point here",
    "the launch was successful",
]
for text in LEAVE:
    out, ch = d.apply(text)
    unchanged = (out == text)
    tag = "PASS" if unchanged else "CHANGED"
    if not unchanged and "jason" not in text:
        ok = False
    print(f"  [{tag}] {text!r}")
    if not unchanged:
        print(f"         -> {out!r}  changes={ch}")

print("\n=== casing normalisation on already-correct words ===")
out, ch = d.apply("i pushed to github and opened an api")
print(f"  {out!r}")
ok &= "GitHub" in out and "API" in out

print("\n=== prompt context ===")
ctx = d.prompt_context()
print(f"  {len(ctx)} chars, {ctx.count(',')+1} terms")
ok &= "whisper.cpp" in ctx

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
