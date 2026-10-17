# ADR-002: SwiftUI macOS client with an independent portable engine

Status: accepted, 2026-10-17. Supersedes the macOS UI decision in ADR-001 following the user's explicit request to move into SwiftUI. The numerical architecture in ADR-001 remains in force.

## Decision

Use SwiftUI for the macOS application, SwiftUI Canvas for the 2D PCB, and MetalKit for real 3D geometry. The host does not embed Qt widgets, a web page or a Python UI. Swift package sources are under `native/macos`. MetalKit is hosted through NSViewRepresentable for the GPU surface and native mouse input, while the application layout, navigation, forms, results and diagnostics are SwiftUI.

Keep the Python import/model/solver/report implementation as an independent, bundled CLI process. This preserves the tested numerical route and future Windows/Linux clients. Existing Qt sources remain available for those clients; they are not part of the macOS SwiftUI frontend. The native worker excludes `ceda.gui`, QtWidgets, QtQuick and QtQuick3D. QtGui/Core remain in the engine solely for the existing 3D silk-font outline helper; this dependency does not create the desktop interface.

Apple has deprecated SceneKit, so the new renderer uses MetalKit directly. The source-based Metal shader is compiled at runtime by Metal; a full Xcode/Metal compiler installation is not needed for this build. SwiftPM plus the installed Command Line Tools are sufficient. Primary references: [MTKView](https://developer.apple.com/documentation/metalkit/mtkview/), [Apple's SceneKit migration guidance](https://developer.apple.com/videos/play/wwdc2025/288/).

## Contracts and process ownership

- `native-export PCB --output DIR` writes versioned `board.json`: actual source outline/rings, copper, tracks, pads, drills, silk graphics/text, layer/port metadata and SHA256. Polygon holes remain separate rings.
- `native-mesh PCB --output DIR [--model-library DIR]` writes `mesh.json` and a 40-byte little-endian Float32 vertex stream (position xyz, normal xyz, color rgb, category). Coordinates are millimetres in the existing `(x, -pcb_y, z)` frame, centered using `center_mm` in metadata. Mesh identity includes the source PCB hash.
- The native client validates schema versions, finite coordinates, binary size, stride and source hash before drawing. Unknown protocol versions or incomplete files are errors.
- Solver jobs use existing `worker --config --output` JSON/report contracts. `--expected-board-sha` prevents a source file changed after import from silently becoming a different simulation input.
- Swift Process arguments are explicit, never shell concatenation. Stdout/stderr are read incrementally from local temporary files, so long logs cannot fill a pipe and freeze the UI. Each job owns its child process and cancellation state.
- STEP conversion remains isolated. Cancellation/exit cleans up the owned STEP subprocess. No arbitrary external processes are terminated.
- Worker paths come from the app bundle; development mode can discover `.venv` relative to a repository or `CEDA_PROJECT_ROOT`. There is no embedded absolute developer path in the binary.

## Packaging and scope

`python scripts/build_macos.py` builds `dist/Ceda SwiftUI.app`, including the Swift executable, generated Ceda icon, demo and a standalone `CedaEngine` directory. It preserves the older local `dist/Ceda.app` artifact. The app is a locally signed development build, not a notarized public release. Each architecture must be built and verified separately.

The first native client supports PCB import, layer display, 2D pan/zoom/port inspection, actual 3D mesh/model display with orbit/pan/zoom, single-source/multiple-load configuration, configuration import/export, solver run/cancel, current/voltage overlays, result verdicts, diagnostics and report export. Settings not edited by the form are retained in imported JSON, including advanced thermal settings; the experimental temperature map has not been added to the native viewport yet and can still be inspected in the generated report.

The native view does not add semiconductor behavior, improve numerical accuracy by changing frameworks, or certify real hardware. Missing models and unsupported geometry remain explicit. 3D view material colors and font approximation retain the limits documented in `03_真实PCB呈现与KiCad参考.md`. The native 3D surface is for inspection; selecting a solver pad is currently done in 2D or in the form.
