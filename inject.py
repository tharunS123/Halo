"""Keystrokes into the focused app: Cmd+V, Cmd+Z, and typed Unicode.

The policy -- which method, into which target, and whether to at all -- is
insertion.py's. This module only presses keys, and refuses loudly when
Accessibility is missing, because that is the failure mode where macOS
swallows synthetic events and nothing at all happens.
"""
import time

import permissions


class InjectionError(RuntimeError):
    pass


def accessibility_ok() -> bool:
    return permissions.accessibility_ok()


def _require_accessibility():
    if not permissions.accessibility_ok():
        app, path = permissions.responsible_app()
        raise InjectionError(
            "Accessibility permission is NOT granted.\n"
            "  Synthetic keystrokes will be silently swallowed by macOS.\n"
            f"  Grant it to: {app}" + (f"  ({path})" if path else "") + "\n"
            "  System Settings > Privacy & Security > Accessibility\n"
            f"  Then fully quit and reopen {app} (Cmd+Q)."
        )


# Virtual key codes (US layout positions; the Cmd shortcuts follow the key,
# which is what apps expect).
_KEY_V, _KEY_Z = 9, 6


def _command_key(keycode: int) -> None:
    _require_accessibility()
    try:
        import Quartz
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        for down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(src, keycode, down)
            Quartz.CGEventSetFlags(ev, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            time.sleep(0.01)
    except Exception as e:
        raise InjectionError(f"could not send a keystroke: {type(e).__name__}") from e


def paste_keystroke() -> None:
    _command_key(_KEY_V)


def undo_keystroke() -> None:
    _command_key(_KEY_Z)


def type_text(text: str, chunk: int = 16) -> None:
    """Type `text` as Unicode key events, no clipboard involved. Slower than a
    paste (~2ms per chunk), and used only where a paste would go elsewhere."""
    _require_accessibility()
    try:
        import Quartz
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        for i in range(0, len(text), chunk):
            piece = text[i:i + chunk]
            for down in (True, False):
                ev = Quartz.CGEventCreateKeyboardEvent(src, 0, down)
                Quartz.CGEventKeyboardSetUnicodeString(ev, len(piece), piece)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
            time.sleep(0.002)
    except Exception as e:
        raise InjectionError(f"could not type the text: {type(e).__name__}") from e


def copy_only(text: str) -> None:
    """Fallback: leave text on the clipboard for the user to paste."""
    import clipboard
    clipboard.put_text_for_user(text)


# --- kept for tests/manual/test_inject.py and anything scripting Halo -------

def inject(text: str, restore_clipboard: bool = True) -> None:
    """Paste `text` into whatever has focus. Prefer insertion.insert()."""
    if not text:
        raise InjectionError("nothing to inject (empty text)")
    import insertion
    r = insertion.insert(text, None)
    if not r.ok:
        raise InjectionError(r.reason)


def undo() -> None:
    undo_keystroke()
