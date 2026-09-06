"""Inject text into the frontmost app via clipboard + synthetic Cmd+V."""
import time

import pyperclip
from pynput.keyboard import Controller, Key

import permissions


class InjectionError(RuntimeError):
    pass


_kb = Controller()


def inject(text: str, restore_clipboard: bool = True) -> None:
    """Paste `text` into whatever currently has keyboard focus.

    Raises InjectionError (never silently no-ops) if Accessibility is missing,
    which is the failure mode that produces no error and no text on macOS.
    """
    if not text:
        raise InjectionError("nothing to inject (empty text)")

    if not permissions.accessibility_ok():
        app, path = permissions.responsible_app()
        raise InjectionError(
            "Accessibility permission is NOT granted.\n"
            "  Synthetic Cmd+V will be silently swallowed by macOS.\n"
            f"  Grant it to: {app}" + (f"  ({path})" if path else "") + "\n"
            "  System Settings > Privacy & Security > Accessibility\n"
            f"  Then fully quit and reopen {app} (Cmd+Q)."
        )

    previous = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None

    pyperclip.copy(text)
    # Give the pasteboard a moment to settle before the paste keystroke.
    time.sleep(0.06)

    try:
        with _kb.pressed(Key.cmd):
            _kb.press("v")
            _kb.release("v")
    except Exception as e:
        raise InjectionError(f"failed to send Cmd+V: {e}") from e

    # Let the target app consume the paste before we touch the clipboard again.
    time.sleep(0.18)

    if restore_clipboard and previous is not None:
        try:
            pyperclip.copy(previous)
        except Exception:
            pass


def undo() -> None:
    """Send Cmd+Z to the focused app -- undoes our last paste."""
    if not permissions.accessibility_ok():
        raise InjectionError("Accessibility permission is NOT granted; "
                             "cannot send Cmd+Z.")
    try:
        with _kb.pressed(Key.cmd):
            _kb.press("z")
            _kb.release("z")
    except Exception as e:
        raise InjectionError(f"failed to send Cmd+Z: {e}") from e


def copy_only(text: str) -> None:
    """Fallback when Accessibility is unavailable: leave text on the clipboard."""
    pyperclip.copy(text)
