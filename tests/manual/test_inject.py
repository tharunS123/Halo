"""STEP 4b TEST: text injection. Focus another app within 5 seconds."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import time
import inject, permissions

TEXT = "Halo injection test OK."

print("Accessibility:", "GRANTED" if permissions.accessibility_ok() else "NOT GRANTED")
print(f"\nClick into TextEdit / Notes / a browser field NOW.")
for s in range(5, 0, -1):
    print(f"  injecting in {s}...", flush=True)
    time.sleep(1)

try:
    inject.inject(TEXT)
    print(f"\n[ok] Sent. You should see: {TEXT!r}")
    print("     If nothing appeared, Accessibility is granted to the wrong app.")
except inject.InjectionError as e:
    print(f"\n[FAILED]\n{e}")
    inject.copy_only(TEXT)
    print("\nText was left on your clipboard as a fallback.")
