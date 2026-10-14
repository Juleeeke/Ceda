import math

import pytest
from shapely.geometry import Polygon,box

from ceda.errors import CedaError
from ceda.kicad import load_board
from ceda.kicad.importer import arc_points
from ceda.kicad.sexpr import parse
from ceda.resources import demo_board


def write_board(tmp_path,text):
    path = tmp_path/"board.kicad_pcb"
    path.write_text(text,encoding="utf-8")
    return path


def test_actual_fill_not_zone_outline(board):
    copper = board.copper[("+3V3","F.Cu")]
    assert copper.intersection(box(18,5,22,7)).area == pytest.approx(1.2)
    assert len(board.pads) == 4
    assert not [i for i in board.issues if i.severity == "error"]
    assert board.layers[0].thickness_mm == 0.035


def test_unfilled_zone_blocks_analysis(tmp_path):
    text = demo_board().read_text()
    start = text.index('  (filled_polygon (layer "F.Cu") (pts\n')
    end = text.index('\n (zone (net 2)',start)
    text = text[:start]+")"+text[end:]
    board = load_board(write_board(tmp_path,text))
    assert any(i.code == "unfilled_zone" for i in board.issues)


def test_rotated_footprint_y_down_transform(tmp_path):
    text = demo_board().read_text().replace('(at 6 6)','(at 16 14 90)',1)
    board = load_board(write_board(tmp_path,text))
    assert board.pad("J1.2").x == pytest.approx(24)
    assert board.pad("J1.2").y == pytest.approx(14)
    assert board.pad("J1.2").geometry.bounds[2]-board.pad("J1.2").geometry.bounds[0] == pytest.approx(4)


def test_short_reported(tmp_path):
    text = demo_board().read_text().replace('(at 0 8)','(at 0 0)',1)
    board = load_board(write_board(tmp_path,text))
    assert any(i.code == "physical_short" for i in board.issues)


def test_custom_pad_rejected(tmp_path):
    text = demo_board().read_text().replace('smd rect','smd custom',1)
    with pytest.raises(CedaError,match="尚不支持"):
        load_board(write_board(tmp_path,text))


def test_cutout_preserved(tmp_path):
    text = demo_board().read_text()
    text = text[:-2]+'(gr_rect (start 10 9) (end 12 11) (layer "Edge.Cuts"))\n)'
    board = load_board(write_board(tmp_path,text))
    assert board.outline.area == pytest.approx(36*18-4)


@pytest.mark.parametrize("text",['(a (b)','a','(a))','(a)(b)'])
def test_malformed_input(text):
    with pytest.raises(CedaError):
        parse(text)


def test_quoted_pin_remains_string():
    assert parse('(pad "001" ; ignored\n (net 1 "name (with) spaces"))')[1] == "001"


def test_arc_through_midpoint():
    points = arc_points((1,0),(0,1),(-1,0))
    assert max(y for x,y in points) > 0.99
    assert all(math.hypot(x,y) == pytest.approx(1) for x,y in points)
