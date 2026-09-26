"""Developer Mode: vocabulary, case conventions, dots, paths, flags,
terminal commands and on-screen identifiers -- and nothing in plain prose."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))
os.environ["HALO_CONFIG_DIR"] = str(FIXTURES)
os.environ["HALO_DATA_DIR"] = tempfile.mkdtemp(prefix="halo-test-")

import config  # noqa: E402
import context  # noqa: E402
import devmode  # noqa: E402
import pipeline  # noqa: E402

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok &= good
    print(f"  [{'PASS' if good else 'FAIL'}] {label}")
    if not good:
        print(f"         got  {got!r}\n         want {want!r}")


A = devmode.apply

print("=== vocabulary ===")
check("the spec's examples", A("use swift UI and super base with post grass"),
      "use SwiftUI and Supabase with Postgres")
check("more terms", A("type script, java script, cloud flare, graph q l, async await"),
      "TypeScript, JavaScript, Cloudflare, GraphQL, async/await")
check("UIViewController", A("subclass UI view controller"), "subclass UIViewController")

print("\n=== case conventions ===")
check("camel", A("camel case user id"), "userId")
check("...stops at a function word", A("set camel case user id to five"), "set userId to five")
check("pascal", A("pascal case user profile view"), "UserProfileView")
check("snake", A("snake case max retry count"), "max_retry_count")
check("kebab", A("kebab case my component"), "my-component")
check("constant", A("constant case api base url"), "API_BASE_URL")

print("\n=== dots, paths, flags ===")
check("filename", A("open main dot swift"), "open main.swift")
check("member access", A("self dot view dot frame"), "self.view.frame")
check("'polka dot dress' is a dress", A("a polka dot dress"), "a polka dot dress")
check("home path", A("tilde slash projects slash halo"), "~/projects/halo")
check("absolute path", A("slash usr slash local slash bin"), "/usr/local/bin")
check("long flag", A("run with dash dash verbose"), "run with --verbose")
check("short flag", A("ls dash l"), "ls -l")
check("underscore", A("user underscore id"), "user_id")
check("a multi-word flag", A("dash dash dry dash run"), "--dry-run")

print("\n=== context ===")
editor = context.Context(category="ide", terms=("UserViewController", "fetch_data", "viewModel"))
check("snaps to identifiers on screen", A("the user view controller calls fetch data", editor),
      "the UserViewController calls fetch_data")
check("single words are left alone", A("the model is fine", editor), "the model is fine")
term = context.Context(category="terminal")
check("a terminal command", A("Git status.", term), "git status")
check("prose in a terminal is left alone", A("Explain this error.", term), "Explain this error.")

print("\n=== when it is on ===")
check("auto: on in an IDE", devmode.active(editor), True)
check("auto: on in a terminal", devmode.active(term), True)
check("auto: on for github.com", devmode.active(context.Context(category="browser", host="github.com")),
      True)
check("auto: off in Mail", devmode.active(context.Context(category="email")), False)
config.DEVELOPER_MODE = "on"
check("forced on", devmode.active(None), True)
config.DEVELOPER_MODE = "off"
check("forced off", devmode.active(editor), False)
config.DEVELOPER_MODE = "auto"

print("\n=== through the pipeline ===")
no = lambda mode, privacy: (None, "stub")  # noqa: E731
check("in an editor", pipeline.process("rename camel case user id dash dash dry dash run", mode="normal",
                                       ctx=editor, select=no).text,
      "Rename userId --dry-run.")
check("prose elsewhere is untouched",
      pipeline.process("add a dash of salt", mode="normal",
                       ctx=context.Context(category="document"), select=no).text,
      "Add a dash of salt.")

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
