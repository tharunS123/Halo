# Homebrew formula for Halo.
#
# This file is the source of truth; the published copy lives in the tap repo
# (tharunS123/homebrew-halo) as Formula/halo.rb. scripts/release.sh copies it
# there with the version and sha256 filled in.
#
# One of two ways to install Halo. The other is the self-contained Halo.app on
# each GitHub release (scripts/make-app.sh), signed with the project's release
# certificate. This formula builds on the user's machine instead, so nothing is
# downloaded as an archive and nothing gets the com.apple.quarantine attribute
# -- no Gatekeeper step at all, for people happy with a Terminal.
class Halo < Formula
  desc "Local push-to-talk dictation for macOS"
  homepage "https://github.com/tharunS123/Halo"
  url "https://github.com/tharunS123/Halo/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "FILLED_IN_AT_RELEASE"
  license "MIT"
  head "https://github.com/tharunS123/Halo.git", branch: "main"

  depends_on "python@3.13"
  depends_on "whisper.cpp"
  # Runs the optional local cleanup model. The model itself (1-2.5GB) is
  # never fetched unless the user asks, so this costs only the binary.
  depends_on "llama.cpp"
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
    resources = app/"Contents/Resources"
    cp buildpath/"overlay/Halo.icns", resources/"Halo.icns"
    # Keep this bundle in sync with overlay/build_app.sh: the new Settings and
    # setup UI load fonts and brand art from Contents/Resources at run time.
    %w[Fonts Brand Licenses].each do |name|
      cp_r buildpath/"overlay/Resources/#{name}", resources/name
    end
    beam_source = buildpath/"overlay/Sources/BorderBeamKit"
    beam_resources = resources/"BorderBeam"
    beam_resources.mkpath
    cp beam_source/"Resources/beam-spec.json", beam_resources/"beam-spec.json"
    metallib = beam_source/"Resources/BorderBeam.metallib"
    cp metallib, beam_resources/"BorderBeam.metallib" if metallib.exist?
    cp beam_source/"LICENSE", beam_resources/"LICENSE"
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
      One more step -- it installs Halo and opens its setup guide, which
      downloads the speech model and walks you through the permissions:

        halo setup

      Halo works offline with no account, and nothing you say leaves this
      Mac. Setup offers an optional 1.1GB cleanup model that also runs here.

      After `brew upgrade halo`, run:

        halo doctor

      There is no paid Apple Developer ID here, so setup offers to sign Halo
      with a certificate generated on your Mac. Say yes and upgrades keep your
      Accessibility and Input Monitoring grants; decline and macOS voids them
      every time the bundle changes, which is every release. `halo doctor`
      says which mode you are in either way.
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/halo --version")
    # Offline and side-effect free: no launchctl, no permissions, no network.
    system bin/"halo", "model", "list"
  end
end
