"""Structure and house style: lists, email layout, stumbles, questions,
typography, developer terms, per-app profiles and fitting to the cursor.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import formatting as f  # noqa: E402

ok = True
P = f.PROFILES


def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {label}")
    if not good:
        print(f"         got  {got!r}\n         want {want!r}")


print("=== stumbles ===")
check("a doubled word", f.collapse_repeats("the the cat"), "the cat")
check("with a comma", f.collapse_repeats("I, I think so"), "I think so")
check("a cut-off word", f.collapse_repeats("th- the best"), "the best")
check("a repeated phrase", f.collapse_repeats("we need to we need to go"), "we need to go")
check("a triple", f.collapse_repeats("I I I want it"), "I want it")
check("'that that' is grammar", f.collapse_repeats("I know that that is true"),
      "I know that that is true")
check("'had had' is grammar", f.collapse_repeats("she had had enough"), "she had had enough")
check("emphasis is meant", f.collapse_repeats("very very good"), "very very good")
check("a place name", f.collapse_repeats("Bora Bora is nice"), "Bora Bora is nice")
check("a hyphenated word", f.collapse_repeats("e-mail me"), "e-mail me")

print("\n=== days and months ===")
check("days", f.proper_days("on thursday or friday"), "on Thursday or Friday")
check("not inside a domain", f.proper_days("see monday.com"), "see monday.com")
check("'may' and 'march' are verbs too", f.proper_days("we may march"), "we may march")

print("\n=== questions ===")
check("aux + subject", f.fix_questions("Can you send it."), "Can you send it?")
check("no mark at all", f.fix_questions("Is this ready"), "Is this ready?")
check("wh + aux", f.fix_questions("What's the plan."), "What's the plan?")
check("how about", f.fix_questions("How about Friday."), "How about Friday?")
check("an order is not a question", f.fix_questions("Do it now."), "Do it now.")
check("a wish is not a question", f.fix_questions("Have a nice day."), "Have a nice day.")
check("a clause is not a question", f.fix_questions("When I get home I'll call."),
      "When I get home I'll call.")
check("only the question sentence", f.fix_questions("I used whisper.cpp today. Are we done."),
      "I used whisper.cpp today. Are we done?")

print("\n=== lists ===")
check("number one, number two",
      f.format_lists("Groceries number one milk number two eggs number three bread.", P["chat"]),
      ("Groceries:\n1. Milk\n2. Eggs\n3. Bread", True))
check("whisper's punctuation between items",
      f.format_lists("Groceries. Number one, milk. Number two, eggs.", P["document"]),
      ("Groceries:\n1. Milk\n2. Eggs", True))
check("bullets and a sub-bullet",
      f.format_lists("Todo bullet point fix tests bullet point ship it sub bullet tag release",
                     P["document"]),
      ("Todo:\n- Fix tests\n- Ship it\n  - Tag release", True))
check("first/second/third in a document",
      f.format_lists("First, clean the house. Second, buy food. Third, call mom.", P["document"]),
      ("1. Clean the house\n2. Buy food\n3. Call mom", True))
check("...but prose in a chat",
      f.format_lists("First, clean the house. Second, buy food. Third, call mom.", P["chat"])[1],
      False)
check("'a bullet point' is a noun", f.format_lists("Add a bullet point here.", P["document"])[1],
      False)
check("'number one priority' is one cue, not a list",
      f.format_lists("Number one priority is speed.", P["document"])[1], False)
check("a terminal gets no lists",
      f.format_lists("number one foo number two bar", P["terminal"])[1], False)

print("\n=== email layout ===")
check("greeting and sign-off",
      f.email_layout("Hi Sam, I wanted to follow up on the report from yesterday. "
                     "Can you send it? Thanks, Alex"),
      ("Hi Sam,\n\nI wanted to follow up on the report from yesterday. "
       "Can you send it?\n\nThanks,\nAlex", True))
check("a one-liner is left alone", f.email_layout("Hi Sam, quick one."),
      ("Hi Sam, quick one.", False))

print("\n=== typography ===")
check("prose gets curly quotes and dashes",
      f.typography('He said "stop" - and we didn\'t. It\'s the users\' fault.', P["document"]),
      "He said “stop”—and we didn’t. It’s the users’ fault.")
check("a terminal stays ASCII",
      f.typography('echo "hi" - done', P["terminal"]), 'echo "hi" - done')
check("a list bullet is not a dash",
      f.typography("Items:\n- one\n- two", P["document"]), "Items:\n- one\n- two")

print("\n=== developer terms ===")
check("unambiguous terms everywhere",
      f.dev_terms("push it to github and fix the json api", P["unknown"]),
      "push it to GitHub and fix the JSON API")
check("not inside a domain or a filename",
      f.dev_terms("see github.com and data.json", P["unknown"]),
      "see github.com and data.json")
check("'python' is a snake outside an editor",
      f.dev_terms("a python in the zoo", P["unknown"]), "a python in the zoo")
check("...and a language inside one",
      f.dev_terms("write it in python", P["ide"]), "write it in Python")
check("a developer site counts as an editor",
      f.profile_for(type("C", (), {"category": "browser", "host": "github.com"})()).dev_terms,
      "all")
check("a terminal is left exactly as typed",
      f.dev_terms("cat data.json | jq", P["terminal"]), "cat data.json | jq")

print("\n=== the closing full stop ===")
check("chat: a short line has none", f.apply_terminal("Sounds good.", P["chat"], enabled=True),
      "Sounds good")
check("chat: unless you asked for it",
      f.apply_terminal("Sounds good.", P["chat"], enabled=True, chat_period=True), "Sounds good.")
check("chat: two sentences keep theirs",
      f.apply_terminal("Sounds good. See you there.", P["chat"], enabled=True),
      "Sounds good. See you there.")
check("chat: a question keeps its mark", f.apply_terminal("Yes?", P["chat"], enabled=True), "Yes?")
check("document: added", f.apply_terminal("Done", P["document"], enabled=True), "Done.")
check("terminal: never added", f.apply_terminal("git status", P["terminal"], enabled=True),
      "git status")
check("the setting still wins", f.apply_terminal("Done", P["document"], enabled=False), "Done")

print("\n=== fitting into the text around the cursor ===")
A = f.adapt_to_cursor
check("no context, no change", A("Hello.", None, None, P["unknown"]), "Hello.")
check("a space after a word", A("World.", "Hello", None, P["unknown"]), " world.")
check("mid-sentence: lower case", A("Then we go.", "I think ", None, P["unknown"]),
      "then we go.")
check("...but not a name", A("John said hi.", "and ", None, P["unknown"]), "John said hi.")
check("...or a vocabulary term", A("Halo works.", "and ", None, P["unknown"], {"Halo"}),
      "Halo works.")
check("...or I", A("I agree.", "and ", None, P["unknown"]), "I agree.")
check("after a full stop: keep the capital", A("Next.", "Done. ", None, P["unknown"]), "Next.")
check("at a list bullet: keep the capital", A("Milk", "Items:\n- ", None, P["unknown"]), "Milk")
check("the sentence carries on after the cursor",
      A("New idea.", "Here is a ", "for later.", P["unknown"]), "new idea ")
check("punctuation right after the cursor", A("Fine.", "It's ", "!", P["unknown"]), "fine")
check("verbatim only fixes spacing",
      A("World.", "Hello", "and more", P["unknown"], spacing_only=True), " World. ")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
