from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import time
from dataclasses import asdict
from datetime import datetime, timezone

import numpy as np

from . import __version__
from .errors import CedaError
from .solver.dc import solve_dc
from .solver.thermal import solve_board_temperature


def analyze(board, config, progress=lambda message: None):
    start = time.monotonic()
    config.validate()
    progress("提取铜几何并生成有限元网格")
    result = solve_dc(board,config)
    refinement = {"status":"not_checked"}
    if config.settings.mesh_refinement:
        from dataclasses import replace
        progress("细化网格，复核负载电压")
        finer = replace(config,settings=replace(config.settings,mesh_size_mm=config.settings.mesh_size_mm/2))
        refined = solve_dc(board,finer)
        changes = [abs(a["voltage_v"]-b["voltage_v"]) for a,b in zip(result.load_results,refined.load_results)]
        drops = []
        for load,item in zip(config.loads,refined.load_results):
            matches = [source.voltage_v for source in config.sources
                       if board.pad(source.positive).net == board.pad(load.positive).net
                       and board.pad(source.negative).net == board.pad(load.negative).net]
            drops.append(abs(matches[0]-item["voltage_v"]) if len(matches) == 1 else 0.0)
        limits = [max(config.settings.voltage_tolerance_v,config.settings.relative_tolerance*drop) for drop in drops]
        passed = all(change <= limit for change,limit in zip(changes,limits))
        refinement = {"status":"pass" if passed else "not_converged","voltage_changes_v":changes,
                      "limits_v":limits,"coarse_nodes":result.diagnostics["nodes"],"fine_nodes":refined.diagnostics["nodes"],
                      "compared_mesh_mm":[config.settings.mesh_size_mm,config.settings.mesh_size_mm/2],
                      "scope":"two DC meshes; not material accuracy or thermal convergence"}
        result = refined
    thermal = None
    if config.settings.thermal_enabled:
        mesh = None
        previous = np.full(len(result.mesh.points),config.settings.ambient_c)
        history = []
        converged = False
        for i in range(config.settings.thermal_iterations):
            progress(f"电热迭代 {i+1}/{config.settings.thermal_iterations}")
            thermal,temperature,mesh = solve_board_temperature(board,config,result,mesh)
            delta = float(np.max(abs(temperature-previous)))
            history.append(delta)
            if delta < config.settings.thermal_tolerance_c:
                converged = True
                break
            previous = 0.5*previous+0.5*temperature
            result = solve_dc(board,config,result.mesh,previous)
        thermal["coupling_status"] = "converged" if converged else "not_converged"
        thermal["iteration_changes_c"] = history
        # DC refinement was performed at ambient temperature, not final hot state.
        refinement["scope"] = "ambient-temperature DC meshes only; thermal mesh not checked"
    for load in result.load_results:
        if refinement["status"] != "pass" or (thermal and thermal["coupling_status"] != "converged"):
            load["verdict"] = "unverified" if load["verdict"] == "pass" else load["verdict"]
    verdict = "fail" if any(l["verdict"] == "fail" for l in result.load_results) else (
        "pass_scoped" if all(l["verdict"] == "pass" for l in result.load_results) else "unverified")
    versions = {}
    for package in ("numpy","scipy","shapely","gmsh"):
        versions[package] = importlib.metadata.version(package)
    encoded_config = json.dumps(config.to_dict(),sort_keys=True,allow_nan=False).encode()
    report = {
        "schema_version":1,"ceda_version":__version__,"timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "elapsed_s":time.monotonic()-start,"platform":platform.platform(),"architecture":platform.machine(),
        "solver_versions":versions,"solver":"2.5D linear triangle FEM / SciPy sparse DC",
        "board":board.summary(),"config":config.to_dict(),"config_sha256":hashlib.sha256(encoded_config).hexdigest(),
        "verdict":verdict,"hardware_verified":False,"physical_accuracy_calibrated":False,
        "loads":result.load_results,"vias":result.via_results,"diagnostics":result.diagnostics,
        "mesh_refinement":refinement,"thermal":thermal,
        "unverified":["芯片功能与固件","上电时序与稳压器控制环路","AC PDN / ESL / 互感 / 高频信号完整性",
                      "封装接触电阻、芯片结温、制造与装配缺陷","原理图与 PCB 网络一致性（需另行提供网表）"],
        "assumptions":["已保存的铺铜作为输入，未重新铺铜或修改原文件。",
                       "源与负载为理想电压源和恒流负载；负载电压相对其本地回流端。",
                       "选定焊盘和过孔环为等电位接触；孔壁电阻按明确给定镀层厚度计算。",
                       "铜电阻率按 20°C 参考值和线性温度系数；未包含粗糙度/趋肤效应。"],
        "mesh":{"points_mm":result.mesh.points.tolist(),"triangles":result.mesh.triangles.tolist(),
                "triangle_keys":[list(k) for k in result.mesh.triangle_keys],
                "voltage_v":result.voltage.tolist(),"current_density_a_mm2":np.linalg.norm(result.current_density_a_mm2,axis=1).tolist(),
                "triangle_loss_w":result.triangle_loss_w.tolist()},
    }
    return report
