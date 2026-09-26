"""Putting text where it was meant to go -- and only there.

Halo used to paste into whatever had focus when the text was ready. If you
dictated into Slack and switched to Mail while whisper worked, your Slack
message landed in Mail. Now:

  1. The target is captured at key-down: app (pid, bundle id), window,
     focused element, selection range (context.capture).
  2. Before inserting, it is verified: same process, and -- where the app
     publishes them -- same window and same focused element. If not, Halo
     does NOT insert. The text goes on the clipboard, the orb says so, and
     it is in History if that is on.
  3. The safest method that works in that app, in order:
       ax     set AXSelectedText on the focused element, then read the
              field back to confirm the text actually landed
       paste  the clipboard, with every type you had copied saved and put
              back (clipboard.py)
       type   synthetic key events carrying the text itself, for apps where
              paste goes somewhere else (remote desktops, VMs)
     AX is only tried where the result can be verified or the app is known
     to honour it. An app that reports success and ignores the write would
     otherwise tempt a fallback paste -- and a second copy of your text.

Every insertion is remembered, in memory only, for "scratch that" (undo())
and for spotting corrections (learning.py): target, text, range, time, and
how many keys you have pressed since.
"""
import time
from dataclasses import dataclass, field

import clipboard
import config
import inject

# How each app takes text. Anything not listed is "auto": AX when the field
# can be read back to verify, otherwise paste.
COMPAT = {
    # Cocoa text system: AXSelectedText is honoured and verifiable.
    "com.apple.TextEdit": "ax", "com.apple.Notes": "ax", "com.apple.mail": "ax",
    "com.apple.dt.Xcode": "ax", "com.apple.Stickies": "ax",
    "com.apple.iWork.Pages": "paste", "com.apple.iWork.Keynote": "paste",
    # Terminals: the AX text area is the scrollback, not the input line.
    "com.apple.Terminal": "paste", "com.googlecode.iterm2": "paste",
    "com.mitchellh.ghostty": "paste", "dev.warp.Warp-Stable": "paste",
    "net.kovidgoyal.kitty": "paste", "io.alacritty": "paste",
    "com.github.wez.wezterm": "paste",
    # Chromium, Electron and friends accept AX writes inconsistently.
    "com.google.Chrome": "paste", "company.thebrowser.Browser": "paste",
    "com.brave.Browser": "paste", "com.microsoft.edgemac": "paste",
    "org.mozilla.firefox": "paste", "com.microsoft.VSCode": "paste",
    "com.todesktop.230313mzl4w4u92": "paste", "com.tinyspeck.slackmacgap": "paste",
    "com.hnc.Discord": "paste", "notion.id": "paste", "md.obsidian": "paste",
    "com.exafunction.windsurf": "paste", "net.whatsapp.WhatsApp": "paste",
    "com.microsoft.teams2": "paste", "com.microsoft.Word": "paste",
    # Paste would go to THIS Mac's clipboard, not the remote one.
    "com.microsoft.rdc.macos": "type", "com.vmware.fusion": "type",
    "com.parallels.desktop.console": "type", "com.realvnc.vncviewer": "type",
    "com.apple.ScreenSharing": "type",
}


@dataclass
class Result:
    ok: bool
    method: str = ""
    reason: str = ""              # why not, for the orb and History
    range: tuple | None = None    # (location, length) of the inserted text


@dataclass
class Record:
    """One thing Halo typed, kept in memory for undo and learning."""
    text: str
    method: str
    pid: int | None
    bundle_id: str
    element: object
    window: object
    range: tuple | None
    at: float = field(default_factory=time.time)
    keys_since: int = 0
    original: str | None = None   # what a transform replaced, for undo
    secure: bool = False


class TargetChanged(Exception):
    pass


def _ax():
    import context
    return context._backend()


def method_for(bundle_id: str) -> str:
    if config.INSERTION_METHOD != "auto":
        return config.INSERTION_METHOD
    return config.INSERTION_APP_OVERRIDES.get(bundle_id) or COMPAT.get(bundle_id, "auto")


def verify(target, ax=None) -> str:
    """"" if `target` is still where input goes, else why not."""
    if target is None or target.pid is None:
        return ""                     # nothing captured: nothing to compare
    ax = ax or _ax()
    found = ax.focused_app()
    if not found:
        return "no app has focus"
    app, pid = found
    if pid != target.pid:
        return "you switched apps"
    if target.window is not None:
        window = ax.attr(app, "AXFocusedWindow")
        if window is not None and not ax.same(window, target.window):
            return "you switched windows"
    if target.element is not None:
        elem = ax.focused_element(app)
        if elem is not None and not ax.same(elem, target.element):
            return "the text field changed"
    return ""


def _value(ax, elem) -> str | None:
    v = ax.attr(elem, "AXValue")
    return v if isinstance(v, str) and len(v) <= 500_000 else None


def _insert_ax(ax, elem, text: str, trusted: bool) -> Result | None:
    """AXSelectedText. None means "not possible here, try the next method"
    and is only returned when nothing can have been written."""
    if elem is None or not ax.settable(elem, "AXSelectedText"):
        return None
    before = _value(ax, elem)
    rng = ax.selected_range(elem)
    if before is None and not trusted:
        return None                    # cannot verify; do not risk a double
    if not ax.set_attr(elem, "AXSelectedText", text):
        return None
    if before is None or rng is None:
        return Result(True, "ax", range=(rng[0], len(text)) if rng else None)
    loc, sel = rng
    after = _value(ax, elem)
    if after is not None and after[loc:loc + len(text)] == text and \
            len(after) == len(before) - sel + len(text):
        return Result(True, "ax", range=(loc, len(text)))
    if after == before:
        # Reported success, changed nothing: safe to fall back.
        return None
    # Something changed but not what we expected. Do not add a second copy.
    return Result(True, "ax", range=None)


def _insert_paste(text: str, pb=None) -> Result:
    snap = clipboard.snapshot(pb)
    ours = clipboard.put_text(text, pb)
    time.sleep(0.05)                   # let the pasteboard settle
    try:
        inject.paste_keystroke()
    except inject.InjectionError as e:
        clipboard.restore(snap, pb, expected_change=ours)
        return Result(False, "paste", str(e))
    time.sleep(0.2)                    # the app reads the pasteboard now
    clipboard.restore(snap, pb, expected_change=ours)
    return Result(True, "paste")


def insert(text: str, target=None, ax=None, pb=None) -> Result:
    """Insert `text` into `target` (a context.Context from key-down), or
    into whatever has focus when there is no target. Never raises."""
    if not text:
        return Result(False, reason="nothing to insert")
    if not inject.accessibility_ok():
        return Result(False, reason="Accessibility is off")
    ax_ = None
    try:
        ax_ = ax or _ax()
        why = verify(target, ax_)
    except Exception:
        why = ""                       # AX unavailable: fall back to focus
    if why:
        return Result(False, reason=why)

    bundle = getattr(target, "bundle_id", "") or ""
    method = method_for(bundle)
    elem = getattr(target, "element", None)
    rng_before = None
    if ax_ is not None and elem is not None:
        try:
            rng_before = ax_.selected_range(elem)
        except Exception:
            rng_before = None

    if method in ("ax", "auto") and ax_ is not None and not getattr(target, "secure", False):
        try:
            r = _insert_ax(ax_, elem, text, trusted=(method == "ax"))
        except Exception:
            r = None
        if r is not None:
            return r
    if method == "type":
        try:
            inject.type_text(text)
            return Result(True, "type", range=(rng_before[0], len(text)) if rng_before else None)
        except inject.InjectionError as e:
            return Result(False, "type", str(e))
    r = _insert_paste(text, pb)
    if r.ok and rng_before:
        r.range = (rng_before[0], len(text))
    return r


# --- undo -------------------------------------------------------------------

def undo(rec: Record, ax=None, max_age: float = 300) -> Result:
    """Remove what Halo inserted in `rec` -- only if that is provably still
    what is there. Returns why not, otherwise.

    Order of preference:
      1. AX: the recorded range still holds exactly the inserted text ->
         select it and replace it with what was there before ("" normally,
         the original for a transform).
      2. Cmd+Z: same app and field, you have not typed since, and it was a
         paste -- so the app's own last undo step is Halo's.
      3. Refuse. Undoing something that is not ours is worse than doing
         nothing: it eats your own work.
    """
    if rec is None:
        return Result(False, reason="nothing to undo")
    if time.time() - rec.at > max_age:
        return Result(False, reason="that was too long ago")
    ax = ax or _ax()
    why = verify(rec, ax)
    if why:
        return Result(False, reason=why)
    replacement = rec.original or ""
    elem = rec.element
    if elem is not None and rec.range is not None:
        value = _value(ax, elem)
        if value is not None:
            loc, length = rec.range
            if value[loc:loc + length] != rec.text:
                # Edited or moved. Accept it only if the text is still there,
                # exactly once, so there is no doubt which copy is ours.
                if value.count(rec.text) != 1:
                    return Result(False, reason="the text has changed since")
                loc = value.index(rec.text)
            if ax.set_selected_range(elem, loc, len(rec.text)) and \
                    ax.set_attr(elem, "AXSelectedText", replacement):
                after = _value(ax, elem)
                if after is not None and after[loc:loc + len(replacement)] == replacement:
                    return Result(True, "ax", range=(loc, len(replacement)))
    if rec.keys_since == 0 and rec.method == "paste" and not rec.original:
        try:
            inject.undo_keystroke()
            return Result(True, "undo")
        except inject.InjectionError as e:
            return Result(False, reason=str(e))
    if rec.keys_since:
        return Result(False, reason="you have typed since")
    return Result(False, reason="this app cannot undo it safely")


def replace_selection(text: str, original: str, target, ax=None, pb=None) -> Result:
    """Transforms: swap the selected `original` for `text`, but only if the
    selection is still exactly `original` -- the source must not have moved
    under a transform that took a second to run."""
    ax = ax or _ax()
    why = verify(target, ax)
    if why:
        return Result(False, reason=why)
    elem = getattr(target, "element", None)
    if elem is not None:
        current = ax.attr(elem, "AXSelectedText")
        if current is not None and str(current) != original:
            return Result(False, reason="the selection changed")
    return insert(text, target, ax, pb)
