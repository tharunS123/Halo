# BorderBeamKit (vendored)

The SwiftUI port of [Border Beam](https://libraries.dev/beam) by Jakub Antalik.
MIT licensed; see `LICENSE` in this directory.

- Source: https://github.com/Jakubantalik/Libraries.dev
- Path: `packages/border-beam/ports/ios/BorderBeamKit/Sources/BorderBeamKit`
- Pinned revision: `f20116327f4e3b28d0fb70b04437dfd092bf88fe`
- Spec version: `1.0.0` (`beam-spec.json`); rotation 1.96 s, fade-in 0.6 s, fade-out 0.5 s

**Why vendored, not a package dependency:** SwiftPM can only depend on a
repository whose `Package.swift` is at its root, and this one lives in a
subdirectory of a monorepo. (Same reason as `ThinkingOrbsKit`.) The upstream
`Tests/` and `snapshot.sh` are not vendored.

## What differs from upstream, and why

Upstream compiles `BeamShaders.metal` through Xcode's build system (a `.process`
resource) and reads its files through SwiftPM's generated `Bundle.module`. Halo
is built with the **Command Line Tools only** (Homebrew builds from source; CI
runs `xcode-select -s /Library/Developer/CommandLineTools` and checks the build
is reproducible), and the Command Line Tools have no `metal` compiler. So:

1. **`BeamShaders.metal`: unmodified**, kept here as the source of truth but
   *excluded* from the SwiftPM target (`Package.swift`). It is compiled once, by
   a maintainer with full Xcode, into `Resources/BorderBeam.metallib` with
   `scripts/build-beam-metallib.sh` (`DEVELOPER_DIR` only; `xcode-select` is
   never touched). The metallib is **committed**, so no build of Halo needs
   Xcode. Needs Xcode's separate Metal Toolchain component:
   `xcodebuild -downloadComponent MetalToolchain`. Re-run the script (and
   commit the result) whenever `BeamShaders.metal` changes; `--check` verifies
   the committed file is current.
2. **`Resources/beam-spec.json`: unmodified**, and the metallib, are plain
   files. `overlay/build_app.sh` copies them to
   `Halo.app/Contents/Resources/BorderBeam/`.
3. **`BeamResources.swift`: new (ours).** Finds those files: the app bundle
   first, then `HALO_BORDERBEAM_RESOURCES`, then the vendored source tree
   relative to the working directory / executable (bare `swift build`
   binaries). It compiles in no absolute path, which would make the binary
   differ by checkout directory and break the reproducible-cdhash guarantee.
   It also exposes `BeamRuntime.shadersAvailable`, so the app can draw a static
   boundary if the metallib has not been generated.
4. **Four one-line patches** to route through it: `BeamSpec.swift`
   (`Bundle.module.url(...)` -> `BeamResources.url(...)`, plus the fatalError
   wording) and `RotateBeamLayers.swift`, `LineBeamLayers.swift`,
   `PulseBeamLayers.swift` (`ShaderLibrary.bundle(.module)` ->
   `BeamResources.shaderLibrary`, a `ShaderLibrary(url:)` created once).

5. **`BorderBeam.swift`: `@State` replaced.** In the current SDK `@State` is a
   SwiftUI macro whose plugin ships only with Xcode, so upstream's two
   `@State` properties (`fade`, `mounted`) fail under the Command Line Tools.
   They live in a small `BeamLifecycle` ObservableObject held by
   `@StateObject`, with two computed properties so the rest of the file is
   upstream's. Marked `HALO PATCH`.

No other upstream `.swift` file is modified. To update: copy the upstream
directory over this one, re-apply the five patches, keep `BeamResources.swift`
and this file, update the pinned revision, regenerate the metallib, and rebuild.

Halo uses only the `.md` size with the `.mono` variant and an explicit circular
radius (see `OverlayView.swift`).
