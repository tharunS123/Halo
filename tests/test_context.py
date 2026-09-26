"""Context Awareness privacy rules, against a fake Accessibility backend that
records every attribute Halo asks for.

The claims in context.py's docstring are only worth something if a test
fails when one stops being true. The central one: in a secure field, not a
single text attribute is even REQUESTED -- not "read and then discarded".
"""
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import context  # noqa: E402

ok = True
SECRET = "ZEBRA-SENTINEL-7730"
TEXT_ATTRS = {"AXValue", "AXSelectedText", "AXStringForRange",
              "AXSelectedTextRange", "AXNumberOfCharacters"}


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


class FakeAX:
    def __init__(self, bundle="com.tinyspeck.slackmacgap", secure_input=False,
                 field=None, text="", cursor=0, selection=0, window_title=None,
                 web_host=None, delay=0.0, range_supported=True):
        self.bundle, self.secure_flag = bundle, secure_input
        self.field = {"AXRole": "AXTextArea"} if field is None else field
        self.text, self.cursor, self.selection = text, cursor, selection
        self.window_title, self.web_host = window_title, web_host
        self.delay, self.range_supported = delay, range_supported
        self.reads: list[str] = []

    def secure_input(self):
        return self.secure_flag

    def focused_app(self):
        time.sleep(self.delay)
        return "app", 4242

    def app_info(self, pid):
        return self.bundle, "Some App"

    def attr(self, elem, name):
        self.reads.append(name)
        if elem == "app":
            return {"AXFocusedUIElement": "field" if self.field is not False else None,
                    "AXFocusedWindow": "window"}.get(name)
        if elem == "window":
            return self.window_title if name == "AXTitle" else None
        if elem == "webarea":
            return {"AXRole": "AXWebArea", "AXURL": self.web_host}.get(name)
        if elem == "field":
            if name == "AXParent":
                return "webarea" if self.web_host else None
            if name == "AXValue":
                return self.text
            if name == "AXNumberOfCharacters":
                return len(self.text)
            if name == "AXSelectedText":
                return self.text[self.cursor:self.cursor + self.selection]
            return self.field.get(name)
        return None

    def selected_range(self, elem):
        self.reads.append("AXSelectedTextRange")
        return self.cursor, self.selection

    def string_for_range(self, elem, loc, length):
        self.reads.append("AXStringForRange")
        if not self.range_supported:
            return None
        return self.text[loc:loc + length]

    def url_host(self, value):
        return value or ""


def capture(ax, **kw):
    return context.capture(ax, **kw)


print("=== secure fields: nothing is even requested ===")
doc = f"my password is {SECRET} and Priya said hi"
for label, ax in (
        ("Secure Event Input is on", FakeAX(secure_input=True, text=doc, cursor=10)),
        ("an AXSecureTextField role",
         FakeAX(field={"AXRole": "AXSecureTextField"}, text=doc, cursor=10)),
        ("an AXSecureTextField subrole",
         FakeAX(field={"AXRole": "AXTextField", "AXSubrole": "AXSecureTextField"},
                text=doc, cursor=10)),
        ("a field labelled Password",
         FakeAX(field={"AXRole": "AXTextField", "AXPlaceholderValue": "Password"},
                text=doc, cursor=10)),
        ("a one-time code field",
         FakeAX(field={"AXRole": "AXTextField", "AXTitle": "Enter one-time code"},
                text=doc, cursor=10)),
        ("an API key field",
         FakeAX(field={"AXRole": "AXTextField", "AXDescription": "API key"},
                text=doc, cursor=10)),
):
    ctx = capture(ax)
    touched = TEXT_ATTRS & set(ax.reads)
    check(f"{label}: no text attribute requested", not touched, sorted(touched))
    check(f"{label}: marked secure, nothing kept",
          ctx.secure and ctx.before is None and ctx.after is None and not ctx.terms
          and not ctx.selected)
    check(f"{label}: the category survives", ctx.category == "chat")

print("\n=== an ordinary field: a bounded window around the cursor ===")
body = ("x" * 900) + f" {SECRET} Priya " + ("y" * 900)
cur = 900 + len(SECRET) + 2
ax = FakeAX(text=body, cursor=cur)
ctx = capture(ax)
check("at most 300 characters before", ctx.before is not None and len(ctx.before) == 300)
check("at most 100 after", ctx.after is not None and len(ctx.after) == 100)
check("never the whole document", "AXValue" not in ax.reads)
check("names near the cursor become terms", "Priya" in ctx.terms, ctx.terms)
ax = FakeAX(text="Hi Jake, " + "z" * 20, cursor=9, selection=5)
ctx = capture(ax)
check("a selection is read", ctx.selected == "zzzzz")

ax = FakeAX(text="short chat input", cursor=5, range_supported=False)
ctx = capture(ax)
check("a small field without AXStringForRange falls back to its value",
      ctx.before == "short" and ctx.after == " chat input")
ax = FakeAX(text="w" * 6000, cursor=5000, range_supported=False)
ctx = capture(ax)
check("...but a large one is never read whole",
      "AXValue" not in ax.reads and ctx.before is None)

print("\n=== classification ===")
check("Slack is chat", capture(FakeAX()).category == "chat")
check("Terminal", capture(FakeAX(bundle="com.apple.Terminal")).category == "terminal")
check("a JetBrains IDE by prefix",
      capture(FakeAX(bundle="com.jetbrains.pycharm")).category == "ide")
ctx = capture(FakeAX(bundle="com.apple.Safari", web_host="mail.google.com"))
check("Gmail in Safari is email", ctx.category == "email" and ctx.host == "mail.google.com")
ctx = capture(FakeAX(bundle="com.apple.Safari", web_host="www.example.org"))
check("an unknown site stays a browser", ctx.category == "browser")
ctx = capture(FakeAX(bundle="org.example.editor", window_title="main.py - editor"))
check("an unknown app editing a .py file is an IDE", ctx.category == "ide")
check("a user override wins",
      context.classify("com.tinyspeck.slackmacgap", {"com.tinyspeck.slackmacgap": "email"})
      == "email")
check("a bogus override is ignored",
      context.classify("com.apple.Terminal", {"com.apple.Terminal": "banana"}) == "terminal")
ctx = capture(FakeAX(bundle="company.thebrowser.Browser", field=False))
check("Chromium with no focused element: category only",
      ctx.category == "browser" and ctx.before is None)

print("\n=== it cannot leak by accident ===")
ctx = capture(FakeAX(text=f"hello {SECRET} there", cursor=10))
check("repr is redacted", SECRET not in repr(ctx) and SECRET not in str(ctx))
check("f-strings are redacted", SECRET not in f"{ctx}")
check("the log summary is redacted", SECRET not in ctx.summary())
ctx.clear()
check("clear() drops every piece of text",
      ctx.before is None and ctx.after is None and not ctx.selected and not ctx.terms)

print("\n=== it never delays a dictation ===")
context._ax = FakeAX(text=f"slow {SECRET}", cursor=4, delay=0.5)
pending = context.capture_async()
t0 = time.time()
got = pending.get(timeout=0.05)
check("a slow capture is abandoned", got is None and time.time() - t0 < 0.2)
time.sleep(0.7)
check("...and whatever it read later is dropped", pending._ctx is None)

context._ax = FakeAX(text="fast Priya", cursor=4)
pending = context.capture_async()
got = pending.get(timeout=1.0)
check("a fast capture arrives", got is not None and got.category == "chat")
pending.discard()
check("discard() clears it", got.before is None)


class Boom(FakeAX):
    def focused_app(self):
        raise RuntimeError(f"AX exploded holding {SECRET}")


context._ax = Boom()
got = context.capture_async().get(timeout=1.0)
check("an AX exception means no context, not a crash", got is None)
check("threads are daemons (never block exit)",
      all(t.daemon for t in threading.enumerate() if t.name == "context-capture"))

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
