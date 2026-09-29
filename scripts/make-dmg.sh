#!/bin/bash
# Build dist/Halo-<version>.dmg, the download attached to each GitHub release:
# Halo.app beside a shortcut to Applications, so installing is one drag.
#
#   scripts/make-dmg.sh            # uses dist/Halo.app, building it if missing
#
# Build and sign the app first with scripts/make-app.sh (release.yml does).
# A copy named Halo.dmg is written too: the release asset with that name is
# what https://github.com/tharunS123/Halo/releases/latest/download/Halo.dmg
# always points at, so the website never needs a version in its link.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VERSION="$(tr -d '[:space:]' < VERSION)"
APP="$ROOT/dist/Halo.app"
OUT="$ROOT/dist/Halo-$VERSION.dmg"

[ -d "$APP" ] || scripts/make-app.sh
built="$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$APP/Contents/Info.plist")"
[ "$built" = "$VERSION" ] || { echo "error: dist/Halo.app is $built, VERSION is $VERSION; rebuild it" >&2; exit 1; }
codesign --verify --strict --deep "$APP"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
ditto "$APP" "$STAGE/Halo.app"
ln -s /Applications "$STAGE/Applications"
cp "packaging/dmg/If macOS blocks Halo.txt" "$STAGE/"

rm -f "$OUT"
hdiutil create -quiet -volname "Halo $VERSION" -srcfolder "$STAGE" \
  -fs HFS+ -format ULFO -ov "$OUT"
cp "$OUT" "$ROOT/dist/Halo.dmg"
echo "$OUT ($(du -h "$OUT" | cut -f1))"
