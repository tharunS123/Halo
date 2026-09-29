#!/bin/bash
# Build dist/Halo.app: the self-contained app the .dmg ships.
#
#   scripts/make-app.sh
#
# Everything Halo runs is inside the bundle, so a download needs no Homebrew,
# no Python and no Terminal:
#
#   Contents/MacOS/Halo              the Swift app (overlay/)
#   Contents/Helpers/whisper-cli     whisper.cpp, static, Metal embedded
#   Contents/Helpers/llama-server    llama.cpp, static, no HTTPS, no web UI
#   Contents/Resources/python/       a relocatable CPython + requirements.txt
#   Contents/Resources/engine/       the engine (*.py)
#   Contents/Resources/share/        default configs
#   Contents/Resources/bin/halo      the CLI, for anyone who wants it
#
# Signing: HALO_SIGN_IDENTITY names a certificate in the keychain; unset means
# ad-hoc. Releases are signed with one self-signed certificate that never
# changes, so the designated requirement -- and with it the user's
# Accessibility, Input Monitoring and Microphone grants -- survives every
# update. See "Distribution" in ARCHITECTURE.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# --- pinned inputs, checksummed ----------------------------------------------
PY_VERSION="3.13.15"
PY_BUILD="20260929"
PY_SHA256="d66c67f16148c7454b1509c32747175f7669c8b8e105b97b92a0000d66af6e6e"
WHISPER_VERSION="1.9.4"
WHISPER_SHA256="57e280cee375ab02425b806ad5146b99f6eb9357e3c2b31357c8a6af2e2e44ae"
LLAMA_VERSION="0.5.0"
LLAMA_SHA256="fef9ed754f4e031fb5c663c29260feda4ebc241abb68d64a81c0f1df5f1748e2"

PY_TARBALL="cpython-${PY_VERSION}+${PY_BUILD}-aarch64-apple-darwin-install_only_stripped.tar.gz"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_BUILD}/${PY_TARBALL/+/%2B}"
WHISPER_URL="https://github.com/ggml-org/whisper.cpp/archive/refs/tags/v${WHISPER_VERSION}.tar.gz"
LLAMA_URL="https://github.com/ggml-org/llama.cpp/archive/refs/tags/v${LLAMA_VERSION}.tar.gz"

BUILD="$ROOT/build"
VENDOR="$BUILD/vendor"
APP="$ROOT/dist/Halo.app"
IDENTITY="${HALO_SIGN_IDENTITY:--}"
JOBS="$(sysctl -n hw.ncpu)"
export MACOSX_DEPLOYMENT_TARGET=14.0

say() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(uname -m)" = "arm64" ] || die "build on Apple Silicon: ggml enables Metal only there"

fetch() {  # url file sha256
  local url="$1" out="$VENDOR/$2" sha="$3"
  mkdir -p "$VENDOR"
  if [ ! -f "$out" ] || [ "$(shasum -a 256 "$out" | cut -d' ' -f1)" != "$sha" ]; then
    say "downloading $2"
    curl -fsSL --retry 3 -o "$out.part" "$url"
    mv "$out.part" "$out"
  fi
  [ "$(shasum -a 256 "$out" | cut -d' ' -f1)" = "$sha" ] || die "$2: checksum mismatch"
}

fetch "$PY_URL" "$PY_TARBALL" "$PY_SHA256"
fetch "$WHISPER_URL" "whisper.cpp-$WHISPER_VERSION.tar.gz" "$WHISPER_SHA256"
fetch "$LLAMA_URL" "llama.cpp-$LLAMA_VERSION.tar.gz" "$LLAMA_SHA256"

# --- whisper-cli and llama-server ----------------------------------------------
# Static, so the binary is one file with nothing but system frameworks behind
# it (Homebrew's link @rpath and /opt/homebrew/opt/ggml, which a download does
# not have). GGML_METAL_EMBED_LIBRARY carries the shader source inside the
# binary and compiles it at run time, so no metallib and no Xcode.
build_tool() {  # name version target cmake-args...
  local name="$1" version="$2" target="$3"; shift 3
  local src="$BUILD/src/$name-$version" obj="$BUILD/obj/$name-$version"
  if [ ! -x "$obj/bin/$target" ]; then
    say "building $target ($name $version)"
    rm -rf "$src" && mkdir -p "$BUILD/src"
    tar -xzf "$VENDOR/$name-$version.tar.gz" -C "$BUILD/src"
    cmake -S "$src" -B "$obj" -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
      -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_METAL=ON -DGGML_METAL_EMBED_LIBRARY=ON \
      "$@" >"$BUILD/$name-cmake.log"
    cmake --build "$obj" --target "$target" -j "$JOBS" >"$BUILD/$name-build.log"
  fi
  # Nothing outside /usr/lib and /System, or the download breaks on a Mac
  # without Homebrew.
  if otool -L "$obj/bin/$target" | tail -n +2 | grep -Ev '^\s+(/usr/lib/|/System/)'; then
    die "$target links something a stock Mac does not have (above)"
  fi
}

build_tool whisper.cpp "$WHISPER_VERSION" whisper-cli \
  -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON -DWHISPER_SDL2=OFF
# No OpenSSL: llama-server only ever listens on 127.0.0.1 for the engine, and
# the engine refuses the network anyway (netguard.py). No web UI, and never the
# prebuilt one, which the build would otherwise download.
build_tool llama.cpp "$LLAMA_VERSION" llama-server \
  -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_TOOLS=ON

# --- the Swift app -------------------------------------------------------------
say "building the Swift app"
HALO_NO_SIGN=1 overlay/build_app.sh >/dev/null
rm -rf "$APP" && mkdir -p "$ROOT/dist"
cp -R overlay/Halo.app "$APP"
C="$APP/Contents"
R="$C/Resources"

mkdir -p "$C/Helpers"
cp "$BUILD/obj/whisper.cpp-$WHISPER_VERSION/bin/whisper-cli" "$C/Helpers/"
cp "$BUILD/obj/llama.cpp-$LLAMA_VERSION/bin/llama-server" "$C/Helpers/"
strip -S "$C/Helpers/whisper-cli" "$C/Helpers/llama-server"

# --- Python ----------------------------------------------------------------------
say "installing Python $PY_VERSION and requirements.txt"
PY="$R/python"
tar -xzf "$VENDOR/$PY_TARBALL" -C "$R"          # unpacks as python/
PIP_DISABLE_PIP_VERSION_CHECK=1 "$PY/bin/python3" -m pip install -q --no-cache-dir \
  --only-binary=:all: -r requirements.txt
# The interpreter is statically linked, so libpython is dead weight, and Tk,
# IDLE, pip and the test suites are never used by the engine.
SITE="$PY/lib/python3.13/site-packages"
rm -rf "$PY/include" "$PY/share" "$PY/lib/pkgconfig" "$PY/lib/libpython3.13.dylib" \
  "$PY"/lib/libtcl* "$PY"/lib/tcl9* "$PY"/lib/tk9* "$PY"/lib/itcl* "$PY"/lib/thread* \
  "$PY"/lib/python3.13/{config-3.13-darwin,ensurepip,idlelib,tkinter,turtledemo,turtle.py} \
  "$PY"/lib/python3.13/lib-dynload/_tkinter* \
  "$SITE"/pip "$SITE"/pip-* "$SITE"/PyObjCTest
find "$PY/bin" -mindepth 1 ! -name python3.13 ! -name python3 ! -name python -delete
find "$SITE" -type d -name tests -prune -exec rm -rf {} +
find "$PY" -type d -name __pycache__ -prune -exec rm -rf {} +
# The pyobjc and cffi wheels are universal2; the x86_64 half can never run
# here: Halo is Apple Silicon only.
find "$PY" -type f \( -name '*.so' -o -name '*.dylib' \) | while read -r f; do
  if lipo -archs "$f" 2>/dev/null | grep -q x86_64 && lipo -archs "$f" | grep -q arm64; then
    lipo -thin arm64 "$f" -output "$f.thin" && mv "$f.thin" "$f"
  fi
done

# --- the engine ----------------------------------------------------------------------
# Same layout as the Homebrew formula (engine/ beside share/ and VERSION), so
# paths.py finds its defaults the same way in both.
say "installing the engine"
mkdir -p "$R/engine" "$R/share/defaults" "$R/share/launchd" "$R/bin"
cp ./*.py "$R/engine/"
cp defaults/*.json "$R/share/defaults/"
cp launchd/io.github.tharuns123.halo.plist.template "$R/share/launchd/"
cp VERSION "$R/VERSION"
cp packaging/app/halo "$R/bin/halo"
chmod 0755 "$R/bin/halo"

# Compile every .py now. A signed bundle must never be written to: Python
# would otherwise drop __pycache__ into it on first import, the seal would
# break, and macOS would call the app damaged. unchecked-hash means the .pyc
# is trusted without comparing mtimes, which a copy out of a .dmg can change.
"$PY/bin/python3" -m compileall -q -j 0 --invalidation-mode unchecked-hash \
  "$PY/lib/python3.13" "$R/engine" >/dev/null

# Info.plist promises macOS 14. pip picks wheels for the Mac it runs on, so a
# build machine on a newer macOS could quietly ship a binary Sonoma refuses.
too_new="$(find "$APP" -type f -print0 | xargs -0 file | awk -F: '/Mach-O/{print $1}' \
  | while read -r f; do
      v="$(otool -l "$f" | awk '/ minos /{print $2; exit}')"
      [ -n "$v" ] && [ "${v%%.*}" -gt 14 ] && echo "$v $f"
    done || true)"
[ -z "$too_new" ] || die "built for a macOS newer than 14:"$'\n'"$too_new"

# --- sign, inside out --------------------------------------------------------------
# Every Mach-O gets its own signature before the bundle is sealed; `--deep`
# is deprecated precisely because it gets this order wrong.
say "signing with ${IDENTITY/#-/ad-hoc}"
xattr -cr "$APP"
sign() { codesign --force --timestamp=none --sign "$IDENTITY" "$@"; }
find "$R/python" "$C/Helpers" -type f -print0 | while IFS= read -r -d '' f; do
  if file -b "$f" | grep -q '^Mach-O'; then sign "$f" 2>&1 | grep -v 'replacing existing signature' || true; fi
done
sign --identifier io.github.tharuns123.halo "$APP"
codesign --verify --strict --deep "$APP"

say "checking the bundle runs"
PYTHONDONTWRITEBYTECODE=1 "$R/bin/halo" --version
"$C/Helpers/whisper-cli" --help >/dev/null 2>&1 || die "whisper-cli does not run"
"$C/Helpers/llama-server" --version >/dev/null 2>&1 || die "llama-server does not run"
# Running it must not have written into the bundle (see compileall above).
codesign --verify --strict --deep "$APP" || die "running the engine modified the signed bundle"

say "$APP ($(du -sh "$APP" | cut -f1))"
codesign -d -r- "$APP" 2>&1 | grep designated
