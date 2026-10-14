from dataclasses import replace

import numpy as np
import pytest
from shapely.geometry import Point,box

from ceda.errors import CedaError
from ceda.model import CopperLayer,Pad,Via
from ceda.solver import solve_dc


def test_uniform_copper_matches_analytic_loop(board,config):
    copper = dict(board.copper)
    copper[("+3V3","F.Cu")] = box(5,5,35,7)
    board = replace(board,copper=copper)
    result = solve_dc(board,config)
    # Full-width source/load contact pads end at x=7 and x=33: length=26 mm.
    expected_r = 1.724e-8*0.026/(0.035e-3)*(1/0.002+1/0.004)
    expected_voltage = 3.3-config.loads[0].current_a*expected_r
    assert result.load_results[0]["voltage_v"] == pytest.approx(expected_voltage,abs=1e-7)
    assert result.diagnostics["copper_loss_w"] == pytest.approx(config.loads[0].current_a**2*expected_r,rel=1e-4)
    assert result.diagnostics["power_balance_relative"] < 1e-8


def test_neck_causes_more_drop_than_wide_copper(board,config):
    neck = solve_dc(board,config)
    wide = solve_dc(replace(board,copper={**board.copper,("+3V3","F.Cu"):box(5,5,35,7)}),config)
    # 4 mm at 0.3 mm rather than 2 mm adds >2 mV at the specified 0.5 A.
    assert neck.load_results[0]["voltage_v"] < wide.load_results[0]["voltage_v"]-0.002
    assert np.linalg.norm(neck.current_density_a_mm2,axis=1).max() > np.linalg.norm(wide.current_density_a_mm2,axis=1).max()


def test_disconnected_same_net_rejected(board,config):
    copper = dict(board.copper)
    copper[("+3V3","F.Cu")] = box(5,5,18,7).union(box(22,5,35,7))
    with pytest.raises(CedaError,match="实际导通"):
        solve_dc(replace(board,copper=copper),config)


def test_missing_material_rejected(board,config):
    board = replace(board,layers=[CopperLayer("F.Cu",None,None),board.layers[1]])
    with pytest.raises(CedaError,match="铜厚"):
        solve_dc(board,config)


def test_node_budget_never_silently_coarsens(board,config):
    config.settings.max_nodes = 100
    with pytest.raises(CedaError,match="超过预算"):
        solve_dc(board,config)


def test_local_ground_potential_included(board,config):
    result = solve_dc(board,config)
    ground_indices = [i for i,key in enumerate(result.mesh.node_keys) if key == ("GND","F.Cu")]
    assert result.voltage[ground_indices].max() > 0.001
    assert result.load_results[0]["voltage_v"] < result.voltage.max()


def test_via_barrels_match_resistance(board,config):
    positive = Point(8,6).buffer(0.6,quad_segs=32).difference(Point(8,6).buffer(0.15,quad_segs=32))
    negative = Point(8,14).buffer(0.6,quad_segs=32).difference(Point(8,14).buffer(0.15,quad_segs=32))
    pads = [Pad("J1.1","J1","1","+3V3",["F.Cu"],positive,8,6),Pad("J1.2","J1","2","GND",["F.Cu"],negative,8,14),
            Pad("U1.1","U1","1","+3V3",["B.Cu"],positive,8,6),Pad("U1.2","U1","2","GND",["B.Cu"],negative,8,14)]
    vias = [Via("vp","+3V3",["F.Cu","B.Cu"],8,6,1.2,0.3),Via("vn","GND",["F.Cu","B.Cu"],8,14,1.2,0.3)]
    board = replace(board,pads=pads,vias=vias,copper={(net,layer):shape for net,shape in [("+3V3",positive),("GND",negative)] for layer in ["F.Cu","B.Cu"]})
    config.settings.via_plating_mm = 0.025
    result = solve_dc(board,config)
    r = 1.724e-8*0.001565/(np.pi*((0.00015+0.000025)**2-0.00015**2))
    assert result.load_results[0]["voltage_v"] == pytest.approx(3.3-2*r*0.5,abs=1e-8)
    assert len(result.via_results) == 2
    assert all(abs(v["current_a"]) == pytest.approx(0.5,rel=1e-7) for v in result.via_results)
