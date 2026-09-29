#!/bin/bash
# Double-click installer shipped inside the Halo .dmg.
#
# It does not contain Halo. It runs the same Homebrew install INSTALL.md
# describes, so Halo is still built on this Mac and never carries the
# com.apple.quarantine attribute (see ARCHITECTURE.md for why that matters).
set -euo pipefail

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die()  { printf '\n\033[31merror:\033[0m %s\n' "$*" >&2; echo; read -r -p "Press Return to close." _; exit 1; }

clear
echo "Halo installer"
echo "Local push-to-talk dictation. Nothing you say leaves this Mac."

[ "$(uname -m)" = "arm64" ] || die "Halo needs a Mac with Apple Silicon (M1 or newer)."
MAJOR="$(sw_vers -productVersion | cut -d. -f1)"
[ "$MAJOR" -ge 14 ] || die "Halo needs macOS 14 (Sonoma) or newer; this Mac has $(sw_vers -productVersion)."

BREW=/opt/homebrew/bin/brew
if [ ! -x "$BREW" ]; then
  say "Installing Homebrew (it will ask for your Mac password; typing shows nothing)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    || die "Homebrew did not install. Nothing else was changed."
fi
[ -x "$BREW" ] || die "Homebrew installed somewhere unexpected; expected $BREW."

eval "$("$BREW" shellenv)"
# Homebrew's own installer asks you to do this by hand; skipping it is why
# `halo` later reports "command not found".
if ! grep -qs 'brew shellenv' "$HOME/.zprofile"; then
  say "Putting Homebrew on your PATH (~/.zprofile)"
  echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile"
fi

say "Installing Halo (builds on this Mac, a couple of minutes)"
brew tap tharuns123/halo
# Homebrew 7 refuses formulae from a personal tap until it is trusted. Older
# versions have no such command, so its absence is not an error.
brew trust tharuns123/halo 2>/dev/null || true
if brew list --formula halo >/dev/null 2>&1; then
  brew upgrade halo || true
else
  brew install halo || die "brew install halo failed. The messages above say why."
fi

say "Starting Halo setup"
halo setup || true

echo
echo "Done. Hold F9, speak, and let go."
echo "If anything misbehaves later:  halo doctor"
echo
read -r -p "Press Return to close." _
