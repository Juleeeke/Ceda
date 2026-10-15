import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
import pytest
from shapely.geometry import Point,box
from ceda.kicad import load_board
from ceda.kicad.importer import arc_points
from ceda.resources import demo_board
from ceda.visualization.models import vrml_mesh,resolve_model,place_model
from ceda.visualization.scene import surface,extrude,build_scene
from ceda.visualization.raster import render


def test_exact_arc_endpoints_close_board():
    points=arc_points((10,1),(10.707107,1.292893),(11,2))
    assert points[0]==[10,1] and points[-1]==[11,2]


def test_source_silk_mask_and_rotated_npth_slot(tmp_path):
    text=demo_board().read_text().replace('(at 6 6)','(at 6 6 90)',1)
    text=text.replace('(layers "F.Cu")','(layers "F.Cu" "F.Mask")',1)
    extra='(footprint "fixture" (layer "F.Cu") (at 20 10 90) (property "Reference" "H1") (pad "" np_thru_hole oval (at 0 0 90) (size 4 2) (drill oval 4 2) (layers "*.Cu" "*.Mask")))'
    path=tmp_path/'board.kicad_pcb';path.write_text(text[:-2]+extra+'\n)')
    b=load_board(path)
    assert b.mask_openings['F.Mask'].contains(Point(6,6))
    reference=next(g for g in b.graphics if g.get('text')=='J1')
    assert reference['x']==pytest.approx(4) and reference['y']==pytest.approx(6)
    hole=next(h for h in b.holes if h['id']=='H1.')
    bounds=hole['geometry'].bounds
    assert bounds[2]-bounds[0]==pytest.approx(2)
    assert bounds[3]-bounds[1]==pytest.approx(4)
    assert not hole['plated']


def test_triangulation_preserves_board_cutout():
    shape=box(0,0,10,10).difference(box(4,4,6,6))
    triangles=surface(shape,1)
    area=sum(abs(np.cross(t[1]-t[0],t[2]-t[0])[2])/2 for t in triangles)
    assert area==pytest.approx(96)
    assert np.max(triangles[:,:,2])==1
    solid=extrude(shape,-0.8,0.8)
    assert solid[:,:,2].min()==pytest.approx(-0.8)
    assert solid[:,:,2].max()==pytest.approx(0.8)


def test_actual_vrml_material_units_transform_and_use(tmp_path):
    path=tmp_path/'part.wrl'
    path.write_text('''#VRML V2.0 utf8
    Shape { appearance Appearance { material DEF gold Material { diffuseColor 1 0.7 0.2 } } }
    Transform { translation 1 0 0 children [ Shape {
      appearance Appearance { material USE gold }
      geometry IndexedFaceSet { coord Coordinate { point [ 0 0 0, 1 0 0, 0 1 0 ] } coordIndex [0,1,2,-1] }
    } ] }''')
    triangles,colors=vrml_mesh(path)
    assert triangles[0,0,0]==pytest.approx(2.54)
    assert triangles[0,1,0]==pytest.approx(5.08)
    assert colors[0].tolist()==[1,0.7,0.2]


def test_model_resolution_and_bottom_transform(tmp_path):
    directory=tmp_path/'library'/'Package.3dshapes';directory.mkdir(parents=True)
    path=directory/'part.step';path.write_text('source')
    assert resolve_model('${KICAD6_3DMODEL_DIR}/Package.3dshapes/part.wrl',tmp_path/'pcb.kicad_pcb',tmp_path/'library')==path
    assert resolve_model('${UNSET_CEDA_TEST_VARIABLE}/none.step',tmp_path/'pcb.kicad_pcb') is None
    spec={'scale':[1,1,1],'offset':[0,0,0],'rotate':[0,0,0]}
    tri=np.array([[[0,0,0],[1,0,0],[0,1,1]]],float)
    placed=place_model(tri,{'x_mm':10,'y_mm':20,'side':'B.Cu','rotation_deg':90},spec,1.6)
    assert placed[0,2].tolist()==pytest.approx([11,-20,-1.8])


def test_depth_buffer_selects_front_surface_not_input_order():
    back=np.array([[-2,-2,0],[2,-2,0],[0,2,0]],float)
    front=back.copy();front[:,2]=1
    for tris,colors in [(np.array([back,front]),[[1,0,0],[0,1,0]]),(np.array([front,back]),[[0,1,0],[1,0,0]])]:
        pixels,ids=render(tris,np.asarray(colors), (80,80),np.zeros(3),5,yaw=0,tilt=0)
        assert pixels[40,40,1]>pixels[40,40,0]


def test_missing_thickness_never_gets_a_fabricated_solid(board):
    from ceda.errors import CedaError
    board.board_thickness_mm=None
    with pytest.raises(CedaError,match='板厚'):build_scene(board)
