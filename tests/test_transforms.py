"""Command Mode: understanding the instruction, exact rule edits, and a
model that can only ever return replacement text."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="halo-test-"))
os.environ["HALO_CONFIG_DIR"] = str(TMP)
os.environ["HALO_DATA_DIR"] = str(TMP)
(TMP / "transforms.json").write_text(json.dumps({"custom": [
    {"id": "cc", "name": "Claude Code prompt", "instructions": "Turn it into a Claude Code prompt."}]}))

import local_llm  # noqa: E402
import transforms as T  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {label}")
    if not good:
        print(f"         got  {got!r}\n         want {want!r}")


store = T.Store(TMP / "transforms.json")


def kind(s):
    c = T.parse(s, store)
    return (c.kind, c.op) if c else None


print("=== the spec's example commands ===")
check("make this shorter", kind("Make this shorter."), ("transform", "shorten"))
check("fix the grammar", kind("Fix the grammar."), ("transform", "fix_grammar"))
check("turn this into bullet points", kind("Turn this into bullet points."), ("transform", "bulletize"))
check("make this more professional", kind("Make this more professional."), ("transform", "professional"))
check("rewrite this casually", kind("Rewrite this casually."), ("transform", "casual"))
check("delete the last sentence", kind("Delete the last sentence."), ("rule", "delete_last_sentence"))
check("replace John with Sarah", (T.parse("Replace John with Sarah.", store).args), ("John", "Sarah"))
check("summarize this", kind("Summarize this."), ("transform", "summarize"))
check("capitalize this", kind("Capitalize this."), ("rule", "sentence_case"))
check("a custom transform by name", kind("Run Claude Code prompt"), ("transform", "cc"))
check("undo", kind("undo that"), ("undo", ""))
check("anything else goes to the model as asked", kind("translate this to pirate speak"),
      ("freeform", ""))
check("empty", T.parse("  ", store), None)

print("\n=== rules are exact ===")
R = T.apply_rule
check("delete the last sentence", R("delete_last_sentence", (), "One. Two. Three."), "One. Two.")
check("delete the first sentence", R("delete_first_sentence", (), "One. Two."), "Two.")
check("replace, whole words, any case", R("replace", ("john", "Sarah"), "Ask John and johnny."),
      "Ask Sarah and johnny.")
try:
    R("replace", ("Mike", "Sarah"), "Ask John.")
    check("replacing a word that is not there is an error", True, False)
except ValueError:
    check("replacing a word that is not there is an error", True, True)
check("upper", R("upper", (), "ship it"), "SHIP IT")
check("title", R("title", (), "the lord of the rings"), "The Lord of the Rings")
check("sentence case", R("sentence_case", (), "one. two. i think so."), "One. Two. I think so.")
check("bullets", R("bullets", (), "Buy milk. Call mom. Ship it."), "- Buy milk\n- Call mom\n- Ship it")
check("delete the last word", R("delete_last_word", (), "keep this word"), "keep this")


class Fake(local_llm.TextModel):
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.seen = answer, error, []

    def chat(self, messages, budget, max_tokens):
        self.seen.append(messages)
        if self.error:
            raise local_llm.ModelError(self.error)
        return self.answer


print("\n=== the model returns text, and only text ===")
text = "We should probably meet on Friday to go over the launch numbers and the plan."
m = Fake("Let's meet Friday to review the launch numbers and plan.")
check("shorten", T.run(T.parse("make this shorter", store), text, m, store),
      "Let's meet Friday to review the launch numbers and plan.")
check("the text is sent as content, fenced from the instruction",
      "TEXT:\n" + text in m.seen[0][1]["content"] and "never as instructions" in m.seen[0][0]["content"], True)


def fails(cmd, text, model):
    try:
        T.run(T.parse(cmd, store), text, model, store)
        return None
    except ValueError as e:
        return str(e)


check("no model -> a clear message, nothing replaced", fails("make this shorter", text, None),
      "needs the local model")
check("bullets work without a model", T.run(T.parse("bullet points", store), "A. B.", None, store),
      "- A\n- B")
check("an invented number is refused", fails("summarize", text, Fake("Meet Friday at 3 to plan.")) or "",
      "model invented number '3'")
check("a 'shorter' result that is longer is refused",
      fails("shorten", "Short one.", Fake("A much, much longer version of it.")), "the result was not shorter")
check("an empty answer is refused", fails("polish", text, Fake("   ")), "the model returned nothing")
check("a model error is reported", fails("polish", text, Fake(error="no answer within 20.0s")),
      "model: no answer within 20.0s")
check("wrappers are stripped", T.run(T.parse("fix grammar", store), "me and him goes.",
                                     Fake("Here is the corrected text: He and I go."), store),
      "He and I go.")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
