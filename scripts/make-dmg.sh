#!/bin/bash
# Build dist/Halo-<version>.dmg, the download attached to each GitHub release:
# Halo.app beside a shortcut to Applications on a window that says "drag Halo
# into Applications", so installing is one drag.
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

WORK="$(mktemp -d)"
STAGE="$WORK/stage"
MNT="$WORK/mnt"
trap 'hdiutil detach -quiet -force "$MNT" 2>/dev/null || true; rm -rf "$WORK"' EXIT
mkdir -p "$STAGE/.background" "$MNT"
ditto "$APP" "$STAGE/Halo.app"
ln -s /Applications "$STAGE/Applications"
cp "packaging/dmg/If macOS blocks Halo.txt" "$STAGE/"
cp packaging/dmg/background.tiff "$STAGE/.background/"

# Writable first, so Finder can lay out the window: the arrow artwork, Halo
# on the left of it and Applications on the right, no toolbar or sidebar.
# Without this the window opens as a bare file list and nothing says "drag".
hdiutil create -quiet -volname "Halo $VERSION" -srcfolder "$STAGE" \
  -fs HFS+ -format UDRW -size "$(( $(du -sm "$STAGE" | cut -f1) + 20 ))m" -ov "$WORK/rw.dmg"
hdiutil attach -quiet -readwrite -noverify -noautoopen -nobrowse -mountpoint "$MNT" "$WORK/rw.dmg"

# Positions are icon centres on the 640x400 artwork (packaging/dmg/background.svg).
# The window is addressed by path, not by volume name, so a "Halo x.y.z"
# already mounted from an earlier download cannot be the one that gets styled.
if ! osascript - "$MNT" <<'APPLESCRIPT'
on run argv
  set vol to (POSIX file (item 1 of argv)) as alias
  tell application "Finder"
    open vol
    set w to container window of vol
    set current view of w to icon view
    set toolbar visible of w to false
    set statusbar visible of w to false
    set sidebar width of w to 0
    set bounds of w to {200, 120, 840, 548}
    set opts to icon view options of w
    set arrangement of opts to not arranged
    set icon size of opts to 96
    set text size of opts to 13
    set background picture of opts to (file ".background:background.tiff" of vol)
    set position of item "Halo.app" of vol to {160, 170}
    set position of item "Applications" of vol to {480, 170}
    set position of item "If macOS blocks Halo.txt" of vol to {320, 290}
    close w
    open vol
    update vol without registering applications
    delay 1
    close container window of vol
  end tell
end run
APPLESCRIPT
then
  # Still installable -- Halo.app and the Applications shortcut are there --
  # just not laid out. CI shows this as a warning on the run.
  echo "::warning::Finder could not lay out the disk image window; it opens as a plain list"
fi
# Finder writes .DS_Store a moment after the window closes.
for _ in 1 2 3 4 5; do [ -f "$MNT/.DS_Store" ] && break; sleep 1; done
SetFile -a V "$MNT/.background" 2>/dev/null || true
rm -rf "$MNT/.fseventsd"
sync
hdiutil detach -quiet "$MNT"

rm -f "$OUT"
hdiutil convert -quiet "$WORK/rw.dmg" -format ULFO -ov -o "$OUT"
cp "$OUT" "$ROOT/dist/Halo.dmg"
echo "$OUT ($(du -h "$OUT" | cut -f1))"
