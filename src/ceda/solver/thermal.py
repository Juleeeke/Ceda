"""Experimental thickness-averaged board heat spreading, not junction CFD."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree
from shapely import covers, points

from ceda.errors import CedaError
from ceda.model import CopperLayer
from .mesh import build_mesh


def solve_board_temperature(board, config, dc, thermal_mesh=None):
    s = config.settings
    if board.outline is None or not board.board_thickness_mm:
        raise CedaError("热分析需要闭合板框和明确板厚。")
    surrogate = replace(board,layers=[CopperLayer("board",None,None)],pads=[],vias=[],copper={("THERMAL","board"):board.outline})
    mesh = thermal_mesh or build_mesh(surrogate,{"THERMAL"},s.mesh_size_mm,s.max_nodes)
    centroids = mesh.points[mesh.triangles].mean(axis=1)
    tree = cKDTree(centroids)
    sheet_k = np.full(len(mesh.triangles),s.thermal_fr4_k_w_mk*board.board_thickness_mm*1e-3)
    pts = points(centroids)
    layer_thickness = {l.name:s.copper_thickness_mm if s.copper_thickness_mm is not None else l.thickness_mm for l in board.layers}
    all_copper_layers = {layer for _,layer in board.copper}
    if any(layer_thickness[layer] is None for layer in all_copper_layers):
        raise CedaError("热分析需要所有铜层的厚度，不能忽略其他网络的散热铜。")
    for (_,layer),geometry in board.copper.items():
        sheet_k[covers(geometry,pts)] += 400.0*layer_thickness[layer]*1e-3
    local = (sheet_k*mesh.areas_mm2)[:,None,None]*np.einsum("tik,tjk->tij",mesh.gradients_per_mm,mesh.gradients_per_mm)
    # Consistent convection mass on both board faces; area conversion mm²→m².
    h = 2*s.thermal_h_w_m2k
    mass = mesh.areas_mm2[:,None,None]*1e-6*h/12*(np.ones((3,3))+np.eye(3))[None,:,:]
    local += mass
    rows = np.repeat(mesh.triangles,3,axis=1).ravel()
    cols = np.tile(mesh.triangles,(1,3)).ravel()
    matrix = coo_matrix((local.ravel(),(rows,cols)),shape=(len(mesh.points),len(mesh.points))).tocsr()
    element_power = np.zeros(len(mesh.triangles))
    _, nearest = tree.query(dc.mesh.points[dc.mesh.triangles].mean(axis=1))
    np.add.at(element_power,nearest,dc.triangle_loss_w)
    for via in dc.via_results:
        obj = next((v for v in board.vias if v.id == via["id"]),None)
        if obj is None:
            pad = board.pad(via["id"])
            location = (pad.x,pad.y)
        else:
            location = (obj.x,obj.y)
        element_power[tree.query(location)[1]] += via["loss_w"]
    for ref,power in s.component_heat_w.items():
        if ref not in board.components:
            raise CedaError(f"热源器件 {ref} 不在 PCB 中。")
        component = board.components[ref]
        element_power[tree.query((component["x_mm"],component["y_mm"]))[1]] += power
    rhs = np.zeros(len(mesh.points))
    np.add.at(rhs,mesh.triangles.ravel(),np.repeat(element_power/3,3))
    rise = spsolve(matrix,rhs)
    if not np.all(np.isfinite(rise)):
        raise CedaError("热场求解失败。")
    convection_w = float(np.sum(h*mesh.areas_mm2*1e-6*np.mean(rise[mesh.triangles],axis=1)))
    total = float(element_power.sum())
    balance = abs(total-convection_w)/max(total,1e-12)
    if balance > 0.001:
        raise CedaError("热场能量守恒检查未通过。")
    temperatures = rise+s.ambient_c
    _, indices = cKDTree(mesh.points).query(dc.mesh.points)
    return {
        "model":"experimental thickness-averaged 2D board; point component heat; uniform convection",
        "evidence":"engineering_estimate", "junction_temperature_verified":False,
        "points_mm":mesh.points.tolist(), "triangles":mesh.triangles.tolist(),
        "temperatures_c":temperatures.tolist(), "maximum_board_c":float(temperatures.max()),
        "injected_power_w":total,"convection_power_w":convection_w,
        "energy_balance_relative":balance,
        "unmodeled_component_heat":[ref for ref in board.components if ref not in s.component_heat_w],
    }, temperatures[indices], mesh
