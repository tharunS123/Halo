#!/bin/bash
# Regenerate overlay/Halo.icns from docs/media/halo-icon.svg.
#
# Run this only when the icon artwork changes, and commit the result: the
# build must not depend on librsvg, and more importantly the .icns is part of
# the app bundle, so regenerating it changes the bundle's code hash and costs
# every user one re-grant of Accessibility. Deterministic input, committed
# output, no surprises at build time.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

command -v rsvg-convert >/dev/null || {
  echo "error: rsvg-convert not found.  brew install librsvg" >&2; exit 1; }

SRC="docs/media/halo-icon.svg"
SET="$(mktemp -d)/Halo.iconset"
mkdir -p "$SET"

# The exact set iconutil expects. Retina entries are the same pixel sizes
# under @2x names, so each is rendered once at its true pixel size.
for spec in 16:16x16 32:16x16@2x 32:32x32 64:32x32@2x \
            128:128x128 256:128x128@2x 256:256x256 512:256x256@2x \
            512:512x512 1024:512x512@2x; do
  px="${spec%%:*}"; name="${spec##*:}"
  rsvg-convert -w "$px" -h "$px" "$SRC" -o "$SET/icon_$name.png"
done

iconutil -c icns "$SET" -o overlay/Halo.icns
echo "wrote overlay/Halo.icns ($(du -h overlay/Halo.icns | cut -f1))"
