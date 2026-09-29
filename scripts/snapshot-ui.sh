#!/usr/bin/env bash
# Native screenshots of the Settings panes and the setup guide, in light and
# dark, at the default and the minimum window size.
#
#   scripts/snapshot-ui.sh [out-dir] [pane ...]
#
# Runs the freshly built overlay/Halo.app as a second, isolated instance --
# its own config, data and sockets in a temp dir, no engine, no microphone --
# so the Halo you use is left alone. The windows are captured with
# `screencapture -l`, which needs Screen Recording for the terminal running
# this script. Development only: it relies on HALO_DEV_COMMANDS.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT="${1:-snapshots}"
shift || true
PANES=("$@")
[ ${#PANES[@]} -gt 0 ] || PANES=(general dictation microphone intelligence styles dictionary
                                 commands models history privacy permissions advanced)
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"

# HALO_APP runs another build -- e.g. a bare `swift build` binary, which finds
# the fonts and brand art in overlay/Resources through its source path.
APP="${HALO_APP:-overlay/Halo.app/Contents/MacOS/Halo}"
[ -x "$APP" ] || { echo "build first: overlay/build_app.sh" >&2; exit 1; }

# Short paths: a Unix socket path must fit in 104 bytes.
T="$(mktemp -d)"
mkdir -p "$T/config" "$T/data" "$T/logs"
cp defaults/*.json "$T/config/"
export HALO_CONFIG_DIR="$T/config" HALO_DATA_DIR="$T/data" HALO_LOG_DIR="$T/logs" \
       HALO_OVERLAY_SOCKET="$T/o.sock" HALO_SUPERVISE=0 HALO_ALLOW_SECOND_INSTANCE=1 \
       HALO_DEV_COMMANDS=1

"$APP" >"$T/app.log" 2>&1 &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; rm -rf "$T"; }
trap cleanup EXIT

say() {  # send one overlay command, print the reply
  python3 - "$T/o.sock" "$1" <<'PY'
import socket, sys
s = socket.socket(socket.AF_UNIX)
s.settimeout(5)
s.connect(sys.argv[1])
s.sendall((sys.argv[2] + "\n").encode())
try:
    print(s.recv(200).decode().strip())
except socket.timeout:
    print("")
PY
}

for _ in $(seq 50); do [ -S "$T/o.sock" ] && break; sleep 0.1; done

shoot() {  # window-kind width height file
  local id
  id="$(say "window $1 $2 $3")"
  [[ "$id" =~ ^[0-9]+$ ]] || { echo "  no $1 window ($id)" >&2; return; }
  sleep 0.6
  screencapture -x -o -l "$id" "$4"
  echo "  $4"
}

for look in light dark; do
  say "appearance $look" >/dev/null
  for pane in "${PANES[@]}"; do
    say "settings $pane" >/dev/null
    sleep 0.5
    shoot settings 900 700 "$OUT/settings-$pane-$look-900x700.png"
    shoot settings 760 520 "$OUT/settings-$pane-$look-760x520.png"
  done
  if [ -z "${SKIP_ONBOARDING:-}" ]; then
    for step in $(seq 1 10); do
      say "onboarding $step" >/dev/null
      sleep 0.5
      shoot onboarding 900 700 "$OUT/onboarding-$step-$look-900x700.png"
      [ "$step" = 1 ] || [ "$step" = 5 ] && \
        shoot onboarding 760 520 "$OUT/onboarding-$step-$look-760x520.png"
    done
  fi
done
echo "wrote $OUT"
