#!/bin/bash
# Load the release signing certificate into a throwaway keychain and print the
# identity to hand to scripts/make-app.sh.
#
#   export HALO_SIGN_IDENTITY="$(scripts/signing-keychain.sh)"
#
# The certificate comes from, in order:
#   HALO_SIGNING_P12_BASE64 + HALO_SIGNING_P12_PASSWORD   (CI: repository secrets)
#   ~/.config/halo-release/halo-release.p12 + p12-password.txt   (the maintainer's Mac)
#
# It is self-signed, and it must be the SAME certificate for every release:
# TCC keys the user's Accessibility, Input Monitoring and Microphone grants on
# "identifier io.github.tharuns123.halo and certificate leaf = H...", so a new
# certificate costs every user a re-grant. Back it up; never regenerate it.
set -euo pipefail

KEYCHAIN="${HALO_SIGNING_KEYCHAIN:-$HOME/Library/Keychains/halo-release-build.keychain-db}"
KC_ARG="${KEYCHAIN%-db}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [ -n "${HALO_SIGNING_P12_BASE64:-}" ]; then
  printf '%s' "$HALO_SIGNING_P12_BASE64" | base64 -D > "$TMP/cert.p12"
  P12="$TMP/cert.p12"
  PW="${HALO_SIGNING_P12_PASSWORD:?HALO_SIGNING_P12_PASSWORD is not set}"
else
  DIR="$HOME/.config/halo-release"
  P12="$DIR/halo-release.p12"
  [ -f "$P12" ] || { echo "error: no signing certificate at $P12" >&2; exit 1; }
  PW="$(cat "$DIR/p12-password.txt")"
fi

KC_PW="$(/usr/bin/openssl rand -hex 16)"
security delete-keychain "$KC_ARG" >/dev/null 2>&1 || true
security create-keychain -p "$KC_PW" "$KC_ARG"
security set-keychain-settings "$KC_ARG"          # no auto-lock mid-build
security unlock-keychain -p "$KC_PW" "$KC_ARG"
security import "$P12" -k "$KC_ARG" -P "$PW" -T /usr/bin/codesign >/dev/null
# Without this codesign stops for the "allow access to this key" dialog.
security set-key-partition-list -S apple-tool:,apple: -s -k "$KC_PW" "$KC_ARG" >/dev/null
# codesign only searches keychains on the search list.
security list-keychains -d user -s "$KC_ARG" $(security list-keychains -d user | tr -d '"')

# Not `find-identity -v`: a self-signed certificate is never "valid" to the
# trust policy (CSSMERR_TP_NOT_TRUSTED), and codesign signs with it anyway.
security find-identity -p codesigning "$KC_ARG" \
  | awk '/Halo Release Signing/ { print $2; exit }'
