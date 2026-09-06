#!/bin/bash
# Visual demo of the overlay states.
BIN="$(dirname "$0")/WisprFlow.app/Contents/MacOS/WisprFlow"
FIFO="/tmp/flowoverlay-demo.fifo"
rm -f "$FIFO"; mkfifo "$FIFO"
"$BIN" < "$FIFO" 2>/dev/null &
exec 3>"$FIFO"
cleanup() { echo quit >&3 2>/dev/null; exec 3>&-; rm -f "$FIFO"; }
trap cleanup EXIT

echo "Look at the BOTTOM CENTER of the screen your mouse is on."
sleep 1.5

echo "-> LISTENING (bars from a simulated voice)"
echo listening >&3
# simulate ~5s of speech-like level variation
python3 - >&3 <<'PY'
import math, random, sys, time
for step in range(150):
    t = step / 30
    env = 0.5 + 0.42 * math.sin(t * 1.7) * math.sin(t * 0.6 + 1)
    v = max(0.03, min(1.0, abs(env) * (0.55 + random.random() * 0.5)))
    print(f"level {v:.3f}", flush=True)
    time.sleep(1/30)
PY

echo "-> PROCESSING (sweeping pulse, morphs out of the waveform)"
echo processing >&3
sleep 5

echo "-> DONE (checkmark springs in, auto-dismisses)"
echo done >&3
sleep 3
echo "Demo finished."
