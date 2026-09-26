"""Writing styles: the right style per app, overrides, custom styles, and the
rules a style applies with no model at all."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="halo-test-"))
os.environ["HALO_CONFIG_DIR"] = str(FIXTURES)
os.environ["HALO_DATA_DIR"] = str(TMP)

import context  # noqa: E402
import pipeline  # noqa: E402
import styles  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {label}")
    if not good:
        print(f"         got  {got!r}\n         want {want!r}")


def ctx(bundle="", category="unknown", host=""):
    return context.Context(bundle_id=bundle, category=category, host=host)


path = TMP / "styles.json"
path.write_text(json.dumps({}))
S = styles.Styles(path)

print("=== the app decides the style ===")
cases = [
    ("Messages", ctx("com.apple.MobileSMS", "chat"), "casual"),
    ("Slack", ctx("com.tinyspeck.slackmacgap", "chat"), "concise"),
    ("Mail", ctx("com.apple.mail", "email"), "professional"),
    ("Google Docs", ctx("com.apple.Safari", "document", "docs.google.com"), "neutral"),
    ("Cursor", ctx("com.todesktop.230313mzl4w4u92", "ide"), "coding"),
    ("Terminal", ctx("com.apple.Terminal", "terminal"), "coding"),
    ("ChatGPT in a browser", ctx("com.apple.Safari", "chat", "chatgpt.com"), "coding"),
    ("an unknown app", ctx("org.example", "unknown"), "neutral"),
    ("no context at all", None, "neutral"),
]
for label, c, want in cases:
    check(label, S.for_context(c)[0].id, want)
check("categories", styles.category_for(ctx("com.apple.MobileSMS", "chat")), "personal_messaging")

print("\n=== overrides, and custom styles ===")
path.write_text(json.dumps({
    "categories": {"email": "formal"},
    "apps": {"com.tinyspeck.slackmacgap": "mine", "host:docs.google.com": "concise"},
    "custom": [{"id": "mine", "name": "My Slack", "base": "casual",
                "instructions": "Write Slack messages casually. Do not add periods to "
                                "short messages. Never use em dashes."}]}))
os.utime(path, (1, 1))          # a different mtime from the first write
S.load()
check("a category default can change", S.for_context(ctx("com.apple.mail", "email"))[0].id, "formal")
check("an app assignment beats its category",
      S.for_context(ctx("com.tinyspeck.slackmacgap", "chat"))[0].name, "My Slack")
check("a website assignment beats its browser",
      S.for_context(ctx("com.apple.Safari", "document", "docs.google.com"))[0].id, "concise")
mine = S.get("mine")
check("custom instructions become rules: no period on short messages", mine.rules.terminal,
      "multi_sentence")
check("...and no em dashes", mine.rules.no_em_dash, True)
check("an unknown style id falls back to neutral", S.get("nope").id, "neutral")

print("\n=== directives read from free text ===")
D = styles.directives
check("never use em dashes", D("Never use em dashes. Use short paragraphs.").no_em_dash, True)
check("no periods on short messages", D("Do not add periods to short messages.").terminal,
      "multi_sentence")
check("no periods at all", D("Never end with a period.").terminal, "never")
check("lowercase", D("write in all lowercase").lowercase_start, True)
check("'do not use lowercase' is not lowercase", D("Do not use lowercase.").lowercase_start, False)
check("plain instructions have no rules", D("Write polished business email.") == styles.Rules(), True)

print("\n=== rules apply with no model ===")
F = styles.finish
check("excited", F("We shipped it.", styles.BUILTIN["excited"]), "We shipped it!")
check("very casual: lowercase, no full stop", F("Sounds good to me.", styles.BUILTIN["very_casual"]),
      "sounds good to me")
check("...but a name keeps its capital", F("Priya is in.", styles.BUILTIN["very_casual"]), "Priya is in")
check("no em dashes", F("It works — mostly.", mine), "It works, mostly.")
check("...and a range becomes a hyphen", F("Pages 5–10.", mine), "Pages 5-10.")
check("neutral changes nothing", F("Fine.", styles.BUILTIN["neutral"]), "Fine.")

print("\n=== through the pipeline ===")
no_model = lambda mode, privacy: (None, "stub")  # noqa: E731
pipeline._styles = S
r = pipeline.process("we shipped it", mode="normal", ctx=ctx("com.apple.mail", "email"),
                     select=no_model)
check("Mail -> Formal: a full stop", r.text, "We shipped it.")
check("the style is reported", r.style, "Formal")
r = pipeline.process("sounds good", mode="normal", ctx=ctx("com.tinyspeck.slackmacgap", "chat"),
                     select=no_model)
check("Slack -> My Slack: no period on a short message", r.text, "Sounds good")


class Fake:
    kind, remote, name = "local", False, "fake"

    def __init__(self):
        self.seen = []

    def chat(self, messages, budget, max_tokens):
        self.seen.append(messages)
        return messages[-1]["content"]


m = Fake()
pipeline.process("the report is done", mode="polished",
                 ctx=ctx("com.tinyspeck.slackmacgap", "chat"), select=lambda mode, privacy: (m, ""))
check("custom instructions reach the local model", "Never use em dashes" in m.seen[0][0]["content"], True)

seen = []
import cleanup  # noqa: E402
saved = cleanup.clean
cleanup.clean = lambda text, **kw: (seen.append(kw), cleanup.CleanupResult(text, "llm", "x"))[1]


class Remote:
    kind, remote, name = "openrouter", True, "OpenRouter"


pipeline.process("the report is done", mode="polished", ctx=ctx("com.tinyspeck.slackmacgap", "chat"),
                 select=lambda mode, privacy: (Remote(), ""))
cleanup.clean = saved
check("...but never to OpenRouter", "em dashes" in repr(seen), False)

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
