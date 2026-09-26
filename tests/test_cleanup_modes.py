"""Cleanup modes, provider choice, and the promise that a model can only ever
make things better: every way a model can fail must end in the rules' text.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

# Before config is imported: the fixtures' vocabulary, and a data dir with no
# local model in it, so nothing here can find a real one.
os.environ["HALO_CONFIG_DIR"] = str(FIXTURES)
os.environ["HALO_DATA_DIR"] = tempfile.mkdtemp(prefix="halo-test-")

import cleanup  # noqa: E402
import config  # noqa: E402
import context  # noqa: E402
import dictionary  # noqa: E402
import local_llm  # noqa: E402
import pipeline  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {label}")
    if not good:
        print(f"         got  {got!r}\n         want {want!r}")


D = dictionary.Dictionary()
NO_MODEL = lambda mode, privacy: (None, "stubbed out")  # noqa: E731


def run(text, mode, ctx=None, select=NO_MODEL):
    return pipeline.process(text, mode=mode, ctx=ctx, dictionary=D, select=select)


SAID = "um so we need five, make that six copies of the the report by friday"

print("=== one utterance, five modes, no model ===")
check("off", run(SAID, "off").text, SAID)
check("verbatim", run(SAID, "verbatim").text, SAID)
check("light", run(SAID, "light").text,
      "So we need five, make that six copies of the report by Friday.")
check("normal", run(SAID, "normal").text, "So we need six copies of the report by Friday.")
check("polished (rules alone match normal)", run(SAID, "polished").text,
      "So we need six copies of the report by Friday.")
check("light is 0.3's local polish", run("um so this should stay local comma and uncleaned",
                                         "light").text,
      "So this should stay local, and uncleaned.")
check("verbatim keeps spoken punctuation", run("hello comma world", "verbatim").text,
      "hello, world")
check("the source is the rules", run(SAID, "normal").source, "rules")
check("off is raw", run(SAID, "off").source, "raw")
check("non-English skips English-only rules",
      pipeline.process("uno, no, dos", mode="normal", language="es", select=NO_MODEL).text,
      "Uno, no, dos.")


class FakeModel(local_llm.TextModel):
    kind = "local"

    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    @property
    def name(self):
        return "fake"

    def chat(self, messages, budget, max_tokens):
        self.calls.append(messages)
        if self.error:
            raise local_llm.ModelError(self.error)
        return self.answer


def with_model(model):
    return lambda mode, privacy: (model, "")


print("\n=== a good answer is used ===")
m = FakeModel("So we need six copies of the report by Friday.")
r = run(SAID, "normal", select=with_model(m))
check("source", r.source, "local")
check("text", r.text, "So we need six copies of the report by Friday.")
check("the model saw the rules' output, not the raw transcript",
      m.calls[0][-1]["content"], "So we need six copies of the report by Friday.")
check("Light never asks a model", run(SAID, "light", select=with_model(m)).source, "rules")

print("\n=== every failure falls back to the rules ===")
rules_text = "So we need six copies of the report by Friday."
for label, model in (
        ("unavailable / loading", FakeModel(error="local model loading")),
        ("too slow", FakeModel(error="no answer within 1.5s")),
        ("crashed", FakeModel(error="server not reachable")),
        ("empty", FakeModel("   ")),
        ("invented a number", FakeModel("So we need seven copies of the report by Friday, 2027.")),
        ("invented a name", FakeModel("So we need six copies of the report for Bob by Friday.")),
        ("answered instead of cleaning", FakeModel(
            "Sure! Here is a detailed plan for producing six copies of your report, "
            "including printing, binding, distribution and a timeline for review.")),
):
    r = run(SAID, "normal", select=with_model(model))
    check(label, (r.source, r.text, r.fell_back), ("rules", rules_text, True))

r = run("What's the capital of France?", "polished",
        select=with_model(FakeModel("The capital of France is Paris.")))
check("a question stays a question", r.text, "What's the capital of France?")

listed = "groceries number one milk number two eggs"
r = run(listed, "normal", select=with_model(FakeModel("Groceries: 1. Milk 2. Eggs")))
check("a model that flattens a list is refused", r.text, "Groceries:\n1. Milk\n2. Eggs")

r = run("I use kubernetes daily", "normal", select=with_model(FakeModel("I use kubernetes daily.")))
check("house style is re-applied after the model", r.text, "I use Kubernetes daily.")
r = run("i used whisper dot cpp", "normal", select=with_model(FakeModel("I used whisper cpp.")))
check("vocabulary is re-applied after the model", "whisper.cpp" in r.text, True)

print("\n=== provider choice ===")
saved = (config.CLEANUP_PROVIDER, config.CLEANUP_ENABLED, config.get_api_key,
         local_llm.local_installed)
config.get_api_key = lambda: "sk-test"
local_llm.local_installed = lambda: False
try:
    config.CLEANUP_PROVIDER, config.CLEANUP_ENABLED = "auto", True
    check("auto, no local model, key -> OpenRouter",
          local_llm.select("normal", privacy=False)[0].kind, "openrouter")
    check("...but never in Privacy Mode", local_llm.select("normal", privacy=True)[0], None)
    config.CLEANUP_ENABLED = False
    check("...and never with OpenRouter switched off (the 0.3.x bug)",
          local_llm.select("normal", privacy=False)[0], None)
    config.CLEANUP_ENABLED = True
    config.CLEANUP_PROVIDER = "local"
    check("local only never falls through to OpenRouter",
          local_llm.select("normal", privacy=False)[0], None)
    config.CLEANUP_PROVIDER = "none"
    check("none means rules only", local_llm.select("normal", privacy=False)[0], None)
    config.CLEANUP_PROVIDER = "auto"
    check("light never asks", local_llm.select("light", privacy=False)[0], None)

    class NotReady(FakeModel):
        def usable(self):
            return False

        def status(self):
            return local_llm.Status("loading")
    local_llm.local_installed = lambda: True
    saved_local = local_llm.local_model
    local_llm.local_model = lambda: NotReady()
    model, why = local_llm.select("normal", privacy=False)
    check("an installed local model that is loading does NOT hand off to OpenRouter",
          (model, why.startswith("local model loading")), (None, True))
    local_llm.local_model = saved_local
finally:
    (config.CLEANUP_PROVIDER, config.CLEANUP_ENABLED, config.get_api_key,
     local_llm.local_installed) = saved

print("\n=== what each provider is told ===")
SECRET = "ZEBRA-SENTINEL-4417"
ctx = context.Context(category="chat", before=f"the code is {SECRET} and Priya said ",
                      after="", terms=("Priya",))
m = FakeModel("Sounds good, Priya.")
run("sounds good priya", "normal", ctx=ctx, select=with_model(m))
sent = repr(m.calls)
check("the local model gets the names near the cursor", "Priya" in sent, True)
check("...but never the text around it", SECRET in sent, False)

seen = []
saved_clean = cleanup.clean


def fake_clean(text, **kw):
    seen.append((text, kw))
    return cleanup.CleanupResult(text, "llm", "stub")


cleanup.clean = fake_clean
try:
    run("sounds good priya", "normal", ctx=ctx,
        select=lambda mode, privacy: (local_llm.OpenRouter(), ""))
finally:
    cleanup.clean = saved_clean
check("OpenRouter is called", len(seen), 1)
check("OpenRouter never sees the text around the cursor", SECRET in repr(seen), False)
check("...nor the names from it", "Priya" in repr(seen[0][1]), False)

print("\n=== context shapes the result ===")
chat = context.Context(category="chat", before="", after="")
check("chat: no full stop on a short reply", run("sounds good", "normal", ctx=chat).text,
      "Sounds good")
mid = context.Context(category="document", before="We should ", after=" tomorrow.")
check("mid-sentence: lower case and no full stop",
      run("Probably ship it", "normal", ctx=mid).text, "probably ship it")
glued = context.Context(category="document", before="We should", after="tomorrow.")
check("...and spaced from words it touches",
      run("Probably ship it", "normal", ctx=glued).text, " probably ship it ")
check("a name near the cursor keeps its capital mid-sentence",
      run("Priya agrees", "normal",
          ctx=context.Context(category="chat", before="and ", after="", terms=("Priya",))).text,
      "Priya agrees")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
