#!/bin/bash
# Regenerate packaging/dmg/background.tiff from packaging/dmg/background.svg.
#
# Run this only when the artwork changes, and commit the result, as with
# make-icon.sh: the release build must not depend on librsvg. The .tiff holds
# a 1x and a 2x image, so Finder picks the sharp one on a Retina display.
#
# The artwork names system typefaces only: on macOS librsvg finds fonts
# through CoreText, which cannot see the app's bundled ones.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

command -v rsvg-convert >/dev/null || {
  echo "error: rsvg-convert not found.  brew install librsvg" >&2; exit 1; }

SRC="packaging/dmg/background.svg"
OUT="packaging/dmg/background.tiff"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

rsvg-convert -w 640 -h 400 "$SRC" -o "$TMP/background.png"
rsvg-convert -w 1280 -h 800 "$SRC" -o "$TMP/background@2x.png"
tiffutil -cathidpicheck "$TMP/background.png" "$TMP/background@2x.png" -out "$OUT" 2>/dev/null
echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
