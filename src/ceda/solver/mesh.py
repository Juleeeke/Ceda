from __future__ import annotations

from dataclasses import dataclass

import gmsh
import numpy as np
from shapely.geometry import Point, Polygon

from ceda.errors import CedaError


@dataclass
class Mesh:
    points: np.ndarray
    triangles: np.ndarray
    triangle_keys: list[tuple[str, str]]
    node_keys: list[tuple[str, str]]
    areas_mm2: np.ndarray
    gradients_per_mm: np.ndarray


def build_mesh(board, nets, size, max_nodes):
    gmsh.initialize([], readConfigFiles=False, run=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", size / 8)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.model.add("ceda-copper")
        surfaces = []

        def add_surface(polygon,z):
            loops = []
            for ring in [polygon.exterior,*polygon.interiors]:
                coords = list(ring.coords)[:-1]
                vertices = [gmsh.model.occ.addPoint(x,y,z) for x,y in coords]
                lines = [gmsh.model.occ.addLine(vertices[i],vertices[(i+1)%len(vertices)]) for i in range(len(vertices))]
                loops.append(gmsh.model.occ.addCurveLoop(lines))
            return gmsh.model.occ.addPlaneSurface(loops)

        for layer_index, layer in enumerate(board.layers):
            for (net, name), geometry in board.copper.items():
                if net not in nets or name != layer.name:
                    continue
                polygons = [geometry] if isinstance(geometry, Polygon) else list(geometry.geoms)
                for polygon in polygons:
                    if polygon.area <= 1e-10:
                        continue
                    tag = add_surface(polygon,layer_index)
                    contacts = [p.geometry for p in board.pads if p.net == net and name in p.layers]
                    contacts.extend(Point(v.x,v.y).buffer(v.diameter_mm/2,quad_segs=32).difference(Point(v.x,v.y).buffer(v.drill_mm/2,quad_segs=32))
                                    for v in board.vias if v.net == net and name in v.layers)
                    tools = []
                    for shape in contacts:
                        intersection = shape.intersection(polygon)
                        if intersection.area <= 1e-10 or intersection.equals(polygon):
                            continue
                        parts = [intersection] if isinstance(intersection,Polygon) else list(intersection.geoms)
                        for part in parts:
                            if isinstance(part,Polygon) and part.area > 1e-10:
                                tools.append((2,add_surface(part,layer_index)))
                    # Fragment contact faces into the copper surface so that
                    # Dirichlet/equipotential boundaries align with mesh edges.
                    entities = gmsh.model.occ.fragment([(2,tag)],tools)[0] if tools else [(2,tag)]
                    for dimension,new_tag in entities:
                        if dimension == 2:
                            surfaces.append((new_tag,(net,name),polygon,layer_index))
        gmsh.model.occ.synchronize()
        gmsh.model.mesh.setSize(gmsh.model.getEntities(0),size)
        gmsh.model.mesh.generate(2)
        tags, coordinates, _ = gmsh.model.mesh.getNodes()
        if len(tags) > max_nodes:
            raise CedaError(f"网格产生 {len(tags):,} 个节点，超过预算 {max_nodes:,}；请调整网格或预算。未静默降精度。")
        points = np.asarray(coordinates).reshape(-1,3)[:,:2]
        index = {int(tag): i for i, tag in enumerate(tags)}
        triangles, keys = [], []
        node_keys = [None] * len(tags)
        for tag, key, _, _ in surfaces:
            element_types, _, node_groups = gmsh.model.mesh.getElements(2, tag)
            for kind, nodes in zip(element_types, node_groups):
                if kind != 2:
                    raise CedaError("网格包含非线性三角形，当前求解器不支持。")
                group = [[index[int(n)] for n in tri] for tri in np.asarray(nodes).reshape(-1,3)]
                triangles.extend(group)
                keys.extend([key] * len(group))
                for tri in group:
                    for n in tri:
                        node_keys[n] = key
        triangles = np.asarray(triangles, dtype=int)
        if not len(triangles):
            raise CedaError("指定的供电网络没有可求解铜区域。")
        xy = points[triangles]
        twice = (xy[:,1,0]-xy[:,0,0])*(xy[:,2,1]-xy[:,0,1]) - (xy[:,2,0]-xy[:,0,0])*(xy[:,1,1]-xy[:,0,1])
        areas = abs(twice)/2
        if np.any(areas < 1e-14):
            raise CedaError("网格含退化三角形。")
        gradients = np.empty((len(triangles),3,2))
        gradients[:,:,0] = np.stack([xy[:,1,1]-xy[:,2,1],xy[:,2,1]-xy[:,0,1],xy[:,0,1]-xy[:,1,1]],axis=1)/twice[:,None]
        gradients[:,:,1] = np.stack([xy[:,2,0]-xy[:,1,0],xy[:,0,0]-xy[:,2,0],xy[:,1,0]-xy[:,0,0]],axis=1)/twice[:,None]
        return Mesh(points, triangles, keys, node_keys, areas, gradients)
    except CedaError:
        raise
    except Exception as exc:
        raise CedaError(f"铜几何网格失败：{exc}") from exc
    finally:
        gmsh.finalize()
