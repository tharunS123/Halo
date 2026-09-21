"""The local punctuation pass: spoken marks, fillers, casing.

The cases that matter are the ones where a rule must NOT fire. Spoken
punctuation is the only stage that can delete a word the speaker actually
said, so most of this file is about ordinary English surviving it.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import punctuate  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {label}")
    if not good:
        print(f"         got  {got!r}\n         want {want!r}")


def polish(text, **kw):
    return punctuate.polish(text, **kw)[0]


print("=== spoken punctuation becomes marks ===")
check("comma", polish("hello comma world"), "Hello, world.")
check("period at the end", polish("we ship tonight period"), "We ship tonight.")
check("question mark", polish("are we ready question mark"), "Are we ready?")
check("exclamation point", polish("ship it exclamation point"), "Ship it!")
check("new line", polish("first new line second"), "First\nSecond.")
check("new paragraph", polish("one new paragraph two"), "One\n\nTwo.")
check("parens hug their contents",
      polish("this open paren maybe close paren works"),
      "This (maybe) works.")
# The terminal period lands OUTSIDE the closing quote. American style would
# tuck it inside, but that needs to know whether the quote ends the sentence
# or just a phrase, and guessing wrong is worse than being consistent.
check("quotes hug their contents",
      polish("he said open quote stop close quote"), 'He said "stop".')

print("\n=== ...but ordinary English survives ===")
# Each of these is a real word the naive substitution eats. The clause-end
# test catches the first two; the determiner veto catches the third.
check("a noun mid-sentence", polish("the jurassic period was long"),
      "The jurassic period was long.")
check("noun before a verb", polish("my trial period ended today"),
      "My trial period ended today.")
check("determiner in front", polish("add a dash of salt"),
      "Add a dash of salt.")
check("a bare quote is a noun", polish("i read a quote from the article"),
      "I read a quote from the article.")
check("colon in ordinary use", polish("the colon is an organ"),
      "The colon is an organ.")
# "comma" must stay usable mid-clause, so the clause-end test cannot guard it.
# The determiner veto alone has to carry this one.
check("a comma after a determiner", polish("add a comma after this word"),
      "Add a comma after this word.")
check("...but comma still works mid-clause", polish("stop comma then go"),
      "Stop, then go.")
check("a semicolon after a determiner", polish("use a semicolon there"),
      "Use a semicolon there.")

print("\n=== capitalization ===")
check("first word", polish("hello there"), "Hello there.")
check("pronoun I", polish("i think i am right"), "I think I am right.")
check("contractions", polish("i'm sure i'll go"), "I'm sure I'll go.")
# The bug this test exists for: "." inside a word is not a sentence break, and
# capitalizing after it corrupts every dotted term in the user's dictionary.
check("a dot inside a word", polish("i used whisper.cpp today"),
      "I used whisper.cpp today.")
check("a domain", polish("go to example.com now"), "Go to example.com now.")
check("after a real sentence break", polish("one. two. three."),
      "One. Two. Three.")

print("\n=== fillers ===")
check("leading", polish("um so we shipped"), "So we shipped.")
check("mid-sentence", polish("it was uh mostly fine"), "It was mostly fine.")
check("umbrella is not a filler", polish("bring an umbrella"),
      "Bring an umbrella.")
check("I like this is not a filler", polish("i like this one"),
      "I like this one.")

print("\n=== terminal punctuation ===")
check("added when missing", polish("this has no end"), "This has no end.")
check("not doubled", polish("this has one."), "This has one.")
check("not after a question", polish("really?"), "Really?")
check("not after a line break", polish("first new line"), "First\n")
check("added after a closing bracket",
      polish("see open paren below close paren"), "See (below).")

print("\n=== each stage can be turned off ===")
check("spoken off", polish("hello comma world", spoken=False, terminal=False),
      "Hello comma world")
check("fillers off", polish("um hello", fillers=False, terminal=False),
      "Um hello")
check("terminal off", polish("no period here", terminal=False),
      "No period here")

print("\n=== nothing in, nothing out ===")
check("empty", polish(""), "")
check("whitespace", polish("   "), "   ")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
