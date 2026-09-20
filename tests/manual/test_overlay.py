"""STEP 3 TEST: Python -> Swift overlay over the Unix socket.

Exercises auto-launch, all three states with simulated mic levels, and the
graceful-degradation path when the overlay is unavailable.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import math
import random
import time

import overlay as overlay_mod

print("=== 1. auto-launch + connect ===")
ui = overlay_mod.Overlay()
ok = ui.start_app()
print(f"  start_app() -> {ok}")
if not ok:
    print("  FAILED: could not launch or connect. Is overlay/build_app.sh run?")
    raise SystemExit(1)

print("\n=== 2. LISTENING with simulated speech (5s) ===")
ui.listening()
t0 = time.time()
while time.time() - t0 < 5:
    t = time.time() - t0
    env = abs(0.5 + 0.42 * math.sin(t * 1.7) * math.sin(t * 0.6 + 1))
    ui.level(max(0.03, min(1.0, env * (0.55 + random.random() * 0.5))))
    time.sleep(1 / 60)          # deliberately faster than the 30fps throttle

print("=== 3. PROCESSING (4s) ===")
ui.processing()
time.sleep(4)

print("=== 4. DONE (auto-dismiss) ===")
ui.done()
time.sleep(2.5)

print("\n=== 5. graceful degradation ===")
bad = overlay_mod.Overlay()
bad.path = "/tmp/definitely-not-a-real-overlay.sock"
t = time.time()
bad.listening(); bad.level(0.5); bad.processing(); bad.done(); bad.hide()
print(f"  all calls against a missing socket: no exception, {time.time()-t:.3f}s")

null = overlay_mod.NullOverlay()
null.listening(); null.level(0.5); null.processing(); null.done(); null.close()
print("  NullOverlay: no-ops fine")

ui.close()
print("\nAll overlay tests passed.")
