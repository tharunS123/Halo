// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "FlowOverlay",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "FlowOverlay", path: "Sources/FlowOverlay")
    ]
)
