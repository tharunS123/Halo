#!/bin/bash
# Builds Halo.app -- agent-style (no Dock icon, no menu bar item).
# This bundle is the TCC identity: grant Accessibility + Input Monitoring to it
# once, and both the overlay and the Python engine it supervises are covered.
set -e
cd "$(dirname "$0")"
# -no_uuid: the linker derives LC_UUID from its inputs, which include absolute
# paths, so the same source built in two directories produced two different
# binaries -- and with ad-hoc signing the binary hash IS the app's identity, so
# every install voided the user's Accessibility grant. Measured: same source,
# same path -> identical cdhash; same source, different path -> different.
swift build -c release -Xlinker -no_uuid
APP="$PWD/Halo.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp .build/release/HaloOverlay "$APP/Contents/MacOS/Halo"
# The other half of it: the symbol table keeps dsymutil debug-map stabs (N_SO /
# N_OSO) holding absolute source and .o paths. Useless in a shipped release
# binary, and path-dependent. Strip before signing, or the signature covers them.
strip -S "$APP/Contents/MacOS/Halo"
VERSION="$(cat "$PWD/../VERSION" 2>/dev/null || echo dev)"
# One source of truth for the bundle metadata: the Homebrew formula renders
# this same template.
sed "s|__VERSION__|$VERSION|g" "$PWD/Info.plist.in" > "$APP/Contents/Info.plist"
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
IDENTITY="${HALO_SIGN_IDENTITY:--}"
[ "$IDENTITY" != "-" ] && echo "Signing with: $IDENTITY"
# Not piped to /dev/null: a silent signing failure ships an unsigned bundle
# that macOS then refuses in ways that look like a Halo bug.
codesign --force --deep --sign "$IDENTITY" "$APP"

if [ "$IDENTITY" = "-" ]; then
  echo
  echo "NOTE: signed ad-hoc. macOS treats each rebuild as a new app, so you"
  echo "      must RE-GRANT Accessibility + Input Monitoring to Halo now:"
  echo "        1. tccutil reset Accessibility io.github.tharuns123.halo"
  echo "        2. tccutil reset ListenEvent   io.github.tharuns123.halo"
  echo "        3. re-add $APP in System Settings > Privacy & Security"
  echo "        4. halo restart"
  echo "      Or let halo do it for you:  halo setup --repair"
  echo "      Avoid it permanently with a self-signed cert in HALO_SIGN_IDENTITY"
  echo "      (see the comments above in this script)."
fi
# Drop the pre-rename bundle so there is only one app to grant permissions to.
rm -rf "$PWD/HaloOverlay.app"
echo "Built: $APP"
