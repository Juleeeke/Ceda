// swift-tools-version: 5.10
import PackageDescription
let package = Package(
    name: "CedaNative",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "CedaNative", targets: ["CedaApp"]),
        .executable(name: "CedaContractChecks", targets: ["CedaContractChecks"])],
    targets: [
        .target(name: "CedaCore"),
        .executableTarget(name: "CedaApp", dependencies: ["CedaCore"]),
        .executableTarget(name: "CedaContractChecks", dependencies: ["CedaCore"], path: "Checks")
    ]
)
