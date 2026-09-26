"""Clipboard preservation: everything you had copied comes back, not just
the plain text. Runs on a private, uniquely named pasteboard -- never the
real one -- so it is safe on a developer's machine and in CI.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from AppKit import NSPasteboard, NSPasteboardItem  # noqa: E402
from Foundation import NSData  # noqa: E402

import clipboard  # noqa: E402

ok = True


def check(label, good, detail=""):
    global ok
    ok &= bool(good)
    print(f"  [{'PASS' if good else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not good else ""))


pb = NSPasteboard.pasteboardWithUniqueName()

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                    "0000000d4944415478da63f8ffff3f0005fe02fea7d6a9f20000000049454e44ae426082")
RTF = b"{\\rtf1\\ansi {\\b bold} text}"
HTML = b"<p><b>bold</b> text</p>"
FILE_URL = b"file:///Users/someone/Desktop/report.pdf"
CUSTOM = b"\x00\x01private-app-data\xff"


def write(items):
    pb.clearContents()
    objs = []
    for entry in items:
        it = NSPasteboardItem.alloc().init()
        for t, data in entry:
            it.setData_forType_(NSData.dataWithBytes_length_(data, len(data)), t)
        objs.append(it)
    pb.writeObjects_(objs)


print("=== every type on every item survives ===")
original = [
    [("public.utf8-plain-text", b"bold text"), ("public.rtf", RTF), ("public.html", HTML)],
    [("public.png", PNG)],
    [("public.file-url", FILE_URL), ("public.url", b"https://example.com/a")],
    [("com.example.private", CUSTOM)],
]
write(original)
snap = clipboard.snapshot(pb)
check("snapshot saw 4 items", len(snap.items) == 4, len(snap.items))
changed = clipboard.put_text("dictated words", pb)
check("the paste text is on the pasteboard", clipboard.read_text(pb) == "dictated words")
types = [str(t) for t in pb.pasteboardItems()[0].types()]
check("...marked transient and concealed for clipboard managers",
      clipboard.TRANSIENT in types and clipboard.CONCEALED in types, types)
check("restored", clipboard.restore(snap, pb, expected_change=changed))
after = clipboard.snapshot(pb)
check("the same number of items", len(after.items) == len(original), len(after.items))
for i, (want, got) in enumerate(zip(original, after.items, strict=False)):
    got_map = dict(got)
    for t, data in want:
        check(f"item {i}: {t} is byte-identical", got_map.get(t) == data)

print("\n=== plain text alone ===")
write([[("public.utf8-plain-text", "héllo — ünïcode ✓".encode())]])
snap = clipboard.snapshot(pb)
c = clipboard.put_text("x", pb)
clipboard.restore(snap, pb, expected_change=c)
check("unicode text round-trips", clipboard.read_text(pb) == "héllo — ünïcode ✓")

print("\n=== an empty clipboard stays empty ===")
pb.clearContents()
snap = clipboard.snapshot(pb)
check("snapshot is empty", snap.empty)
c = clipboard.put_text("x", pb)
clipboard.restore(snap, pb, expected_change=c)
check("nothing is left behind", not (pb.pasteboardItems() or []))

print("\n=== a newer copy is never overwritten ===")
write([[("public.utf8-plain-text", b"what you had before")]])
snap = clipboard.snapshot(pb)
c = clipboard.put_text("dictated", pb)
pb.clearContents()
pb.setString_forType_("you copied this meanwhile", clipboard.PLAIN)
check("restore declines", clipboard.restore(snap, pb, expected_change=c) is False)
check("your newer copy is still there", clipboard.read_text(pb) == "you copied this meanwhile")

print("\n=== the recovery path is not transient ===")
clipboard.put_text_for_user("recovered dictation", pb)
types = [str(t) for t in pb.pasteboardItems()[0].types()]
check("text left for the user is a normal copy", clipboard.TRANSIENT not in types, types)

pb.releaseGlobally()
print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)
