#!/bin/bash
# Builds Halo.app -- agent-style (no Dock icon, no menu bar item).
# This bundle is the TCC identity: grant Accessibility + Input Monitoring to it
# once, and both the overlay and the Python engine it supervises are covered.
set -e
cd "$(dirname "$0")"
swift build -c release
APP="$PWD/Halo.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp .build/release/HaloOverlay "$APP/Contents/MacOS/Halo"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Halo</string>
  <key>CFBundleDisplayName</key><string>Halo</string>
  <key>CFBundleIdentifier</key><string>io.github.tharuns123.halo</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>Halo</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <!-- Agent app: no Dock icon, no menu bar, never becomes active. -->
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
  <!-- REQUIRED for microphone access. Without this key macOS denies the mic
       and hands the app a stream of zeros instead of an error -- which looks
       exactly like a working recording of total silence. The Python engine
       runs as our child, so its mic use is attributed to THIS bundle. -->
  <key>NSMicrophoneUsageDescription</key>
  <string>Halo records audio while you hold the dictation hotkey, and transcribes it on this Mac.</string>
</dict>
</plist>
PLIST
# Signing identity matters for TCC.
#
# Ad-hoc (-) means the code identity IS the binary's hash, so every rebuild
# looks like a brand-new app and macOS silently voids your Accessibility and
# Input Monitoring grants. With a self-signed certificate the identity is the
# certificate, so grants survive rebuilds.
#
#   Keychain Access > Certificate Assistant > Create a Certificate...
#     Name: Halo Signing   Identity Type: Self Signed Root
#     Certificate Type: Code Signing
#   Then: export HALO_SIGN_IDENTITY="Halo Signing"
# Prefer a real certificate: with one, TCC keys on the certificate rather than
# the binary hash, so Accessibility survives rebuilds. Auto-detect if the user
# has not named one explicitly.
IDENTITY="${HALO_SIGN_IDENTITY:-}"
if [ -z "$IDENTITY" ]; then
  IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null \
              | sed -n 's/.*"\(Apple Development:[^"]*\)".*/\1/p' | head -1)"
fi
[ -z "$IDENTITY" ] && IDENTITY="-"
[ "$IDENTITY" != "-" ] && echo "Signing with: $IDENTITY"
codesign --force --deep --sign "$IDENTITY" "$APP" 2>/dev/null || true

if [ "$IDENTITY" = "-" ]; then
  echo
  echo "NOTE: signed ad-hoc. macOS treats each rebuild as a new app, so you"
  echo "      must RE-GRANT Accessibility + Input Monitoring to Halo now:"
  echo "        1. tccutil reset Accessibility io.github.tharuns123.halo"
  echo "        2. tccutil reset ListenEvent   io.github.tharuns123.halo"
  echo "        3. re-add $APP in System Settings > Privacy & Security"
  echo "        4. ./haloctl restart"
  echo "      Avoid this permanently by creating a self-signed cert and setting"
  echo "      HALO_SIGN_IDENTITY (see comments in overlay/build_app.sh)."
fi
# Drop the pre-rename bundle so there is only one app to grant permissions to.
rm -rf "$PWD/HaloOverlay.app"
echo "Built: $APP"
