from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView
from shapely.geometry import Polygon

from ceda.report import color


def painter_path(shape):
    result = QPainterPath()
    result.setFillRule(Qt.FillRule.OddEvenFill)
    polygons = [shape] if isinstance(shape,Polygon) else list(shape.geoms)
    for polygon in polygons:
        for ring in [polygon.exterior,*polygon.interiors]:
            coords = list(ring.coords)
            result.moveTo(*coords[0])
            for x,y in coords[1:]:
                result.lineTo(x,y)
            result.closeSubpath()
    return result


class BoardView(QGraphicsView):
    pad_clicked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#ffffff"))
        self.board = None
        self.report = None
        self.layer = "F.Cu"
        self.field = "current"
        self.selected_pad = None
        self.range_text = ""

    def render_board(self,board=None,report=None,fit=False):
        if board is not None:
            self.board = board
        if report is not None:
            self.report = report
        scene = self.scene()
        scene.clear()
        if self.board is None:
            text = scene.addText("导入 KiCad PCB，或打开演示板\n选择真实供电与回流焊盘后开始分析")
            text.setDefaultTextColor(QColor("#929ca9"))
            self.fitInView(scene.itemsBoundingRect(),Qt.AspectRatioMode.KeepAspectRatio)
            return
        if self.board.outline is not None:
            scene.addPath(painter_path(self.board.outline),QPen(QColor("#bbc3cf"),0.045),QColor("#fafbfc"))
        for (net,layer),shape in self.board.copper.items():
            if layer == self.layer:
                item = scene.addPath(painter_path(shape),QPen(Qt.PenStyle.NoPen),QColor("#b6c7d4"))
                item.setToolTip(f"{net} / {layer} · {shape.area:.3f} mm²")
        self.range_text = "几何预览 · 尚未求解"
        if self.report and self.field != "geometry":
            if self.field == "temperature" and self.report.get("thermal"):
                mesh = self.report["thermal"]
                triangles = mesh["triangles"]
                pts = mesh["points_mm"]
                values = np.mean(np.array(mesh["temperatures_c"])[triangles],axis=1)
                indices = list(range(len(triangles)))
                unit = "°C · 实验性板温"
            else:
                mesh = self.report["mesh"]
                triangles,pts = mesh["triangles"],mesh["points_mm"]
                values = np.asarray(mesh["current_density_a_mm2"]) if self.field == "current" else np.mean(np.array(mesh["voltage_v"])[triangles],axis=1)
                indices = [i for i,key in enumerate(mesh["triangle_keys"]) if key[1] == self.layer]
                unit = "A/mm²" if self.field == "current" else "V · 相对源负端"
            if indices:
                minimum,maximum = min(values[i] for i in indices),max(values[i] for i in indices)
                self.range_text = f"{minimum:.4g} → {maximum:.4g} {unit} · 当前视图范围"
                for i in indices:
                    polygon = QPolygonF([QPointF(*pts[n]) for n in triangles[i]])
                    item = scene.addPolygon(polygon,QPen(Qt.PenStyle.NoPen),QColor(color(values[i],minimum,maximum)))
                    item.setToolTip(f"{values[i]:.6g} {unit}")
        for pad in self.board.pads:
            if self.layer not in pad.layers:
                continue
            item = scene.addPath(painter_path(pad.geometry),QPen(QColor("#778394"),0.035))
            item.setData(0,pad.id)
            item.setToolTip(f"{pad.id} / {pad.net}")
            text = scene.addText(pad.id)
            text.setScale(0.05)
            text.setPos(pad.x+0.2,pad.y-0.7)
            text.setDefaultTextColor(QColor("#535f70"))
            text.setData(0,pad.id)
        if self.selected_pad:
            pad = self.board.pad(self.selected_pad)
            if self.layer in pad.layers:
                scene.addPath(painter_path(pad.geometry.buffer(0.1)),QPen(QColor("#4671b6"),0.06))
        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-1,-1,1,1))
        if fit:
            self.fitInView(scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self,event):
        item = self.itemAt(event.position().toPoint())
        if item is not None and item.data(0):
            self.selected_pad = item.data(0)
            self.pad_clicked.emit(self.selected_pad)
        super().mousePressEvent(event)

    def wheelEvent(self,event):
        factor = 1.18 if event.angleDelta().y() > 0 else 1/1.18
        self.scale(factor,factor)
        event.accept()
