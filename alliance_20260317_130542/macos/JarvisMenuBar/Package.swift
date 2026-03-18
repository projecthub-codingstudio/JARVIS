// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "JarvisMenuBar",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .executable(name: "JarvisMenuBar", targets: ["JarvisMenuBar"]),
    ],
    targets: [
        .executableTarget(
            name: "JarvisMenuBar",
            path: "Sources"
        ),
    ]
)
