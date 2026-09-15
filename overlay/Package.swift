// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "FlowOverlay",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "FlowOverlay",
            dependencies: ["ThinkingOrbsKit"],
            path: "Sources/FlowOverlay"
        ),
        // Vendored from Libraries.dev (MIT); see Sources/ThinkingOrbsKit/VENDORED.md.
        .target(
            name: "ThinkingOrbsKit",
            path: "Sources/ThinkingOrbsKit",
            exclude: ["LICENSE", "VENDORED.md"]
        ),
    ]
)
