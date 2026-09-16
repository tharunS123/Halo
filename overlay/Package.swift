// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "HaloOverlay",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "HaloOverlay",
            dependencies: ["ThinkingOrbsKit"],
            path: "Sources/HaloOverlay"
        ),
        // Vendored from Libraries.dev (MIT); see Sources/ThinkingOrbsKit/VENDORED.md.
        .target(
            name: "ThinkingOrbsKit",
            path: "Sources/ThinkingOrbsKit",
            exclude: ["LICENSE", "VENDORED.md"]
        ),
    ]
)
