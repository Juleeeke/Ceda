from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union

from ceda.errors import CedaError
from ceda.model import Board, CopperLayer, Issue, Pad, Via
from .sexpr import child, children, number, parse


def xy(node, key):
    item = child(node, key)
    if item is None or len(item) < 3:
        raise CedaError(f"几何对象缺少 {key} 坐标。")
    return float(item[1]), float(item[2])


def arc_points(start, mid, end, tolerance=0.01):
    a, b, c = np.array([start, mid, end], dtype=float)
    matrix = 2 * np.array([b - a, c - a])
    if abs(np.linalg.det(matrix)) < 1e-12:
        raise CedaError("圆弧的三个点共线，无法提取。")
    center = np.linalg.solve(matrix, [b @ b - a @ a, c @ c - a @ a])
    radius = float(np.linalg.norm(a - center))
    angles = [math.atan2(*(p - center)[::-1]) for p in (a, b, c)]
    sweep = (angles[2] - angles[0]) % (2 * math.pi)
    if (angles[1] - angles[0]) % (2 * math.pi) > sweep:
        sweep -= 2 * math.pi
    step = min(math.pi / 24, 2 * math.acos(max(-1, 1 - tolerance / radius)))
    count = max(3, math.ceil(abs(sweep) / max(step, 1e-5)) + 1)
    points = [(center + radius * np.array([math.cos(t), math.sin(t)])).tolist()
              for t in np.linspace(angles[0], angles[0] + sweep, count)]
    # Retain exact serialized endpoints so adjoining Edge.Cuts form a closed ring.
    points[0], points[-1] = list(start), list(end)
    return points


def polygon_points(node):
    pts = child(node, "pts")
    if pts is None:
        raise CedaError("铜多边形缺少 pts。")
    result = []
    for item in pts[1:]:
        if item[0] == "xy":
            result.append((float(item[1]), float(item[2])))
        elif item[0] == "arc":
            result.extend(arc_points(xy(item, "start"), xy(item, "mid"), xy(item, "end")))
        else:
            raise CedaError(f"尚不支持多边形顶点类型 {item[0]}。")
    shape = Polygon(result)
    if not shape.is_valid:
        # KiCad represents holes using zero-width bridges. Only accept a repair
        # when it preserves area; any other invalid geometry is rejected.
        fixed = shape.buffer(0)
        if fixed.is_empty or abs(fixed.area - shape.area) > max(1e-8, shape.area * 1e-8):
            raise CedaError("铜多边形无效，不能保证修复保留几何。请在 KiCad 重新铺铜。")
        shape = fixed
    return shape


def transform(shape, x, y, rotation):
    return affinity.translate(affinity.rotate(shape, -rotation, origin=(0, 0)), x, y)


def pad_shape(node):
    w, h = xy(node, "size")
    if w <= 0 or h <= 0:
        raise CedaError("焊盘尺寸必须大于 0。")
    kind = node[3]
    if kind == "custom":
        from .presentation import graphic_shape
        primitives = child(node, "primitives")
        if not primitives:
            raise CedaError("尚不支持缺少 primitives 的 custom 焊盘。")
        anchor = child(child(node, "options", ["options"]), "anchor", ["anchor", "circle"])[1]
        shapes = [box(-w/2,-h/2,w/2,h/2) if anchor == "rect" else Point(0,0).buffer(w/2,quad_segs=32)]
        shapes.extend(graphic_shape(p) for p in primitives[1:] if isinstance(p,list))
        return unary_union(shapes)
    if kind == "circle":
        return Point(0, 0).buffer(w / 2, quad_segs=32)
    if kind in {"rect", "roundrect"}:
        radius = min(w, h) * number(node, "roundrect_rratio", 0.25) if kind == "roundrect" else 0
        return box(-w / 2 + radius, -h / 2 + radius,
                   w / 2 - radius, h / 2 - radius).buffer(radius, quad_segs=16) if radius else box(-w/2, -h/2, w/2, h/2)
    if kind == "oval":
        if w >= h:
            return LineString([(-(w-h)/2, 0), ((w-h)/2, 0)]).buffer(h/2, quad_segs=32)
        return LineString([(0, -(h-w)/2), (0, (h-w)/2)]).buffer(w/2, quad_segs=32)
    raise CedaError(f"尚不支持 {kind} 焊盘，不能跳过铜几何。")


def load_board(path: str | Path) -> Board:
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
        root = parse(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError) as exc:
        raise CedaError(f"无法读取 PCB 文件：{exc}") from exc
    if not root or root[0] != "kicad_pcb":
        raise CedaError("请选择 KiCad .kicad_pcb 文件。")
    layer_defs = child(root, "layers", [])
    layer_names = [entry[1] for entry in layer_defs[1:]
                   if isinstance(entry, list) and len(entry) > 1 and entry[1].endswith(".Cu")]
    if not layer_names:
        raise CedaError("PCB 没有铜层定义。")
    issues = []
    stackup = child(child(root, "setup", ["setup"]), "stackup", ["stackup"])
    stack_layers = {}
    z = 0.0
    for entry in children(stackup, "layer"):
        thickness = number(entry, "thickness")
        if entry[1] in layer_names:
            stack_layers[entry[1]] = (thickness, z + thickness / 2 if thickness is not None else None)
        if thickness is not None:
            z += thickness
    layers = [CopperLayer(name, *stack_layers.get(name, (None, None))) for name in layer_names]
    for layer in layers:
        if layer.thickness_mm is None:
            issues.append(Issue("missing_copper_thickness", "warning", f"{layer.name} 缺少铜厚，分析时必须明确提供。"))
    nets = {int(entry[1]): entry[2] for entry in children(root, "net") if len(entry) > 2}

    def net_name(node):
        item = child(node, "net")
        if item is None:
            return ""
        return item[2] if len(item) > 2 else nets.get(int(item[1]), "")

    pieces = defaultdict(list)
    pads, vias, components = [], [], {}
    drill_cuts = []
    for footprint in children(root, "footprint"):
        props = {p[1]: p[2] for p in children(footprint, "property") if len(p) > 2}
        ref = props.get("Reference")
        if ref is None:
            ref_node = next((t for t in children(footprint, "fp_text") if t[1] == "reference"), None)
            ref = ref_node[2] if ref_node else "?"
        if ref in components:
            raise CedaError(f"重复器件位号 {ref}。")
        origin = xy(footprint, "at")
        at = child(footprint, "at")
        rotation = float(at[3]) if len(at) > 3 else 0
        components[ref] = {"value": props.get("Value", ""), "footprint": footprint[1], "x_mm": origin[0], "y_mm": origin[1]}
        for graphic in footprint[1:]:
            if isinstance(graphic, list) and str(graphic[0]).startswith("fp_"):
                layer = child(graphic, "layer", ["layer", ""])[1]
                if layer.endswith(".Cu"):
                    raise CedaError(f"{ref} 含未支持的封装铜图形 {graphic[0]}，请先转换成受支持的铜对象。")
        for node in children(footprint, "pad"):
            if node[2] == "np_thru_hole":
                local = xy(node, "at")
                theta = math.radians(-rotation)
                px = origin[0]+local[0]*math.cos(theta)-local[1]*math.sin(theta)
                py = origin[1]+local[0]*math.sin(theta)+local[1]*math.cos(theta)
                drill = child(node,"drill")
                from .presentation import drill_shape
                pad_at = child(node,"at")
                angle = float(pad_at[3]) if len(pad_at)>3 else 0
                hole = drill_shape(node,px,py,angle)
                if hole is None:
                    raise CedaError("非镀铜孔必须有钻孔定义。")
                drill_cuts.append((hole,layer_names))
                continue
            local = xy(node, "at")
            pad_at = child(node, "at")
            angle = float(pad_at[3]) if len(pad_at) > 3 else 0
            theta = math.radians(-rotation)
            px = origin[0] + local[0]*math.cos(theta) - local[1]*math.sin(theta)
            py = origin[1] + local[0]*math.sin(theta) + local[1]*math.cos(theta)
            # KiCad serializes pad angle in the board frame, not the footprint frame.
            shape = transform(pad_shape(node), px, py, angle)
            layers_token = child(node, "layers", ["layers"])[1:]
            pad_layers = list(layer_names) if "*.Cu" in layers_token else [n for n in layer_names if n in layers_token]
            if not pad_layers:
                continue
            drill = child(node, "drill")
            drill_mm = None
            if drill is not None:
                if drill[1] == "oval" or child(drill, "offset") is not None:
                    raise CedaError(f"{ref}.{node[1]} 使用槽孔/偏心孔，第一版暂不支持其镀层建模。")
                drill_mm = float(drill[1])
                hole = Point(px, py).buffer(drill_mm/2, quad_segs=32)
                shape = shape.difference(hole)
                drill_cuts.append((hole,layer_names))
            pad = Pad(f"{ref}.{node[1]}", ref, node[1], net_name(node), pad_layers, shape, px, py, drill_mm, node[2] == "thru_hole")
            pads.append(pad)
            for layer in pad_layers:
                pieces[(pad.net, layer)].append(shape)
    tracks = []
    for node in children(root, "segment") + children(root, "arc"):
        layer = child(node, "layer")[1]
        if layer not in layer_names:
            continue
        start, end = xy(node, "start"), xy(node, "end")
        coords = arc_points(start, xy(node, "mid"), end) if node[0] == "arc" else [start, end]
        width = number(node, "width")
        if width is None or width <= 0:
            raise CedaError("铜走线宽度无效。")
        geometry = LineString(coords).buffer(width/2, quad_segs=16)
        pieces[(net_name(node), layer)].append(geometry)
        tracks.append({"net":net_name(node),"layer":layer,"geometry":geometry,"width_mm":width})
    for index, node in enumerate(children(root, "via")):
        x, y = xy(node, "at")
        diameter, drill = number(node, "size"), number(node, "drill")
        if drill is None or diameter is None or not 0 < drill < diameter:
            raise CedaError("过孔尺寸无效。")
        pair = child(node, "layers")[1:]
        if len(pair) != 2 or any(p not in layer_names for p in pair):
            raise CedaError("无法识别过孔层对。")
        indices = sorted(layer_names.index(p) for p in pair)
        connected = layer_names[indices[0]:indices[1]+1]
        identifier = child(node, "uuid", ["uuid", f"via-{index}"])[1]
        via = Via(identifier, net_name(node), connected, x, y, diameter, drill)
        vias.append(via)
        ring = Point(x, y).buffer(diameter/2, quad_segs=32).difference(Point(x, y).buffer(drill/2, quad_segs=32))
        for layer in connected:
            pieces[(via.net, layer)].append(ring)
        drill_cuts.append((Point(x,y).buffer(drill/2,quad_segs=32),connected))
    for zone in children(root, "zone"):
        if child(zone, "keepout") is not None:
            continue
        zone_layers = child(zone, "layers") or child(zone, "layer", ["layer"])
        if not any(n in layer_names for n in zone_layers[1:]):
            continue
        fills = children(zone, "filled_polygon")
        if not fills:
            issues.append(Issue("unfilled_zone", "error", "存在没有已保存铺铜结果的铜区；请在 KiCad 铺铜并保存后再分析。"))
        for fill in fills:
            layer = child(fill, "layer", child(zone, "layer", ["layer", ""]))[1]
            if layer not in layer_names:
                raise CedaError("无法识别铺铜所属层。")
            pieces[(net_name(zone), layer)].append(polygon_points(fill))
    edges = []
    for node in root[1:]:
        if not isinstance(node, list):
            continue
        layer = child(node, "layer", ["layer", ""])[1]
        if layer.endswith(".Cu") and str(node[0]).startswith("gr_"):
            raise CedaError(f"尚不支持板上铜图形 {node[0]}，不能忽略其电气连接。")
        if layer != "Edge.Cuts":
            continue
        if node[0] == "gr_rect":
            p1, p2 = xy(node, "start"), xy(node, "end")
            edges.append(box(min(p1[0],p2[0]),min(p1[1],p2[1]),max(p1[0],p2[0]),max(p1[1],p2[1])).boundary)
        elif node[0] == "gr_line":
            edges.append(LineString([xy(node,"start"), xy(node,"end")]))
        elif node[0] == "gr_arc":
            edges.append(LineString(arc_points(xy(node,"start"),xy(node,"mid"),xy(node,"end"))))
        elif node[0] == "gr_circle":
            center, end = xy(node, "center"), xy(node, "end")
            edges.append(Point(center).buffer(math.dist(center,end),quad_segs=64).boundary)
        else:
            issues.append(Issue("unsupported_outline", "error", f"未支持的板框对象 {node[0]}。"))
    polygons = list(polygonize(unary_union(edges))) if edges else []
    outline = None
    if polygons:
        # Symmetric difference preserves nested cutouts instead of filling them.
        outline = Polygon(polygons[0].exterior)
        for polygon in polygons[1:]:
            outline = outline.symmetric_difference(Polygon(polygon.exterior))
    else:
        issues.append(Issue("missing_outline", "error", "板框缺失或没有闭合。"))
    copper = {key: unary_union(value) for key, value in pieces.items()}
    for key,geometry in copper.items():
        holes = [shape for shape,cut_layers in drill_cuts if key[1] in cut_layers]
        if holes:
            copper[key] = geometry.difference(unary_union(holes))
    for (net, layer), shape in copper.items():
        if not net:
            issues.append(Issue("unassigned_copper", "warning", f"{layer} 存在未分配网络的铜。"))
        if outline is not None and shape.difference(outline.buffer(1e-6)).area > 1e-5:
            issues.append(Issue("copper_outside_outline", "error", f"{net}/{layer} 铜超出板框。", [net, layer]))
    for layer in layer_names:
        layer_shapes = [(net, shape) for (net, name), shape in copper.items() if name == layer]
        for i, (net_a, a) in enumerate(layer_shapes):
            for net_b, b in layer_shapes[i+1:]:
                if a.intersects(b):
                    issues.append(Issue("physical_short", "error", f"{layer} 上 {net_a or '未分配'} 与 {net_b or '未分配'} 的铜接触。", [net_a, net_b, layer]))
    board = Board(path, hashlib.sha256(raw).hexdigest(), int(number(root,"version",0)), layers, pads, vias, copper, outline, issues, components, number(child(root,"general",["general"]),"thickness"))
    board.tracks = tracks
    from .presentation import collect_presentation
    collect_presentation(board,root)
    return board
