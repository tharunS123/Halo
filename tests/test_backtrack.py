"""Spoken self-correction: the corrections that must resolve, and -- more
important -- the ordinary sentences that happen to contain a cue word and
must come through untouched.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import backtrack  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {label}")
    if not good:
        print(f"         got  {got!r}\n         want {want!r}")


def fix(text):
    return backtrack.resolve(text).text


print("=== the three examples from the spec ===")
check("actually", fix("Meet me Thursday — actually Friday."), "Meet me Friday.")
check("no", fix("Send it to John — no, Jake."), "Send it to Jake.")
check("make that, mid-sentence", fix("We need five — make that six — copies."),
      "We need six copies.")

print("\n=== the way whisper actually punctuates them ===")
check("comma before the cue", fix("Meet me Thursday, actually Friday."),
      "Meet me Friday.")
check("full stop before the cue", fix("Send it to John. No, Jake."),
      "Send it to Jake.")
check("commas around make that", fix("We need five, make that six, copies."),
      "We need six copies.")
check("no pause after the replacement", fix("We need five, make that six copies."),
      "We need six copies.")

print("\n=== every cue ===")
check("sorry", fix("Tell him, sorry, her."), "Tell her.")
check("I mean", fix("We'll go by car, I mean train."), "We'll go by train.")
check("no", fix("The meeting is on Monday, no, Tuesday."), "The meeting is on Tuesday.")
check("correction", fix("It costs twenty five dollars, correction, thirty dollars."),
      "It costs thirty dollars.")
check("make that", fix("Order three, make that four."), "Order four.")
check("rather", fix("Let's use Python, rather Swift, for this."),
      "Let's use Swift for this.")
check("or rather", fix("It's due in June, or rather July."), "It's due in July.")
check("wait", fix("The meeting is on Monday, wait, Tuesday."),
      "The meeting is on Tuesday.")
check("scratch that, mid-sentence",
      fix("I think we should go. We could also, scratch that, let's just go."),
      "I think we should go. let's just go.")
check("scratch that, at a sentence start drops the one before",
      fix("I think we should go. Scratch that. Let's stay home."),
      "Let's stay home.")
check("let me rephrase", fix("The API is slow. Let me rephrase. The API times out."),
      "The API times out.")

print("\n=== what the replacement replaces is found by meaning ===")
check("a time keeps its PM", fix("Meet me at 3 PM, actually 4."), "Meet me at 4 PM.")
check("a day keeps what follows it", fix("Meet me Thursday at noon, actually Friday."),
      "Meet me Friday at noon.")
check("a longer replacement takes its span",
      fix("Meet me Thursday at 3, actually Friday at 4."), "Meet me Friday at 4.")
check("a two-word name", fix("Call John Smith, no, Jake Miller."), "Call Jake Miller.")
check("restart from the repeated words",
      fix("Send it to John, sorry, send it to Jake."), "send it to Jake.")
check("restart on the article", fix("I'll take the red one, I mean the blue one."),
      "I'll take the blue one.")
check("a conjunction keeps its comma",
      fix("Invite John, no, Jake, and Mary too."), "Invite Jake, and Mary too.")
check("two corrections in one utterance",
      fix("Meet Thursday, actually Friday, at 3, make that 4."), "Meet Friday at 4.")

print("\n=== ordinary English is left alone ===")
for sentence in (
        "I actually like it.",               # no pause before the cue
        "No, I don't think so.",             # the cue opens the utterance
        "I said no, Jake.",                  # no pause before "no"
        "Wait for me.",
        "Sorry for the delay.",
        "Thanks, sorry for the delay.",      # an apology, not a correction
        "Seriously, I mean it.",
        "You're right, I mean it.",
        "It's fine, actually.",              # nothing after the cue
        "No problem, no worries.",
        "Hold on, wait until Friday.",
        "I'd rather not.",
        "Please, no more meetings.",
        "It was, rather, unusual.",          # "rather" is never positional
        "That's, actually, a good point.",
        "I don't know, actually, maybe we should wait.",
):
    check(sentence, fix(sentence), sentence)

print("\n=== ambiguity is reported, not guessed ===")
r = backtrack.resolve("It was, rather, unusual.")
check("an aside is flagged for the model", r.ambiguous, ["rather"])
check("...and not changed", r.text, "It was, rather, unusual.")
r = backtrack.resolve("Sorry for the delay.")
check("an opening cue is not even ambiguous", r.ambiguous, [])
r = backtrack.resolve("Meet me Thursday, actually Friday.")
check("a repair says how it was found", [x.method for x in r.repairs], ["typed"])

print("\n=== edge cases ===")
check("empty", fix(""), "")
check("only a cue", fix("Actually."), "Actually.")
check("scratch that at the end leaves nothing",
      fix("Meet me at noon, scratch that."), "")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
