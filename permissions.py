"""macOS TCC permission checks for Accessibility + Input Monitoring.

Critical macOS detail: when you launch Python from a terminal, macOS does NOT
attribute these permissions to the python binary. It attributes them to the
*responsible process* -- the app that owns the session (Terminal, iTerm2,
Ghostty, VS Code, ...). That is the app you must tick in System Settings.
"""
import ctypes
import os
import subprocess
import sys

_AX_FRAMEWORK = (
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
_IOKIT_FRAMEWORK = "/System/Library/Frameworks/IOKit.framework/IOKit"

# IOHIDRequestType
_kIOHIDRequestTypePostEvent = 0    # -> Accessibility-ish (synthetic events)
_kIOHIDRequestTypeListenEvent = 1  # -> Input Monitoring
# IOHIDAccessType
GRANTED, DENIED, UNKNOWN = 0, 1, 2


def _load(path):
    try:
        return ctypes.cdll.LoadLibrary(path)
    except OSError:
        return None


def accessibility_ok() -> bool:
    """True if this process may post synthetic keystrokes (Cmd+V)."""
    lib = _load(_AX_FRAMEWORK)
    if lib is None:
        return False
    try:
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except AttributeError:
        return False


def input_monitoring_state() -> int:
    """GRANTED / DENIED / UNKNOWN for global key *listening*."""
    lib = _load(_IOKIT_FRAMEWORK)
    if lib is None:
        return UNKNOWN
    try:
        lib.IOHIDCheckAccess.restype = ctypes.c_int
        lib.IOHIDCheckAccess.argtypes = [ctypes.c_uint32]
        return int(lib.IOHIDCheckAccess(_kIOHIDRequestTypeListenEvent))
    except AttributeError:
        return UNKNOWN


def request_input_monitoring() -> bool:
    """Ask macOS to show the Input Monitoring prompt. Returns True if granted."""
    lib = _load(_IOKIT_FRAMEWORK)
    if lib is None:
        return False
    try:
        lib.IOHIDRequestAccess.restype = ctypes.c_bool
        lib.IOHIDRequestAccess.argtypes = [ctypes.c_uint32]
        return bool(lib.IOHIDRequestAccess(_kIOHIDRequestTypeListenEvent))
    except AttributeError:
        return False


def request_accessibility() -> bool:
    """Show the Accessibility prompt (with the 'Open System Settings' button)."""
    lib = _load(_AX_FRAMEWORK)
    if lib is None:
        return False
    try:
        cf = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32
        ]
        cf.CFDictionaryCreate.restype = ctypes.c_void_p
        cf.CFDictionaryCreate.argtypes = [ctypes.c_void_p] + [ctypes.c_void_p] * 2 + [
            ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p
        ]
        key = ctypes.c_void_p(
            cf.CFStringCreateWithCString(None, b"AXTrustedCheckOptionPrompt", 0x08000100)
        )
        true_val = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
        keys = (ctypes.c_void_p * 1)(key)
        vals = (ctypes.c_void_p * 1)(true_val)
        opts = cf.CFDictionaryCreate(None, keys, vals, 1, None, None)
        lib.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
        lib.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
        return bool(lib.AXIsProcessTrustedWithOptions(ctypes.c_void_p(opts)))
    except Exception:
        return accessibility_ok()


def responsible_app() -> tuple[str, str]:
    """(display_name, full_path) of the .app macOS attributes permissions to.

    Walks the process ancestry and takes the OUTERMOST .app bundle, skipping
    Python's own embedded Python.app (framework builds run from inside one,
    which is never the responsible process) and nested helper bundles.
    """
    candidates = []
    try:
        pid = os.getpid()
        for _ in range(15):
            out = subprocess.run(
                ["ps", "-o", "ppid=,comm=", "-p", str(pid)],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip()
            if not out:
                break
            ppid_s, _, comm = out.partition(" ")
            comm = comm.strip()
            if ".app/Contents/MacOS/" in comm and ".framework/" not in comm:
                candidates.append(comm.split(".app/Contents/MacOS/")[0] + ".app")
            try:
                pid = int(ppid_s)
            except ValueError:
                break
            if pid <= 1:
                break
    except Exception:
        pass

    if not candidates:
        return "your terminal app", ""
    # Outermost bundle = last one found walking toward launchd.
    path = candidates[-1]
    return os.path.basename(path), path


_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_"


def open_settings(pane: str):
    subprocess.run(["open", _PANE + pane], check=False)


def report(require: bool = True) -> bool:
    """Print a permission report. Returns True if the REQUIRED grant is present.

    Accessibility is the hard requirement: pynput's global key listener calls
    AXIsProcessTrusted() before creating its CGEventTap, so without it the
    hotkey only fires while your terminal is focused AND Cmd+V is swallowed.
    Input Monitoring is advisory -- macOS lists key-tapping apps there too, but
    it is not what gates pynput.
    """
    app, app_path = responsible_app()
    ax = accessibility_ok()
    im = input_monitoring_state()

    print("=" * 66)
    print(" macOS permission check")
    print("=" * 66)
    print(f" Running as : {os.path.realpath(sys.executable)}")
    print(f" Grant to   : {app}   <-- tick THIS, not 'python'")
    if app_path:
        print(f" App path   : {app_path}")
    print("-" * 66)
    print(f" Accessibility     [REQUIRED] : {'OK' if ax else 'NOT GRANTED'}")
    print("     gates BOTH the global hotkey listener AND Cmd+V injection")
    print(f" Input Monitoring  [advisory] : "
          f"{'OK' if im == GRANTED else 'denied' if im == DENIED else 'not granted'}")
    print("     not what pynput checks; grant it too if macOS offers")
    print("=" * 66)

    if ax:
        print(" Accessibility granted -- hotkey and injection will work.\n")
        return True

    print()
    print(" WITHOUT ACCESSIBILITY YOU GET EXACTLY THIS:")
    print("   - the hotkey only fires while the terminal is focused")
    print("   - Cmd+V is silently swallowed, no error, no text")
    print()
    print(" FIX")
    print("   1. System Settings > Privacy & Security > Accessibility")
    print(f"   2. Enable: {app}")
    if app_path:
        print(f"      (if missing: '+', then Cmd+Shift+G, paste {app_path})")
    print(f"   3. Fully QUIT {app} with Cmd+Q -- closing the window is NOT enough --")
    print("      then reopen it and rerun. macOS only re-reads this grant on restart.")
    print()

    if require:
        print(" Opening System Settings...")
        request_accessibility()
        open_settings("Accessibility")
    return False
