"""Spoken forms to written ones: numbers, money, times, dates, phones,
emails, URLs. Every rule is paired with the ordinary speech it must not touch.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import itn  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {label}")
    if not good:
        print(f"         got  {got!r}\n         want {want!r}")


n = itn.normalize

print("=== cardinals ===")
check("ten and up become digits", n("twenty five people came"), "25 people came")
check("with 'and'", n("one hundred and five"), "105")
check("thousands", n("three thousand two hundred"), "3200")
check("commas from ten thousand", n("forty two thousand users"), "42,000 users")
check("a decimal", n("three point five million"), "3.5 million")
check("a scale stays a word", n("two million people"), "2 million people")
check("...one to nine stay words", n("one of them had two options"),
      "one of them had two options")
check("...unless a unit follows", n("it took five seconds"), "it took 5 seconds")
check("...or a label precedes", n("see page three"), "see page 3")
check("...version numbers", n("version two"), "version 2")
check("idioms survive", n("one in a million"), "one in a million")
check("a bare scale survives", n("thousands of them"), "thousands of them")

print("\n=== ordinals ===")
check("eleventh and up", n("the twenty first century"), "the 21st century")
check("first to tenth stay words", n("the first time"), "the first time")
check("teens", n("on the thirteenth floor"), "on the 13th floor")

print("\n=== percentages and money ===")
check("percent", n("It went up twenty five percent."), "It went up 25%.")
check("digits percent", n("It's 50 percent off."), "It's 50% off.")
check("dollars and cents", n("It costs five dollars and fifty cents."),
      "It costs $5.50.")
check("whisper's own digits", n("That's 5 dollars."), "That's $5.")
check("millions of dollars", n("We raised two million dollars."), "We raised $2 million.")
check("euros", n("about thirty euros"), "about €30")

print("\n=== times ===")
check("hour and minutes", n("Meet at three thirty p.m."), "Meet at 3:30 PM.")
check("whisper's 3.30 p.m.", n("Meet at 3.30 p.m. tomorrow."), "Meet at 3:30 PM tomorrow.")
check("the full stop survives p.m.", n("Call at 5 pm. Then leave."),
      "Call at 5 PM. Then leave.")
# "a.m." at the very end is also the sentence's full stop, so one survives.
check("oh-five", n("at seven oh five a.m."), "at 7:05 AM.")
check("no dot, no full stop", n("call at 5 pm"), "call at 5 PM")
check("o'clock", n("at seven o'clock"), "at 7 o'clock")
check("'I am' is not a time", n("I am here"), "I am here")

print("\n=== dates and years ===")
check("month and ordinal", n("on January fifth"), "on January 5")
check("with a year", n("on January twenty first, 2027"), "on January 21, 2027")
check("the fifth of March", n("the fifth of March"), "March 5")
check("a spoken year", n("back in twenty twenty six"), "back in 2026")
check("nineteen ninety nine", n("since nineteen ninety nine"), "since 1999")
check("the modal 'may' is not a month", n("I may go on May fifth"), "I may go on May 5")
check("May I", n("May I help"), "May I help")

print("\n=== phone numbers ===")
check("ten spoken digits", n("My number is five five five one two three four five six seven."),
      "My number is (555) 123-4567.")
check("seven digits", n("call five five five one two three four"), "call 555-1234")
check("whisper's groups", n("call 555 123 4567"), "call (555) 123-4567")
check("three digits are not a phone", n("one two three go"), "one two three go")

print("\n=== emails ===")
check("dotted local part", n("email me at john dot smith at gmail dot com"),
      "email me at john.smith@gmail.com")
check("a name", n("send it to Sam at example dot com"), "send it to sam@example.com")
check("a cue word", n("my email is hello at halo dot dev"), "my email is hello@halo.dev")
check("'look at' is not an address", n("look at google dot com"), "look at google.com")
check("'at home' is not an address", n("I'm at home at John's place"),
      "I'm at home at John's place")

print("\n=== URLs ===")
check("a domain", n("go to example dot com"), "go to example.com")
check("a path", n("go to example dot com slash docs"), "go to example.com/docs")
check("a scheme", n("https colon slash slash github dot com slash halo"),
      "https://github.com/halo")
check("www", n("visit www dot apple dot com"), "visit www.apple.com")
check("'dot' alone is speech", n("connect the dots"), "connect the dots")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
