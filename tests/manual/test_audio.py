"""STEP 1 TEST: record 4 seconds from the mic and report what was captured."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import time
from audio import Recorder
import sounddevice as sd

print("=== Input devices ===")
for i, d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0:
        mark = " <- DEFAULT" if i == sd.default.device[0] else ""
        print(f"  [{i}] {d['name']} ({d['max_input_channels']}ch){mark}")

r = Recorder()
print("\n[recording] Speak now for 4 seconds...")
r.start()
for s in range(4, 0, -1):
    print(f"  {s}...", flush=True)
    time.sleep(1)
path, dur = r.stop()

if path is None:
    print("\nFAILED: no audio captured. Check Microphone permission.")
else:
    peak = Recorder.peak_level(path)
    print(f"\n[ok] wrote {path}")
    print(f"     duration : {dur:.2f}s")
    print(f"     peak level: {peak:.3f}")
    if peak < 0.01:
        print("     WARNING: near-silent. Wrong input device, or mic muted?")
    else:
        print("     Mic is working.")
    print(f"\nPlay it back to confirm:\n  afplay {path}")
