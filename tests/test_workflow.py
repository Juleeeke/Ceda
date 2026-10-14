import hashlib
import json
import shutil

import numpy as np
import pytest

from ceda.analysis import analyze
from ceda.config import AnalysisConfig
from ceda.errors import CedaError
from ceda.netlist import compare_netlist
from ceda.report import write_report
from ceda.resources import demo_config
from ceda.spice import run_transient


@pytest.mark.parametrize("value",[float("nan"),float("inf"),0,-1])
def test_invalid_current_rejected(value):
    data = json.loads(demo_config().read_text())
    data["loads"][0]["current_a"] = value
    with pytest.raises(CedaError):
        AnalysisConfig.from_dict(data)


def test_refinement_and_report_provenance(board,config,tmp_path):
    config.settings.mesh_refinement = True
    report = analyze(board,config)
    assert report["mesh_refinement"]["status"] == "pass"
    assert report["verdict"] == "fail"
    assert report["hardware_verified"] is False
    path = write_report(board,report,tmp_path/"run")
    assert path.is_file()
    assert hashlib.sha256((path.parent/"input.kicad_pcb").read_bytes()).hexdigest() == board.sha256
    data = json.loads((path.parent/"result.json").read_text())
    assert data["board"]["sha256"] == board.sha256
    assert "芯片功能" in path.read_text()


def test_disabled_refinement_cannot_produce_pass(board,config):
    config.loads[0].minimum_voltage_v = 3.0
    report = analyze(board,config)
    assert report["verdict"] == "unverified"
    assert report["loads"][0]["verdict"] == "unverified"


def test_thermal_energy_and_evidence(board,config):
    config.settings.thermal_enabled = True
    config.settings.thermal_h_w_m2k = 10
    config.settings.thermal_fr4_k_w_mk = 0.3
    config.settings.component_heat_w = {"U1":0.1}
    config.settings.thermal_iterations = 20
    report = analyze(board,config)
    heat = report["thermal"]
    assert heat["maximum_board_c"] > config.settings.ambient_c
    assert heat["energy_balance_relative"] < 1e-8
    assert heat["junction_temperature_verified"] is False
    assert heat["evidence"] == "engineering_estimate"
    assert heat["coupling_status"] == "converged"


def test_netlist_mismatch_detected(board,tmp_path):
    path = tmp_path/"net.xml"
    path.write_text('<export><nets><net name="WRONG"><node ref="U1" pin="1"/></net></nets></export>')
    comparison = compare_netlist(board,path)
    assert comparison["status"] == "fail"
    assert any(d["status"] == "net_mismatch" for d in comparison["differences"])


@pytest.mark.skipif(shutil.which("ngspice") is None,reason="ngspice optional")
def test_ngspice_layout_bridge_reaches_extracted_dc(board,config,tmp_path):
    report = analyze(board,config)
    result = run_transient(report,tmp_path)
    assert result["samples"] > 100
    assert result["final_load_v"] == pytest.approx(report["loads"][0]["voltage_v"],abs=1e-5)
    waveform = np.loadtxt(tmp_path/"waveform.csv",delimiter=",",skiprows=1)
    assert waveform[0,2] < 0.05
    assert waveform[-1,2] > 3
