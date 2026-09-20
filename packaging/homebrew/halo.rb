# Homebrew formula for Halo.
#
# This file is the source of truth; the published copy lives in the tap repo
# (tharunS123/homebrew-halo) as Formula/halo.rb. scripts/release.sh copies it
# there with the version and sha256 filled in.
#
# Why a formula and not a downloadable .app: Homebrew builds this on the
# user's machine, so nothing is ever downloaded as an archive and nothing gets
# the com.apple.quarantine attribute. A downloaded ad-hoc-signed app would be
# refused outright by Gatekeeper ("Halo is damaged"), which is strictly worse
# than the prompt it was trying to avoid. Do not switch to a bottled .app or a
# release zip without a paid Developer ID and notarization.
class Halo < Formula
  desc "Local push-to-talk dictation for macOS"
  homepage "https://github.com/tharunS123/Halo"
  url "https://github.com/tharunS123/Halo/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "FILLED_IN_AT_RELEASE"
  license "MIT"
  head "https://github.com/tharunS123/Halo.git", branch: "main"

  depends_on "python@3.13"
  depends_on "whisper.cpp"
  depends_on arch: :arm64        # ggml only enables Metal on Apple Silicon
  depends_on macos: :sonoma      # the app bundle targets macOS 14

  # Deliberately NOT `depends_on xcode:`. The Command Line Tools are enough,
  # which is why the vendored orb code avoids SwiftUI macros (their compiler
  # plugin ships only inside Xcode.app). See CONTRIBUTING.md.

  def install
    # --- the SwiftUI agent app (no remote SwiftPM dependencies) ---
    # --disable-sandbox: SwiftPM cannot compile its own manifest inside
    # Homebrew's sandbox (it needs writable caches), and fails with an
    # "Invalid manifest" error that names no cause.
    #
    # -Xlinker -no_uuid, plus the strip below, is what makes this build
    # reproducible. Homebrew builds in a randomly named temp directory, and
    # both LC_UUID and the symbol table's dsymutil debug-map stabs embed
    # absolute paths -- so the same source produced a different binary on every
    # install. Ad-hoc signing makes the binary hash the app's TCC identity, so
    # that silently voided the user's Accessibility grant each time, including
    # on releases that changed nothing but Python.
    # Measured: with these two, the same source built in two different
    # directories is byte-for-byte identical.
    system "swift", "build", "-c", "release", "--disable-sandbox",
           "-Xlinker", "-no_uuid",
           "--package-path", "overlay",
           "--scratch-path", buildpath/"swift-build"

    app = libexec/"Halo.app"
    (app/"Contents/MacOS").mkpath
    (app/"Contents/Resources").mkpath
    cp buildpath/"swift-build/release/HaloOverlay", app/"Contents/MacOS/Halo"
    cp buildpath/"overlay/Halo.icns", app/"Contents/Resources/Halo.icns"
    (app/"Contents/Info.plist").write (buildpath/"overlay/Info.plist.in").read
                                                                        .gsub("__VERSION__", version.to_s)
    system "strip", "-S", app/"Contents/MacOS/Halo"   # before signing, not after
    system "codesign", "--force", "--deep", "--sign", "-", app

    # --- the Python engine ---
    engine = libexec/"engine"
    engine.install Dir["*.py"]
    (libexec/"share/defaults").install Dir["defaults/*.json"]
    (libexec/"share/launchd").install "launchd/io.github.tharuns123.halo.plist.template"
    libexec.install "VERSION"

    venv = libexec/"venv"
    system Formula["python@3.13"].opt_bin/"python3.13", "-m", "venv", venv
    system venv/"bin/pip", "install", "--no-cache-dir", "--upgrade", "pip"
    system venv/"bin/pip", "install", "--no-cache-dir", "-r", "requirements.txt"

    (bin/"halo").write <<~SHELL
      #!/bin/bash
      exec "#{opt_libexec}/venv/bin/python" "#{opt_libexec}/engine/cli.py" "$@"
    SHELL
    chmod 0755, bin/"halo"
  end

  def caveats
    <<~EOS
      One more step -- it downloads the speech model and walks you through the
      three macOS permissions:

        halo setup

      Halo works offline with no account. An OpenRouter key is optional and
      only adds punctuation and filler-word cleanup; setup explains the
      tradeoff and never requires one.

      After `brew upgrade halo`, run:

        halo doctor

      Halo is signed ad-hoc (there is no paid Apple Developer ID), so macOS
      voids its Accessibility and Input Monitoring grants whenever the app
      bundle itself changes. `halo doctor` detects exactly that and tells you
      what to re-tick. Updates that only touch the engine leave grants alone.
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/halo --version")
    # Offline and side-effect free: no launchctl, no permissions, no network.
    system bin/"halo", "model", "list"
  end
end
