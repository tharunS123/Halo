import SwiftUI

// HALO LOCAL ADDITION (not upstream). See VENDORED.md.
//
// Upstream loads beam-spec.json and the compiled shader library through
// SwiftPM's generated `Bundle.module`, and needs Xcode's build system to turn
// BeamShaders.metal into a metallib. Halo builds with the Command Line Tools
// alone (no `metal` compiler), so here both files are plain resources:
//
//   Halo.app/Contents/Resources/BorderBeam/beam-spec.json
//   Halo.app/Contents/Resources/BorderBeam/BorderBeam.metallib
//
// copied there by overlay/build_app.sh. The metallib is compiled once, with
// full Xcode, by scripts/build-beam-metallib.sh and committed.

/// Where the beam's resources live, and whether the shaders can run at all.
enum BeamResources {
    static let directoryName = "BorderBeam"

    /// Looked up once. Order: the app bundle (a built Halo.app), an explicit
    /// override for tests, then the vendored source tree (bare `swift build`
    /// / `swift run` binaries). No absolute source path is compiled into the
    /// binary: that would make the build differ by checkout directory, and the
    /// ad-hoc signature (hence the user's Accessibility grant) depends on the
    /// binary being byte-identical wherever it is built.
    static let directory: URL? = {
        let fm = FileManager.default
        func isBeamDir(_ u: URL) -> Bool {
            fm.fileExists(atPath: u.appendingPathComponent("beam-spec.json").path)
        }
        if let res = Bundle.main.resourceURL {
            let u = res.appendingPathComponent(directoryName)
            if isBeamDir(u) { return u }
        }
        if let env = ProcessInfo.processInfo.environment["HALO_BORDERBEAM_RESOURCES"] {
            let u = URL(fileURLWithPath: env)
            if isBeamDir(u) { return u }
        }
        // <overlay>/.build/<triple>/release/HaloOverlay  ->  <overlay>
        var roots: [URL] = [URL(fileURLWithPath: fm.currentDirectoryPath)]
        if let exe = Bundle.main.executableURL {
            var u = exe.resolvingSymlinksInPath()
            for _ in 0..<5 { u.deleteLastPathComponent(); roots.append(u) }
        }
        for root in roots {
            for rel in ["Sources/BorderBeamKit/Resources", "overlay/Sources/BorderBeamKit/Resources"] {
                let u = root.appendingPathComponent(rel)
                if isBeamDir(u) { return u }
            }
        }
        return nil
    }()

    static func url(_ file: String) -> URL? {
        directory.map { $0.appendingPathComponent(file) }
            .flatMap { FileManager.default.fileExists(atPath: $0.path) ? $0 : nil }
    }

    static var metallibURL: URL? { url("BorderBeam.metallib") }

    /// The compiled shaders. Created once: `ShaderLibrary(url:)` loads the
    /// metallib, and the layers ask for it every frame.
    static let shaderLibrary: ShaderLibrary = {
        // A missing URL still yields a library (its functions then fail to
        // resolve and SwiftUI logs it); callers gate on `shadersAvailable`.
        ShaderLibrary(url: metallibURL ?? URL(fileURLWithPath: "/dev/null"))
    }()
}

/// Public switch for the host app: `BorderBeam` needs the compiled metallib.
/// When it is absent (the metallib has not been generated -- see
/// scripts/build-beam-metallib.sh) hosts should draw a static boundary rather
/// than instantiating the view.
public enum BeamRuntime {
    public static let shadersAvailable: Bool = {
        BeamResources.metallibURL != nil && BeamResources.url("beam-spec.json") != nil
    }()
}
