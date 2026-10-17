# Ceda macOS native application

SwiftUI + Canvas + MetalKit, minimum macOS 14. The current local build is arm64 (Apple Silicon). No third-party Swift package is required. The Python engine remains portable and independent.

Build from the repository root after installing the existing Python dev dependencies:

```sh
.venv/bin/python scripts/build_macos.py
```

Open `dist/Ceda SwiftUI.app`. Import a saved KiCad PCB, or use “打开合成演示板”. The demo has a deliberately insufficient voltage threshold; the expected result is **3.2920661237 V, fail**, not a fabricated pass.

The bundle includes the Python interpreter and engine libraries; an end user does not need the repository virtual environment. This is a locally signed development bundle. The old Qt development artifact is kept separately.

Development:

```sh
CEDA_PROJECT_ROOT="$PWD" swift run --package-path native/macos CedaNative
swift run --package-path native/macos CedaContractChecks
```

The contract/process checker avoids XCTest so it works with Command Line Tools alone. The build script places compiler and package caches inside `build/` to avoid dependence on writable user caches.

GPU validation of the actual production shader (requires a Metal device):

```sh
.venv/bin/python -m ceda native-export path/to/board.kicad_pcb --output outputs/native-board
.venv/bin/python -m ceda native-mesh path/to/board.kicad_pcb --output outputs/native-board --model-library path/to/models
build/swiftpm/release/CedaNative --check-contract outputs/native-board
build/swiftpm/release/CedaNative --metal-snapshot outputs/native-board outputs/native-gpu.png
```

This renders the exported actual mesh into a GPU texture. It is separate evidence from exercising native window controls and from validating PCB numerical or hardware accuracy. See [ADR-002](../../docs/architecture/adr-002-swiftui-macos.md).
