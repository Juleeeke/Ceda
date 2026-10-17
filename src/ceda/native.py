"""Versioned file contract for native frontends, without importing a GUI shell."""
from __future__ import annotations
import json,os
from dataclasses import asdict
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from ceda.errors import CedaError

CATEGORIES=['substrate','copper','mask','pads','silk','models']


def polygons(shape):
    if shape is None or shape.is_empty:return []
    pieces=[shape] if isinstance(shape,Polygon) else getattr(shape,'geoms',[])
    return [{'rings':[[[float(x),float(y)] for x,y in ring.coords] for ring in [p.exterior,*p.interiors]]}
            for p in pieces if isinstance(p,Polygon)]


def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf-8')
    temporary.replace(path)


def export_board(board,output):
    output=Path(output);objects=[];texts=[]
    def add(kind,shape,layer='',net='',pad_id=None,layers=None):
        geometry=polygons(shape)
        if geometry:objects.append({'id':len(objects),'kind':kind,'polygons':geometry,'layer':layer,
            'layers':layers or [layer],'net':net,'pad_id':pad_id})
    for (net,layer),shape in board.copper.items():add('copper',shape,layer,net)
    for track in board.tracks:add('track',track['geometry'],track['layer'],track['net'])
    for pad in board.pads:add('pad',pad.geometry,net=pad.net,pad_id=pad.id,layers=pad.layers)
    from shapely.geometry import Point
    for via in board.vias:
        ring=Point(via.x,via.y).buffer(via.diameter_mm/2).difference(Point(via.x,via.y).buffer(via.drill_mm/2))
        add('via',ring,net=via.net,layers=via.layers)
    for hole in board.holes:add('hole',hole['geometry'],layers=hole['layers'])
    for graphic in board.graphics:
        if graphic['kind']=='shape':add('graphic',graphic['geometry'],graphic['layer'])
        else:texts.append({k:v for k,v in graphic.items() if k!='geometry'})
    bounds=list(board.outline.bounds) if board.outline is not None else None
    if bounds is None and board.copper:
        from shapely.ops import unary_union
        bounds=list(unary_union(list(board.copper.values())).bounds)
    document={'schema_version':1,'board':board.summary(),'bounds_mm':bounds,'outline':polygons(board.outline),
        'objects':objects,'texts':texts,'warnings':board.presentation_warnings}
    write_json(output/'board.json',document)
    return document


def export_mesh(board,output,library=None,progress=lambda message:None):
    # QtGui is only a font-outline helper in this backend process, never the UI.
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtGui import QGuiApplication
    app=QGuiApplication.instance() or QGuiApplication(['Ceda font geometry'])
    from ceda.visualization.scene import build_scene
    from ceda.visualization.models import resolve_model,vrml_mesh,isolated_step_mesh,place_model
    scene=build_scene(board);cache={}
    for ref,component in board.components.items():
        specifications=component.get('models',[])
        if not specifications:scene.warnings.append(f'{ref}：未关联三维模型')
        for spec in specifications:
            scene.models_total+=1;path=resolve_model(spec['path'],board.path,library)
            if path is None:
                scene.warnings.append(f"{ref}：模型文件未找到 {spec['path']}");continue
            try:
                if path not in cache:
                    progress(f'读取实际模型：{path.name}')
                    if path.suffix.lower()=='.wrl':cache[path]=vrml_mesh(path)
                    elif path.suffix.lower() in {'.step','.stp'}:
                        t,c,warning=isolated_step_mesh(path);cache[path]=(t,c)
                        if warning:scene.warnings.append(f'{path.name}：{warning}')
                    else:raise CedaError(f'未支持模型格式 {path.suffix}')
                t,c=cache[path]
                scene.add(place_model(t,component,spec,board.board_thickness_mm),c,'models')
                scene.models_loaded+=1
            except (CedaError,ValueError,OSError) as exc:scene.warnings.append(f'{ref}：{exc}')
    triangles,colors=scene.arrays()
    bounds=board.outline.bounds;center=np.array([(bounds[0]+bounds[2])/2,-(bounds[1]+bounds[3])/2,0])
    normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-20)
    categories=np.asarray([CATEGORIES.index(c) for c in scene.categories],dtype=np.float32)
    data=np.concatenate([triangles-center,np.repeat(normals[:,None,:],3,axis=1),
        np.repeat(colors[:,None,:],3,axis=1),np.repeat(categories[:,None,None],3,axis=1)],axis=2).astype('<f4')
    if not np.isfinite(data).all():raise CedaError('三维显示数据包含非有限数值。')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    temp=output/'vertices.bin.tmp';temp.write_bytes(data.tobytes());temp.replace(output/'vertices.bin')
    metadata={'schema_version':1,'vertices_file':'vertices.bin','vertex_count':int(len(data)*3),'stride_bytes':40,
        'center_mm':center.tolist(),'span_mm':max(bounds[2]-bounds[0],bounds[3]-bounds[1]),
        'categories':CATEGORIES,'models_loaded':scene.models_loaded,'models_total':scene.models_total,
        'warnings':scene.warnings,'board_sha256':board.sha256}
    write_json(output/'mesh.json',metadata)
    return metadata
