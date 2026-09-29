// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "HaloOverlay",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "HaloOverlay",
            dependencies: ["ThinkingOrbsKit", "BorderBeamKit"],
            path: "Sources/HaloOverlay"
        ),
        // Vendored from Libraries.dev (MIT); see Sources/ThinkingOrbsKit/VENDORED.md.
        .target(
            name: "ThinkingOrbsKit",
            path: "Sources/ThinkingOrbsKit",
            exclude: ["LICENSE", "VENDORED.md"]
        ),
        // Vendored from Libraries.dev (MIT); see Sources/BorderBeamKit/VENDORED.md.
        // The shader source and the resources are excluded on purpose: upstream
        // compiles the .metal with Xcode's build system, which the Command Line
        // Tools do not have. They ship as plain files instead -- the metallib
        // is compiled once by scripts/build-beam-metallib.sh and committed, and
        // build_app.sh copies it into Halo.app (BeamResources.swift finds it).
        .target(
            name: "BorderBeamKit",
            path: "Sources/BorderBeamKit",
            exclude: ["LICENSE", "VENDORED.md", "BeamShaders.metal", "Resources"]
        ),
    ]
)
