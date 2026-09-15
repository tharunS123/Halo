# ThinkingOrbsKit (vendored)

The SwiftUI port of [thinking-orbs](https://libraries.dev/orbs.html) by Jakub
Antalik and Alexandr Brinza. MIT licensed; see `LICENSE` in this directory.

- Source: https://github.com/Jakubantalik/Libraries.dev
- Path: `packages/thinking-orbs/ports/ios/ThinkingOrbsKit/Sources/ThinkingOrbsKit`
- Commit: `9d735d1566d6` (2026-08-16)

**Why vendored, not a package dependency:** SwiftPM can only depend on a
repository whose `Package.swift` is at its root, and this one lives in a
subdirectory of a monorepo.

**Upstream `.swift` files are unmodified.** The one local addition is
`FlowOverrides.swift`, a public entry point that lets the overlay drive preset
options (the `composing` ribbon's `wobMul`) from the mic level. To update:
copy that upstream directory over this one, keep `FlowOverrides.swift`, and
rebuild. Then check that no file uses `@State` or other SwiftUI macros: the
overlay must build with the Command Line Tools alone (see "Background mode" in
the project README).
