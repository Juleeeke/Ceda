# v0.1 capabilities and evidence boundaries

This release implements the first DC closed loop (P0) and experimental entry points towards P1. It does not complete all first-version system verification requirements from the design.

| Area | Implemented | Limits |
|---|---|---|
| KiCad input | S-expression `.kicad_pcb`, saved fills, tracks/arcs, circle/rect/oval/roundrect pads, circular vias/PTH, stackup | Custom pads, copper graphics, slots/offset drills blocked; blind-via layer pair supported geometrically, not fabrication calibrated |
| Copper geometry | Union of actual conductor regions; holes, narrow necks, rotations; geometric short and board-boundary checks | Saved fill freshness not proven; user must refill/save in KiCad; not full DRC |
| Circuit intent | Optional KiCad XML netlist vs pad nets | Native `.kicad_sch` connectivity/ERC/model import not yet available |
| DC solver | Conforming triangle FEM, explicit barrel resistance, both supply and return, pad-local VDD–GND | Ideal sources, constant current loads, equipotential selected pad contacts; no connectors/VRM control models |
| Quality | Residual, power conservation, physical disconnect failures, two DC mesh levels | Two meshes are a scoped numerical check; no material uncertainty or empirical accuracy guarantee |
| Thermal | Optional steady-state thickness-averaged board heat with copper spreading and relaxed electrical iteration | Experimental estimate; uniform convection, point component heat, no layerwise/package/junction or CFD validation; no thermal mesh refinement |
| Transient | Optional ngspice RC startup/load step using extracted single-port loop R | One source / one load only; no inductance, multiport effects, chip/VRM startup verification |
| Desktop | Import, per-layer copper/field view, selectable pads, source/load editing, multiple loads, subprocess job/cancel, configuration and report export | One source in GUI; detailed thermal settings via JSON; no IPC editor integration yet |
| Portability | Python/Qt core, per-platform build script and three-OS CI definition | Only local macOS ARM execution is verified in this development session; remote CI has not been run |

`pass_scoped` means only the configured DC minimum-voltage criteria passed and the required mesh check passed. It never means the board is safe to manufacture in every scenario. No minimum threshold gives `unverified`; failed mesh refinement cannot produce a pass. `hardware_verified` and `physical_accuracy_calibrated` are currently false.

Voltage sources clamp configured positive pads to specified V and negative pads to zero. Multiple independent sources are available via JSON/CLI; contradictory constraints fail. PTH external ports connect on the first listed copper layer; the shaft resistance connects the remaining layers. Source physical placement and contact assumptions must be appropriate to the real assembly.

Copper reference resistivity defaults to 1.724e-8 Ω·m at 20°C and temperature coefficient 0.00393 /°C, visible in the scenario. Copper thickness comes from the KiCad stackup or an explicit override. Via plating is never silently inferred. Thermal copper conductivity is currently a fixed 400 W/(m·K) modeling assumption.

The synthetic demo is intentionally a model/solver example. Reference-board and measured-error calibration remain required before professional accuracy claims. Tests cover analytic strip/loop resistance, via barrel resistance, missing material, disconnected copper, geometry holes/rotations, power and thermal energy conservation, reproducibility, optional ngspice and desktop worker execution.
