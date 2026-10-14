# Development milestones

- v0.1 / P0: portable desktop, saved KiCad copper, DC source and local return, conforming mesh, diagnostics, reporting. This is the first implementation, not all of P1.
- P0 hardening: verified real KiCad boards, all common pad/copper primitives, fill freshness/IPC read-only adapter, per-terminal contact layer selection, large-board budgets, manufactured reference coupons.
- P1 electrical: validated multiport RLC extraction, source impedance and protection parts, model library/pin mapping, DC-DC/LDO behavior, native schematic mapping, enable/reset/power-good timing, analog/ADC and interface test benches.
- P1 thermal: layered 2.5D/3D backend via GetDP/Elmer, package/board contacts, material sensitivities, heat-source uncertainty, mesh/time-step convergence and measured temperatures.
- P2: Renode synchronization, advanced SI/PI, openEMS critical structures, other CAD formats.

Before claiming P1 complete, run the B01–B08 benchmarks from the original design with model coverage and measured-reference evidence. Any unmodeled block remains unverified. Current macOS tests do not imply Windows/Linux are tested; CI is configured to establish that evidence when dispatched.
