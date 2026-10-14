"""Optional ngspice transient bridge with an explicit single-port DC boundary."""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import numpy as np

from .errors import CedaError


def executable():
    return shutil.which("ngspice")


def run_transient(report, output, capacitance_f=10e-6, esr_ohm=0.05, ramp_s=0.001, duration_s=0.01):
    if len(report["config"]["sources"]) != 1 or len(report["loads"]) != 1:
        raise CedaError("瞬态桥接当前只支持单电源、单负载；多负载需多端口提取，不能等效成独立电阻。")
    for value,label in ((capacitance_f,"电容"),(esr_ohm,"ESR"),(ramp_s,"上电时间"),(duration_s,"仿真时长")):
        if not math.isfinite(value) or value <= 0:
            raise CedaError(f"{label} 必须为正的有限值。")
    if duration_s <= ramp_s*3:
        raise CedaError("仿真时长需要大于上电时间的 3 倍。")
    program = executable()
    if not program:
        raise CedaError("未找到 ngspice。macOS 可通过 Homebrew 安装；Windows/Linux 在 PATH 配置求解器。")
    source = report["config"]["sources"][0]
    load = report["loads"][0]
    loop_r = (source["voltage_v"]-load["voltage_v"])/load["current_a"]
    if not math.isfinite(loop_r) or loop_r <= 0:
        raise CedaError("不能从当前端口提取正的布局环路电阻。")
    output = Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    netlist = output / "layout-transient.cir"
    # Relative output names avoid quoting arbitrary user paths in SPICE syntax.
    text = f"""Ceda single-port extracted DC loop + explicit RC load
* Valid only for low-frequency resistive layout; no inductance/VRM model.
Vinput vin 0 PWL(0 0 {ramp_s:.12g} {source['voltage_v']:.12g})
Rlayout vin vload {loop_r:.12g}
Rdecap vload cap {esr_ohm:.12g}
Cdecap cap 0 {capacitance_f:.12g} IC=0
Iload vload 0 PWL(0 0 {ramp_s*2:.12g} 0 {ramp_s*2+duration_s/1000:.12g} {load['current_a']:.12g})
.control
set wr_singlescale
set wr_vecnames
tran {duration_s/2000:.12g} {duration_s:.12g} uic
wrdata waveform.txt v(vin) v(vload)
quit
.endc
.end
"""
    netlist.write_text(text,encoding="utf-8")
    try:
        process = subprocess.run([program,"-b",netlist.name],cwd=output,capture_output=True,text=True,timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise CedaError("ngspice 超过 120 秒预算，已终止。") from exc
    (output/"ngspice.log").write_text(process.stdout+process.stderr,encoding="utf-8")
    wave_path = output/"waveform.txt"
    if process.returncode or not wave_path.is_file():
        raise CedaError("ngspice 未生成有效波形；请查看 ngspice.log。")
    values = np.loadtxt(wave_path,skiprows=1)
    if values.ndim != 2 or values.shape[1] != 3 or not np.all(np.isfinite(values)) or values[-1,0] < duration_s*0.99:
        raise CedaError("ngspice 波形不完整或非有限。")
    np.savetxt(output/"waveform.csv",values,delimiter=",",header="time_s,input_v,load_v",comments="")
    return {"status":"success","evidence":"explicit RC model / layout DC loop; not device startup verification",
            "loop_resistance_ohm":loop_r,"capacitance_f":capacitance_f,"esr_ohm":esr_ohm,
            "samples":len(values),"final_load_v":float(values[-1,2]),"minimum_after_step_v":float(values[values[:,0] >= ramp_s*2,2].min()),
            "waveform_csv":str(output/"waveform.csv"),"netlist":str(netlist)}
