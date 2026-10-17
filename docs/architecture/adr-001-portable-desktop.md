# ADR-001: Qt desktop, independent Python core and solver processes

Status: accepted, 2026-10-14.

## Context

macOS/Apple Silicon first, offline/local, personal/small-team users. Future Windows/Linux portability is required from the outset. Inputs and outputs must be reproducible. Long numerical jobs must not freeze the UI. The starting repository contained only an MIT license.

## Options

| Form | Benefits | Costs |
|---|---|---|
| Swift/AppKit | Excellent native macOS integration | Requires another UI for Windows/Linux |
| Electron or Tauri + Python worker | Web UI ecosystem, cross-platform shell | Adds JS and native/IPC packaging layers before solver validation |
| Qt/PySide6 + Python worker | Cross-platform widgets; direct numerical ecosystem; common schemas and tooling | Native binary dependencies and OS-specific builds; Qt licensing |

## Decision

Use Qt/PySide6 Widgets for the desktop; Python dataclasses/JSON for the core and public artifact contracts; Gmsh/Shapely for constrained copper geometry; SciPy sparse finite-element DC initially; optional ngspice subprocess. Keep `ceda.gui` separate from import, models, solver and reporting. Use a QProcess job with explicit input/output snapshots; the same CLI runs headlessly.

Qt is chosen over Swift to retain one desktop implementation across operating systems. Native filesystem dialogs, `pathlib`, explicit executable argument lists and `shutil.which` replace fixed macOS paths. OS-specific app packaging is isolated in `scripts/build_desktop.py`.

## Numerical route adjustment

The design listed GetDP as a field-solver candidate. The first runnable milestone uses explicit linear triangle finite-element matrices on a Gmsh mesh with analytic regression tests. This keeps the first DC problem small and inspectable while preserving JSON/result boundaries for GetDP/Elmer later. It does not claim industrial solver parity. The thermal implementation is explicitly experimental and thickness averaged; high-accuracy multilayer/package heat remains a later backend.

Contact faces are fragmented into the conductor mesh, since assigning an equipotential pad by an unconstrained point cloud failed the analytic strip test. Copper net names are not used to merge physically disconnected islands. Via barrel resistances are explicit; missing plating/stackup data blocks runs.

## Trade-offs and revisit triggers

- Python suits numerical development but packaging must include shared libraries correctly.
- PySide6/Gmsh license obligations are recorded separately from Ceda's MIT code.
- Initial native-file import does not require a running KiCad instance. IPC linkage is deferred until read-only snapshot analysis is trusted.
- Replace/extend the field backend when multiport AC, professional thermal models or large-board benchmarks justify it. Keep actual case data and validation gates independent of solver selection.
- Avoid silent downgrade: unsupported geometry, missing materials, resource limits, nonconvergence and undefined model scope are explicit.

## Sources

[Qt for Python](https://doc.qt.io/qtforpython-6/), [Gmsh](https://gmsh.info/), [KiCad file format](https://dev-docs.kicad.org/en/file-formats/sexpr-pcb/), [SciPy sparse solvers](https://docs.scipy.org/doc/scipy/reference/sparse.linalg.html), [ngspice](https://ngspice.sourceforge.io/shared.html).

## Follow-up decision (2026-10-17)

The user's request to move the macOS interface to SwiftUI is implemented in [ADR-002](adr-002-swiftui-macos.md). macOS now has a preferred native client, while the independent numerical core and cross-platform artifact contracts remain unchanged. Qt remains a separate client option rather than the macOS native frontend.
