#!/bin/bash
# Cut a release: tag it, then update the Homebrew tap to point at the tarball.
#
#   scripts/release.sh 0.3.0
#
# There is no build artifact to upload. The tap builds from source on the
# user's machine, which is what keeps the app free of Gatekeeper quarantine.
set -euo pipefail

VERSION="${1:-}"
[ -n "$VERSION" ] || { echo "usage: scripts/release.sh <version>   e.g. 0.3.0" >&2; exit 1; }
VERSION="${VERSION#v}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAP="${HALO_TAP_DIR:-$HOME/Developer/homebrew-halo}"
REPO="tharunS123/Halo"
cd "$ROOT"

[ -z "$(git status --porcelain)" ] || { echo "error: working tree is dirty" >&2; exit 1; }

echo "$VERSION" > VERSION
git add VERSION
git commit -m "Release v$VERSION" --allow-empty
git tag "v$VERSION"
git push origin HEAD --tags

echo "==> waiting for the tarball to appear"
URL="https://github.com/$REPO/archive/refs/tags/v$VERSION.tar.gz"
for _ in $(seq 1 30); do
  curl -fsIL "$URL" >/dev/null 2>&1 && break
  sleep 2
done

SHA="$(curl -fsL "$URL" | shasum -a 256 | cut -d' ' -f1)"
echo "==> sha256 $SHA"

[ -d "$TAP" ] || { echo "error: tap not found at $TAP (set HALO_TAP_DIR)" >&2; exit 1; }
mkdir -p "$TAP/Formula"
sed -e "s|/archive/refs/tags/v[0-9.]*\.tar\.gz|/archive/refs/tags/v$VERSION.tar.gz|" \
    -e "s|sha256 \".*\"|sha256 \"$SHA\"|" \
    "$ROOT/packaging/homebrew/halo.rb" > "$TAP/Formula/halo.rb"

cd "$TAP"
git add Formula/halo.rb
git commit -m "halo $VERSION"
git push

echo
echo "Released v$VERSION. Verify with:"
echo "  brew update && brew upgrade halo && halo doctor"
