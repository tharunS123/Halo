#!/usr/bin/env bash
# Compiles the Border Beam shaders into overlay/Sources/BorderBeamKit/Resources/
# BorderBeam.metallib. A maintainer runs this ONCE (and whenever the vendored
# BeamShaders.metal changes); the result is committed. Building Halo never needs
# it: build_app.sh copies the committed metallib into Halo.app, so the Command
# Line Tools stay sufficient and CI stays reproducible. See
# overlay/Sources/BorderBeamKit/VENDORED.md.
#
#   scripts/build-beam-metallib.sh [--check]
#
# --check compiles to a temp dir and fails if the committed metallib differs.
#
# Needs full Xcode's `metal` compiler *and* its Metal Toolchain component:
#   xcodebuild -downloadComponent MetalToolchain     # one-off, no sudo
# DEVELOPER_DIR points at Xcode for this script only; it never touches
# `xcode-select`.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

KIT="overlay/Sources/BorderBeamKit"
SRC="$KIT/BeamShaders.metal"
OUT="$KIT/Resources/BorderBeam.metallib"
export DEVELOPER_DIR="${BEAM_DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"

if ! xcrun -sdk macosx --find metal >/dev/null 2>&1 \
   || ! xcrun -sdk macosx metal --version >/dev/null 2>&1; then
  cat >&2 <<MSG
error: no working Metal compiler under DEVELOPER_DIR=$DEVELOPER_DIR
       Xcode 26+ ships the Metal Toolchain as a separate component. Install it
       once (a download of several hundred MB from Apple; needs no sudo):
           DEVELOPER_DIR=$DEVELOPER_DIR xcodebuild -downloadComponent MetalToolchain
MSG
  exit 1
fi

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

# Compile from inside the source directory with a relative path, so no absolute
# path can end up in the object file. macOS 14 is the deployment target
# (Package.swift), Metal 3.1 its language version.
compile() {  # out.metallib
  local air="$T/$(basename "$1").air"
  (cd "$KIT" && xcrun -sdk macosx metal -c -std=metal3.1 -mmacosx-version-min=14.0 \
      BeamShaders.metal -o "$air")
  xcrun -sdk macosx metallib "$air" -o "$1"
}

compile "$T/a.metallib"
compile "$T/b.metallib"
if cmp -s "$T/a.metallib" "$T/b.metallib"; then
  echo "deterministic: two compiles are byte-identical"
else
  echo "note: two compiles differ (fine -- the metallib is committed, not rebuilt)"
fi

if [ "${1:-}" = "--check" ]; then
  if cmp -s "$T/a.metallib" "$OUT"; then echo "ok: $OUT is current"; exit 0; fi
  echo "committed $OUT differs from a fresh compile" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
cp "$T/a.metallib" "$OUT"
echo "wrote $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
echo "  compiler: $(xcrun -sdk macosx metal --version | head -1)"
shasum -a 256 "$OUT"
