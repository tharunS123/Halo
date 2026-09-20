"""STEP 4a: find out what your function keys actually emit.

Press F9, then F13, then Esc to quit. Prints the raw key object pynput sees,
so we can pick a hotkey that works with YOUR 'use F1-F12 as standard function
keys' setting.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import permissions
from pynput import keyboard

if not permissions.accessibility_ok():
    print("WARNING: Accessibility is not granted.")
    print("Events will ONLY arrive while this terminal is focused,")
    print("which makes this probe useless for testing a GLOBAL hotkey.\n")
    permissions.report(require=False)
    print("\nContinuing anyway so you can at least see key names...\n")

print("Press F9, then F13. Press Esc to finish.")
print("(If nothing prints at all, Input Monitoring is the problem.)\n")

seen = []


def on_press(key):
    name = getattr(key, "name", None) or getattr(key, "char", None) or str(key)
    vk = getattr(key, "vk", None)
    print(f"  press   -> {key!r:<28} name={name!r:<10} vk={vk}")
    seen.append(name)
    if key == keyboard.Key.esc:
        return False


def on_release(key):
    name = getattr(key, "name", None) or getattr(key, "char", None) or str(key)
    print(f"  release -> {name!r}")


with keyboard.Listener(on_press=on_press, on_release=on_release) as ln:
    ln.join()

print("\n=== summary ===")
print("keys seen:", sorted(set(seen)))
for want in ("f9", "f13"):
    print(f"  {want}: {'USABLE' if want in seen else 'not detected'}")
