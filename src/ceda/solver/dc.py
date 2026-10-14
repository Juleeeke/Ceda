from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import MatrixRankWarning, spsolve
from shapely import covers, points
from shapely.geometry import Point

from ceda.errors import CedaError
from .mesh import Mesh, build_mesh


@dataclass
class DCResult:
    mesh: Mesh
    voltage: np.ndarray
    current_density_a_mm2: np.ndarray
    triangle_loss_w: np.ndarray
    load_results: list[dict]
    via_results: list[dict]
    diagnostics: dict


class Groups:
    def __init__(self, size):
        self.parent = list(range(size))

    def root(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, members):
        if len(members):
            root = self.root(int(members[0]))
            for item in members[1:]:
                self.parent[self.root(int(item))] = root


def solve_dc(board, config, mesh=None, temperatures_c=None):
    config.validate()
    blocking = [i.message for i in board.issues if i.severity == "error"]
    if blocking:
        raise CedaError("导入预检未通过：" + "；".join(blocking))
    terminals = [p for src in config.sources for p in (src.positive,src.negative)]
    terminals += [p for load in config.loads for p in (load.positive,load.negative)]
    nets = {board.pad(p).net for p in terminals}
    if "" in nets:
        raise CedaError("电源或负载焊盘没有网络。")
    if len(board.pads) != len({p.id for p in board.pads}):
        raise CedaError("存在重复焊盘编号（如叠加焊盘），当前端口映射不支持。")
    s = config.settings
    thickness = {l.name: s.copper_thickness_mm if s.copper_thickness_mm is not None else l.thickness_mm for l in board.layers}
    used_layers = {name for net, name in board.copper if net in nets}
    if any(thickness[name] is None or thickness[name] <= 0 for name in used_layers):
        raise CedaError("供电网络所在铜层缺少有效铜厚。请提供全局铜厚或 KiCad 叠层。")
    mesh = mesh or build_mesh(board,nets,s.mesh_size_mm,s.max_nodes)
    groups = Groups(len(mesh.points))
    geometric_points = points(mesh.points)

    def contact(shape, net, layer):
        mask = np.asarray([key == (net,layer) for key in mesh.node_keys])
        nodes = np.flatnonzero(mask & covers(shape.buffer(1e-7), geometric_points))
        if len(nodes) == 0:
            raise CedaError(f"{net}/{layer} 接触区域没有网格节点，请细化网格。")
        groups.union(nodes)
        return int(nodes[0])

    pad_nodes = {}
    for identifier in dict.fromkeys(terminals):
        pad = board.pad(identifier)
        members = [contact(pad.geometry,pad.net,layer) for layer in pad.layers]
        # Plated through-hole contacts are connected by explicit barrels below,
        # not silently shorted across the stack.
        pad_nodes[identifier] = members[0]
    z = {l.name: s.layer_positions_mm.get(l.name,l.z_mm) for l in board.layers}
    vias = []
    for via in board.vias:
        if via.net not in nets:
            continue
        ring = Point(via.x,via.y).buffer(via.diameter_mm/2,quad_segs=32).difference(Point(via.x,via.y).buffer(via.drill_mm/2,quad_segs=32))
        vias.append((via.id,via.net,via.layers,ring,via.drill_mm))
    for pad in board.pads:
        if pad.plated and pad.net in nets and pad.drill_mm:
            vias.append((pad.id,pad.net,pad.layers,pad.geometry,pad.drill_mm))
    links = []
    for identifier,net,layers,shape,drill in vias:
        if s.via_plating_mm is None:
            raise CedaError("供电路径有镀铜孔，必须明确配置孔壁镀铜厚度。")
        if any(z[layer] is None for layer in layers):
            raise CedaError("过孔连接层缺少 Z 位置；请完善叠层或 layer_positions_mm。")
        contacts = [contact(shape,net,layer) for layer in layers]
        for i in range(len(layers)-1):
            length = abs(z[layers[i+1]]-z[layers[i]])*1e-3
            if length <= 0:
                raise CedaError("过孔层位置没有有效间距。")
            plating = s.via_plating_mm * 1e-3
            area = np.pi * ((drill*1e-3/2+plating)**2-(drill*1e-3/2)**2)
            resistance = s.resistivity_ohm_m * length / area
            if temperatures_c is not None:
                resistance *= 1+s.temperature_coefficient*(float(np.mean(temperatures_c))-20)
            links.append((identifier,layers[i],layers[i+1],contacts[i],contacts[i+1],resistance))
    roots = np.asarray([groups.root(i) for i in range(len(mesh.points))])
    _, dof = np.unique(roots,return_inverse=True)
    n = int(dof.max())+1
    element_dofs = dof[mesh.triangles]
    rho = np.full(len(mesh.triangles),s.resistivity_ohm_m)
    # Reference resistivity is specified at 20 °C, even in an uncoupled run.
    temp = np.full(len(mesh.triangles),s.ambient_c) if temperatures_c is None else np.mean(temperatures_c[mesh.triangles],axis=1)
    rho *= 1+s.temperature_coefficient*(temp-20)
    if np.any(rho <= 0):
        raise CedaError("给定温度超出铜电阻率线性模型的适用域。")
    t = np.asarray([thickness[layer]*1e-3 for _,layer in mesh.triangle_keys])
    local = (t/rho*mesh.areas_mm2)[:,None,None] * np.einsum("tik,tjk->tij",mesh.gradients_per_mm,mesh.gradients_per_mm)
    rows = np.repeat(element_dofs,3,axis=1).ravel().tolist()
    cols = np.tile(element_dofs,(1,3)).ravel().tolist()
    vals = local.ravel().tolist()
    for _,_,_,a,b,resistance in links:
        a,b = int(dof[a]),int(dof[b])
        rows.extend([a,a,b,b]); cols.extend([a,b,a,b]); vals.extend([1/resistance,-1/resistance,-1/resistance,1/resistance])
    matrix = coo_matrix((vals,(rows,cols)),shape=(n,n)).tocsr()
    matrix.eliminate_zeros()
    rhs = np.zeros(n)
    fixed = {}
    for source in config.sources:
        for identifier,value in ((source.positive,source.voltage_v),(source.negative,0.0)):
            node = int(dof[pad_nodes[identifier]])
            if node in fixed and abs(fixed[node]-value) > 1e-12:
                raise CedaError("电源约束在同一实际铜节点冲突。")
            fixed[node] = value
    for load in config.loads:
        rhs[dof[pad_nodes[load.positive]]] -= load.current_a
        rhs[dof[pad_nodes[load.negative]]] += load.current_a
    count, labels = connected_components(matrix,directed=False)
    floating = []
    for label in range(count):
        members = np.flatnonzero(labels == label)
        if not any(int(i) in fixed for i in members):
            if np.any(abs(rhs[members]) > 1e-15):
                raise CedaError("负载到电源/回流没有实际导通路径；不能把同名网络当作已连接。")
            fixed[int(members[0])] = 0.0
            floating.append(int(len(members)))
    fixed_nodes = np.array(sorted(fixed),dtype=int)
    free = np.setdiff1d(np.arange(n),fixed_nodes)
    voltage = np.zeros(n)
    voltage[fixed_nodes] = [fixed[int(i)] for i in fixed_nodes]
    with warnings.catch_warnings():
        warnings.simplefilter("error",MatrixRankWarning)
        try:
            if len(free):
                voltage[free] = spsolve(matrix[free][:,free],rhs[free]-matrix[free][:,fixed_nodes]@voltage[fixed_nodes])
        except (MatrixRankWarning,RuntimeError) as exc:
            raise CedaError("DC 矩阵奇异或求解失败，请检查物理连通和端口。") from exc
    if not np.all(np.isfinite(voltage)):
        raise CedaError("DC 求解产生非有限电压。")
    nodal_voltage = voltage[dof]
    gradient = np.einsum("ti,tik->tk",nodal_voltage[mesh.triangles],mesh.gradients_per_mm)*1000
    density = -gradient/rho[:,None]/1e6
    losses = np.sum(gradient**2,axis=1)/rho*t*mesh.areas_mm2*1e-6
    via_results = []
    via_loss = 0.0
    for identifier,la,lb,a,b,resistance in links:
        current = (nodal_voltage[a]-nodal_voltage[b])/resistance
        power = current**2*resistance
        via_loss += power
        via_results.append({"id":identifier,"from_layer":la,"to_layer":lb,"current_a":float(current),"resistance_ohm":float(resistance),"loss_w":float(power)})
    reactions = matrix@voltage-rhs
    residual = float(np.max(abs(reactions[free]))) if len(free) else 0.0
    source_power = float(sum(voltage[i]*reactions[i] for i in fixed))
    load_results = []
    load_power = 0.0
    for load in config.loads:
        supply = float(nodal_voltage[pad_nodes[load.positive]]-nodal_voltage[pad_nodes[load.negative]])
        load_power += supply*load.current_a
        load_results.append({"label":load.label or load.positive,"positive":load.positive,"negative":load.negative,
                             "current_a":load.current_a,"voltage_v":supply,"minimum_voltage_v":load.minimum_voltage_v,
                             "verdict":"unverified" if load.minimum_voltage_v is None else ("pass" if supply >= load.minimum_voltage_v else "fail")})
    conductor_loss = float(losses.sum()+via_loss)
    balance = abs(source_power-load_power-conductor_loss)/max(abs(source_power),1e-12)
    if residual > max(1e-8,sum(l.current_a for l in config.loads)*1e-6) or balance > 0.001:
        raise CedaError(f"数值质量门槛未通过：残差 {residual:g} A，功率不平衡 {balance:.3%}。")
    return DCResult(mesh,nodal_voltage,density,losses,load_results,via_results,
                    {"nodes":len(mesh.points),"degrees_of_freedom":n,"triangles":len(mesh.triangles),
                     "max_residual_a":residual,"source_power_w":source_power,"load_power_w":load_power,
                     "copper_loss_w":float(losses.sum()),"via_loss_w":via_loss,"power_balance_relative":balance,
                     "floating_islands":floating,"contact_model":"equipotential selected pad / via annulus; pin contact resistance excluded"})
