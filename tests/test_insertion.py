"""Safe insertion and safe undo, against a fake Accessibility layer.

The promises under test: text never lands in an app you switched to; AX
insertion is only trusted when it can be read back, so an app that ignores
the write gets exactly one copy via paste, never two; the clipboard comes
back; and "scratch that" removes Halo's own text or nothing at all.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from AppKit import NSPasteboard  # noqa: E402

import clipboard  # noqa: E402
import context  # noqa: E402
import inject  # noqa: E402
import insertion  # noqa: E402

ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


class Field:
    """A text field: value, selection, and how it treats AX writes."""

    def __init__(self, value="", cursor=None, honours=True, readable=True, settable=True):
        self.value = value
        self.sel = (len(value) if cursor is None else cursor, 0)
        self.honours, self.readable, self.settable = honours, readable, settable

    def type_in(self, text):
        loc, n = self.sel
        self.value = self.value[:loc] + text + self.value[loc + n:]
        self.sel = (loc + len(text), 0)


class FakeAX:
    def __init__(self, fields, focus=("app1", "win1", "f1"), pids=None):
        self.fields = fields
        self.focus = list(focus)
        self.pids = pids or {"app1": 101, "app2": 202}

    def focused_app(self):
        return self.focus[0], self.pids[self.focus[0]]

    def attr(self, elem, name):
        if elem in self.pids:
            return {"AXFocusedWindow": self.focus[1], "AXFocusedUIElement": self.focus[2]}.get(name)
        f = self.fields.get(elem)
        if f is None:
            return None
        if name == "AXValue":
            return f.value if f.readable else None
        if name == "AXSelectedText":
            loc, n = f.sel
            return f.value[loc:loc + n]
        return None

    def focused_element(self, app):
        return self.focus[2]

    @staticmethod
    def same(a, b):
        return a is not None and a == b

    def settable(self, elem, name):
        return self.fields[elem].settable

    def set_attr(self, elem, name, value):
        f = self.fields[elem]
        if name == "AXSelectedText" and f.honours:
            f.type_in(value)
        return True

    def selected_range(self, elem):
        return self.fields[elem].sel

    def set_selected_range(self, elem, loc, length):
        self.fields[elem].sel = (loc, length)
        return True


pb = NSPasteboard.pasteboardWithUniqueName()
KEYS = []


def fake_paste():
    KEYS.append("cmd+v")
    field = AX.fields[AX.focus[2]]
    field.type_in(clipboard.read_text(pb))


inject.accessibility_ok = lambda: True
inject.paste_keystroke = fake_paste
inject.undo_keystroke = lambda: KEYS.append("cmd+z")
TYPED = []
inject.type_text = lambda text: TYPED.append(text)


def target(bundle, elem="f1", window="win1", pid=101):
    t = context.Context(bundle_id=bundle, pid=pid, element=elem, window=window)
    return t


AX = None


def setup(field, focus=("app1", "win1", "f1")):
    global AX
    AX = FakeAX({"f1": field, "f2": Field("other field")}, focus=focus)
    KEYS.clear()
    TYPED.clear()
    return AX


print("=== the target must still be there ===")
ax = setup(Field("Hello "))
check("same app and field -> ok", insertion.verify(target("x"), ax) == "")
ax.focus = ["app2", "win9", "f2"]
check("switched app -> refused", insertion.verify(target("x"), ax) == "you switched apps")
ax.focus = ["app1", "win2", "f1"]
check("switched window -> refused", insertion.verify(target("x"), ax) == "you switched windows")
ax.focus = ["app1", "win1", "f2"]
check("another field -> refused", insertion.verify(target("x"), ax) == "the text field changed")

pb.clearContents()
pb.setString_forType_("what you had copied", clipboard.PLAIN)
ax = setup(Field("Dear team, "))
ax.focus = ["app2", "win9", "f2"]
r = insertion.insert("ship it", target("com.apple.TextEdit"), ax, pb)
check("an app switch means no insertion at all", not r.ok and r.reason == "you switched apps"
      and ax.fields["f2"].value == "other field" and not KEYS)
check("...and the clipboard is untouched", clipboard.read_text(pb) == "what you had copied")

print("\n=== the method depends on the app ===")
ax = setup(Field("Dear team, "))
r = insertion.insert("ship it", target("com.apple.TextEdit"), ax, pb)
check("TextEdit: AX, verified", r.ok and r.method == "ax" and ax.fields["f1"].value == "Dear team, ship it")
check("...with the range recorded", r.range == (11, 7), r.range)
check("...and no keystroke at all", not KEYS)

ax = setup(Field("abc"))
r = insertion.insert("def", target("org.example.unknown"), ax, pb)
check("an unknown app that can be read back: AX", r.ok and r.method == "ax" and ax.fields["f1"].value == "abcdef")

ax = setup(Field("abc", honours=False))
r = insertion.insert("def", target("org.example.electron"), ax, pb)
check("reports success but ignores the write -> ONE copy via paste",
      r.ok and r.method == "paste" and ax.fields["f1"].value == "abcdef", ax.fields["f1"].value)

ax = setup(Field("abc", readable=False, honours=True))
r = insertion.insert("def", target("org.example.opaque"), ax, pb)
check("cannot be read back -> AX not even tried, paste instead",
      r.ok and r.method == "paste" and ax.fields["f1"].value == "abcdef", ax.fields["f1"].value)

pb.clearContents()
pb.setString_forType_("your clipboard", clipboard.PLAIN)
ax = setup(Field("> "))
r = insertion.insert("git status", target("com.apple.Terminal"), ax, pb)
check("Terminal: paste", r.ok and r.method == "paste" and ax.fields["f1"].value == "> git status")
check("...and your clipboard is back afterwards", clipboard.read_text(pb) == "your clipboard")

ax = setup(Field(""))
r = insertion.insert("remote text", target("com.microsoft.rdc.macos"), ax, pb)
check("Remote Desktop: typed, never the local clipboard", r.ok and r.method == "type"
      and TYPED == ["remote text"] and not KEYS)

ax = setup(Field(""))
t = target("org.example.unknown")
t.secure = True
r = insertion.insert("hunter2", t, ax, pb)
check("a secure field is never written through AX", r.ok and r.method == "paste")

print("\n=== scratch that ===")
ax = setup(Field("Notes: "))
t = target("com.apple.TextEdit")
r = insertion.insert("buy milk", t, ax, pb)
rec = insertion.Record("buy milk", r.method, 101, "com.apple.TextEdit", "f1", "win1", r.range)
u = insertion.undo(rec, ax)
check("AX undo removes exactly Halo's text", u.ok and ax.fields["f1"].value == "Notes: ", ax.fields["f1"].value)

ax = setup(Field("Notes: "))
r = insertion.insert("buy milk", t, ax, pb)
ax.fields["f1"].value = "Hi. Notes: buy milk"          # you typed before it
rec = insertion.Record("buy milk", r.method, 101, "com.apple.TextEdit", "f1", "win1", r.range)
u = insertion.undo(rec, ax)
check("text that moved but is unique is still found", u.ok and ax.fields["f1"].value == "Hi. Notes: ")

ax = setup(Field("Notes: "))
r = insertion.insert("milk", t, ax, pb)
ax.fields["f1"].value = "milk, more milk"
rec = insertion.Record("milk", r.method, 101, "com.apple.TextEdit", "f1", "win1", r.range)
u = insertion.undo(rec, ax)
check("ambiguous copies -> refuse rather than guess", not u.ok and ax.fields["f1"].value == "milk, more milk")

ax = setup(Field("chat: ", readable=False))
rec = insertion.Record("hello", "paste", 101, "com.tinyspeck.slackmacgap", "f1", "win1", None)
u = insertion.undo(rec, ax)
check("a paste nothing has followed: Cmd+Z", u.ok and KEYS == ["cmd+z"])
rec.keys_since = 3
KEYS.clear()
u = insertion.undo(rec, ax)
check("...but not after you have typed", not u.ok and u.reason == "you have typed since" and not KEYS)

rec = insertion.Record("hello", "paste", 101, "x", "f1", "win1", None)
ax.focus = ["app2", "win9", "f2"]
KEYS.clear()
u = insertion.undo(rec, ax)
check("never into another app", not u.ok and u.reason == "you switched apps" and not KEYS)

rec = insertion.Record("hello", "paste", 101, "x", "f1", "win1", None, at=0)
ax.focus = ["app1", "win1", "f1"]
check("nor after five minutes", not insertion.undo(rec, ax).ok)

print("\n=== transforms replace only the selection they read ===")
f = Field("make this shorter please")
f.sel = (0, 24)
ax = setup(f)
t = target("com.apple.TextEdit")
r = insertion.replace_selection("shorter", "make this shorter please", t, ax, pb)
check("selection unchanged -> replaced", r.ok and ax.fields["f1"].value == "shorter")
f = Field("something else entirely")
f.sel = (0, 5)
ax = setup(f)
r = insertion.replace_selection("x", "make this shorter please", t, ax, pb)
check("selection changed -> left alone", not r.ok and ax.fields["f1"].value == "something else entirely")
rec = insertion.Record("shorter", "ax", 101, "com.apple.TextEdit", "f1", "win1", (0, 7),
                       original="make this shorter please")
ax = setup(Field("shorter"))
u = insertion.undo(rec, ax)
check("undo of a transform restores the original",
      u.ok and ax.fields["f1"].value == "make this shorter please")

pb.releaseGlobally()
print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
