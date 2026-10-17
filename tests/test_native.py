import json
import os
import subprocess
import sys

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import numpy as np
import pytest
from shapely.geometry import Polygon
from ceda.native import export_board,export_mesh
from ceda.resources import demo_board,demo_config


def test_native_contract_preserves_millimetre_geometry(board,tmp_path):
    data=export_board(board,tmp_path)
    assert json.loads((tmp_path/'board.json').read_text())['board']['sha256']==board.sha256
    serialized=[p for o in data['objects'] if o['kind']=='copper' and o['net']=='+3V3' for p in o['polygons']]
    area=sum(Polygon(p['rings'][0],p['rings'][1:]).area for p in serialized)
    assert area==pytest.approx(board.copper[('+3V3','F.Cu')].area)
    assert data['bounds_mm']==[2,2,38,20]


def test_native_mesh_binary_coordinates_and_categories(board,tmp_path):
    before=board.copper[('+3V3','F.Cu')].wkb
    metadata=export_mesh(board,tmp_path)
    vertices=np.fromfile(tmp_path/'vertices.bin',dtype='<f4').reshape(-1,10)
    assert len(vertices)==metadata['vertex_count']
    assert len((tmp_path/'vertices.bin').read_bytes())==metadata['vertex_count']*40
    assert np.isfinite(vertices).all()
    assert vertices[:,0].min()==pytest.approx(-18)
    assert vertices[:,0].max()==pytest.approx(18)
    assert set(vertices[:,9]).issubset(set(range(6)))
    assert board.copper[('+3V3','F.Cu')].wkb==before
    assert metadata['models_loaded']==0 and metadata['models_total']==0
    assert len(metadata['warnings'])==2


def test_native_rejects_changed_snapshot_before_solver(tmp_path):
    result=subprocess.run([sys.executable,'-m','ceda','worker',str(demo_board()),'--config',str(demo_config()),
        '--output',str(tmp_path/'run'),'--expected-board-sha','wrong'],capture_output=True,text=True)
    assert result.returncode==2
    assert '已经改变' in result.stderr
    assert not (tmp_path/'run'/'result.json').exists()
