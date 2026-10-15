"""Watertight board geometry and display triangles in millimetres.

Independent implementation using Shapely constrained triangulation; KiCad GPL
renderer code is studied but not copied or linked into this MIT application.
"""
from dataclasses import dataclass,field
import numpy as np
from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon
from shapely.ops import unary_union

from ceda.errors import CedaError


@dataclass
class Scene:
    triangles: list = field(default_factory=list)
    colors: list = field(default_factory=list)
    categories: list = field(default_factory=list)
    pad_ids: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    models_loaded: int = 0
    models_total: int = 0

    def add(self,triangles,color,category,pad=None):
        triangles=np.asarray(triangles,float).reshape(-1,3,3)
        self.triangles.extend(triangles)
        rgb=np.asarray(color,float)
        self.colors.extend(np.tile(rgb,(len(triangles),1)) if rgb.ndim==1 else rgb)
        self.categories.extend([category]*len(triangles));self.pad_ids.extend([pad]*len(triangles))

    def arrays(self):
        return np.asarray(self.triangles,float).reshape(-1,3,3),np.asarray(self.colors,float).reshape(-1,3)


def surface(shape,z):
    if shape.is_empty: return np.empty((0,3,3))
    tris=[]
    for triangle in constrained_delaunay_triangles(shape).geoms:
        coords=np.asarray(triangle.exterior.coords)[:3]
        tris.append(np.c_[coords[:,0],-coords[:,1],np.full(3,z)])
    return np.asarray(tris).reshape(-1,3,3)


def walls(shape,lo,hi):
    triangles=[]
    polygons=[shape] if isinstance(shape,Polygon) else getattr(shape,'geoms',[])
    for polygon in polygons:
        if not isinstance(polygon,Polygon):continue
        for ring in [polygon.exterior,*polygon.interiors]:
            coords=list(ring.coords)
            for a,b in zip(coords,coords[1:]):
                p,q,r,s=[a[0],-a[1],lo],[b[0],-b[1],lo],[b[0],-b[1],hi],[a[0],-a[1],hi]
                triangles.extend([[p,q,r],[p,r,s]])
    return np.asarray(triangles).reshape(-1,3,3)


def extrude(shape,lo,hi):
    return np.concatenate([surface(shape,lo)[:,::-1],surface(shape,hi),walls(shape,lo,hi)])


def build_scene(board):
    if board.outline is None: raise CedaError('三维板卡需要闭合的真实 Edge.Cuts 板框。')
    thickness=board.board_thickness_mm
    if not thickness or thickness<=0: raise CedaError('PCB 文件缺少有效板厚，不能生成真实尺寸的三维板卡。')
    scene=Scene();scene.warnings.extend(board.presentation_warnings)
    if any(not ('F.Cu' in h['layers'] and 'B.Cu' in h['layers']) for h in board.holes):
        scene.warnings.append('当前板含盲/埋孔：完整实体腔体未实现，三维视口不能用于其深度/间隙判定。')
    top,bottom=thickness/2,-thickness/2
    top_inner,bottom_inner=top,bottom
    zmap={}
    for i,layer in enumerate(board.layers):
        if layer.z_mm is not None and layer.thickness_mm is not None:
            zmap[layer.name]=thickness/2-layer.z_mm
            if i==0:top_inner=zmap[layer.name]-layer.thickness_mm/2;top=zmap[layer.name]+layer.thickness_mm/2
            if i==len(board.layers)-1:bottom_inner=zmap[layer.name]+layer.thickness_mm/2;bottom=zmap[layer.name]-layer.thickness_mm/2
        else:
            zmap[layer.name]=top if i==0 else bottom if i==len(board.layers)-1 else None
    holes=unary_union([h['geometry'] for h in board.holes if 'F.Cu' in h['layers'] and 'B.Cu' in h['layers']])
    body=board.outline.difference(holes)
    scene.add(surface(body,top_inner),[0.25,0.35,0.23],'substrate')
    scene.add(surface(body,bottom_inner),[0.25,0.35,0.23],'substrate')
    scene.add(walls(body,bottom_inner,top_inner),[0.49,0.43,0.28],'substrate')
    for hole in board.holes:
        if hole['plated']:
            layers=hole['layers'];low=zmap.get(layers[-1]);high=zmap.get(layers[0])
            if low is not None and high is not None:
                scene.add(walls(hole['geometry'],low,high),[0.65,0.56,0.38],'copper')
    metal=[0.78,0.68,0.44]
    for layer_name,z,side in [('F.Cu',top,'F'),('B.Cu',bottom,'B')]:
        copper=unary_union([s for (net,layer),s in board.copper.items() if layer==layer_name]).intersection(board.outline)
        margin=0.001 if side=='F' else -0.001
        scene.add(surface(copper,z+margin),metal,'copper')
        opening=board.mask_openings.get(side+'.Mask',Polygon())
        nonplated=unary_union([h['geometry'] for h in board.holes if not h['plated']])
        mask=board.outline.difference(opening).difference(nonplated)
        # Pure display separation prevents z fighting; does not alter electrical geometry.
        mask_z=z+margin*2
        mask_color=[0.035,0.25,0.15]
        source_color=next((s['color'] for s in board.stackup if s['name']==side+'.Mask'),'')
        if source_color.startswith('#') and len(source_color)>=7:
            try:mask_color=[int(source_color[i:i+2],16)/255 for i in (1,3,5)]
            except ValueError: pass
        scene.add(surface(mask,mask_z),mask_color,'mask')
        # The relief of copper under mask uses the same coating hue, not exposed gold.
        scene.add(surface(copper.intersection(mask),mask_z+margin),np.asarray(mask_color)*1.15,'mask')
        for g in board.graphics:
            if g['layer']!=side+'.SilkS':continue
            if g['kind']=='shape':shape=g['geometry'].intersection(board.outline).difference(opening)
            else:
                shape=text_geometry(g).intersection(board.outline).difference(opening)
            scene.add(surface(shape,mask_z+margin*3),[0.91,0.93,0.85],'silk')
        for pad in board.pads:
            if layer_name in pad.layers:
                # Only mask-open copper is physically exposed on a manufactured board.
                exposed=pad.geometry.intersection(opening).intersection(board.outline)
                scene.add(surface(exposed,z+margin*4),metal,'pads',pad.id)
    return scene


def text_geometry(g):
    # Typography uses the local system font. Position, size and orientation come
    # from the PCB; exact KiCad stroke-font contours are not claimed.
    from PySide6.QtGui import QFont,QPainterPath,QTransform
    from shapely import affinity
    font=QFont('Helvetica');font.setPixelSize(100)
    path=QPainterPath();path.addText(0,0,font,g['text']);bounds=path.boundingRect()
    scale=g['size'][1]/max(bounds.height(),1e-6)
    transform=QTransform();transform.scale(scale,scale)
    path=transform.map(path);bounds=path.boundingRect()
    rings=[]
    for polygon in path.toSubpathPolygons():
        if len(polygon)>=3:
            shape=Polygon([(p.x()-bounds.center().x(),p.y()-bounds.center().y()) for p in polygon])
            if shape.is_valid:rings.append(shape)
    result=Polygon()
    for ring in rings:result=result.symmetric_difference(ring)
    if g['mirror']:result=affinity.scale(result,-1,1,origin=(0,0))
    return affinity.translate(affinity.rotate(result,-g['angle'],origin=(0,0)),g['x'],g['y'])
