"""Source-derived manufacturing/display objects, separate from solver domains."""
from __future__ import annotations

import math
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from ceda.errors import CedaError
from .sexpr import child, children, number


def graphic_shape(node):
    from .importer import xy, arc_points, polygon_points
    kind = node[0].split('_', 1)[1]
    stroke = number(child(node, 'stroke', ['stroke']), 'width', number(node, 'width', 0.15))
    filled = child(node, 'fill', ['fill', 'none'])[1] in {'yes', 'solid'}
    if kind == 'line':
        line = LineString([xy(node, 'start'), xy(node, 'end')])
    elif kind == 'arc':
        line = LineString(arc_points(xy(node, 'start'), xy(node, 'mid'), xy(node, 'end')))
    elif kind == 'circle':
        c, e = xy(node, 'center'), xy(node, 'end')
        area = Point(c).buffer(math.dist(c, e), quad_segs=48)
        return area if filled else area.boundary.buffer(stroke / 2)
    elif kind == 'rect':
        a, b = xy(node, 'start'), xy(node, 'end')
        area = box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        return area if filled else area.boundary.buffer(stroke / 2, join_style=2)
    elif kind == 'poly':
        area = polygon_points(node)
        return area if filled else area.boundary.buffer(stroke / 2)
    else:
        raise CedaError(f'尚未支持显示图形 {node[0]}。')
    return line.buffer(stroke / 2, quad_segs=16)


def drill_shape(node, x, y, angle=0):
    from .importer import transform
    drill = child(node, 'drill')
    if drill is None:
        return None
    if child(drill, 'offset') is not None:
        raise CedaError('偏心钻孔尚未支持。')
    if drill[1] != 'oval':
        return Point(x, y).buffer(float(drill[1]) / 2, quad_segs=32)
    w, h = float(drill[2]), float(drill[3])
    if w >= h:
        shape = LineString([(-(w-h)/2, 0), ((w-h)/2, 0)]).buffer(h/2, quad_segs=32)
    else:
        shape = LineString([(0, -(h-w)/2), (0, (h-w)/2)]).buffer(w/2, quad_segs=32)
    return transform(shape, x, y, angle)


def collect_presentation(board, root):
    from .importer import xy, transform, pad_shape
    setup = child(root, 'setup', ['setup'])
    for layer in children(child(setup,'stackup',['stackup']), 'layer'):
        board.stackup.append({'name': layer[1], 'thickness_mm': number(layer,'thickness'),
            'color': child(layer,'color',['color',''])[1], 'material': child(layer,'material',['material',''])[1]})
    default_margin = number(setup, 'pad_to_mask_clearance', 0)
    masks = {'F.Mask': [], 'B.Mask': []}
    warnings = board.presentation_warnings

    def graphics(nodes, origin=(0, 0), rotation=0, ref=''):
        for node in nodes:
            if not isinstance(node, list) or not node:
                continue
            key = node[0]
            layer = child(node, 'layer', ['layer', ''])[1]
            if not layer:
                continue
            if key in {'fp_text', 'gr_text', 'property'}:
                # Other footprint properties are metadata, not visible text.
                if key == 'property' and node[1] not in {'Reference', 'Value'}:
                    continue
                effects = child(node, 'effects', ['effects'])
                if 'hide' in node or child(node, 'hide', ['hide', 'no'])[1] == 'yes' or 'hide' in effects:
                    continue
                text = node[2] if key in {'fp_text', 'property'} else node[1]
                if not text or '${VALUE}' in text:
                    continue
                text = text.replace('${REFERENCE}', ref)
                at = child(node, 'at')
                if not at:
                    continue
                point = transform(Point(float(at[1]), float(at[2])), *origin, rotation)
                font = child(effects, 'font', ['font'])
                size = child(font, 'size', ['size', 1, 1])
                board.graphics.append({'kind': 'text', 'text': text, 'x': point.x, 'y': point.y,
                    'angle': float(at[3]) if len(at) > 3 else 0, 'layer': layer,
                    'size': (float(size[1]), float(size[2])), 'reference': ref,
                    'mirror': 'mirror' in child(effects, 'justify', [])})
            elif key.startswith(('fp_', 'gr_')) and key not in {'fp_text', 'gr_text'}:
                if layer.endswith('.Cu') or layer == 'Edge.Cuts':
                    continue
                try:
                    shape = transform(graphic_shape(node), *origin, rotation)
                    board.graphics.append({'kind': 'shape', 'geometry': shape, 'layer': layer, 'reference': ref})
                    if layer in masks:
                        masks[layer].append(shape)
                except CedaError as exc:
                    warnings.append(str(exc))

    graphics(root[1:])
    for fp in children(root, 'footprint'):
        origin = xy(fp, 'at'); at = child(fp, 'at')
        rotation = float(at[3]) if len(at) > 3 else 0
        props = {p[1]: p[2] for p in children(fp, 'property') if len(p) > 2}
        ref = props.get('Reference')
        if ref is None:
            text = next((p for p in children(fp, 'fp_text') if p[1] == 'reference'), None)
            ref = text[2] if text else '?'
        component = board.components[ref]
        component.update(rotation_deg=rotation, side=child(fp, 'layer', ['layer', 'F.Cu'])[1], models=[])
        for model in children(fp, 'model'):
            def triple(key, default):
                item = child(child(model, key, [key]), 'xyz')
                return [float(x) for x in item[1:4]] if item else default
            if 'hide' not in model:
                component['models'].append({'path': model[1], 'offset': triple('offset', [0, 0, 0]),
                    'scale': triple('scale', [1, 1, 1]), 'rotate': triple('rotate', [0, 0, 0])})
        graphics(fp[1:], origin, rotation, ref)
        fp_margin = number(fp, 'solder_mask_margin', default_margin)
        for node in children(fp, 'pad'):
            local = xy(node, 'at')
            point = transform(Point(*local), *origin, rotation)
            at = child(node, 'at'); angle = float(at[3]) if len(at) > 3 else 0
            hole = drill_shape(node, point.x, point.y, angle)
            if hole is not None:
                board.holes.append({'geometry': hole, 'plated': node[2] == 'thru_hole',
                    'layers': [l.name for l in board.layers], 'id': f'{ref}.{node[1]}'})
            if node[2] == 'np_thru_hole':
                continue
            layers = child(node, 'layers', ['layers'])[1:]
            shape = transform(pad_shape(node), point.x, point.y, angle)
            margin = number(node, 'solder_mask_margin', fp_margin)
            opening = shape.buffer(margin)
            for layer in masks:
                if layer in layers or '*.Mask' in layers:
                    masks[layer].append(opening)
    # Vias are tented unless the source requests a mask opening.
    tenting = child(setup, 'tenting', ['tenting'])
    legacy_tented = child(setup, 'tenting') is None
    for via, node in zip(board.vias, children(root, 'via')):
        hole = Point(via.x, via.y).buffer(via.drill_mm/2, quad_segs=32)
        board.holes.append({'geometry': hole, 'plated': True, 'layers': via.layers, 'id': via.id})
        local_tent = child(node, 'tenting', tenting)
        for layer, side, copper in [('F.Mask', 'front', 'F.Cu'), ('B.Mask', 'back', 'B.Cu')]:
            covered = child(local_tent, side, [side, 'yes' if legacy_tented else 'no'])[1] == 'yes'
            if copper in via.layers and not covered:
                masks[layer].append(Point(via.x, via.y).buffer(via.diameter_mm/2 + default_margin))
    board.mask_openings = {layer: unary_union(pieces) for layer, pieces in masks.items()}
