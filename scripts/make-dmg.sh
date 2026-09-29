#!/bin/bash
# Build dist/Halo-<version>.dmg: the installer-style disk image attached to
# each GitHub release.
#
#   scripts/make-dmg.sh
#
# The image holds packaging/dmg/, not Halo.app. See "Releasing" in
# CONTRIBUTING.md: a downloaded ad-hoc-signed app is refused by Gatekeeper.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VERSION="$(tr -d '[:space:]' < VERSION)"
OUT="$ROOT/dist/Halo-$VERSION.dmg"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p dist
cp -p packaging/dmg/* "$STAGE/"
chmod +x "$STAGE/Install Halo.command"

rm -f "$OUT"
hdiutil create -quiet -volname "Halo $VERSION" -srcfolder "$STAGE" \
  -fs HFS+ -format UDZO -ov "$OUT"
echo "$OUT"
