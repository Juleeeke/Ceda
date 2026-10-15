from __future__ import annotations

import math
import numpy as np
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView, QStyleOptionGraphicsItem
from shapely.geometry import Polygon

from ceda.report import color

LAYER_COLORS = {'F.Cu':'#d96161','B.Cu':'#5d96df','F.SilkS':'#f2f0d4','B.SilkS':'#a5cee4',
    'F.Fab':'#adb6c1','B.Fab':'#a4b2c0','F.CrtYd':'#cc77d1','B.CrtYd':'#849ad0','Edge.Cuts':'#dccf74'}


def painter_path(shape):
    result = QPainterPath(); result.setFillRule(Qt.FillRule.OddEvenFill)
    if shape.is_empty:
        return result
    polygons = [shape] if isinstance(shape, Polygon) else getattr(shape, 'geoms', [])
    for polygon in polygons:
        if not isinstance(polygon, Polygon):
            continue
        for ring in [polygon.exterior, *polygon.interiors]:
            coords = list(ring.coords); result.moveTo(*coords[0])
            for x, y in coords[1:]:
                result.lineTo(x, y)
            result.closeSubpath()
    return result


class PhysicalText(QGraphicsItem):
    """Text scaled to millimetres, hidden when it would become illegible."""
    def __init__(self, text, height, width=None, color='#e2e8ef'):
        super().__init__(); self.text = text; self.height = height
        self.font = QFont('Helvetica'); self.font.setPixelSize(100)
        from PySide6.QtGui import QFontMetricsF
        metrics = QFontMetricsF(self.font)
        self.bounds = QRectF(-metrics.horizontalAdvance(text)/2, -metrics.height()/2,
                             metrics.horizontalAdvance(text), metrics.height())
        self.setScale(height / metrics.height())
        self.color = QColor(color)
        if width:
            ratio = width / max(self.bounds.width() * self.scale(), 1e-6)
            if ratio < 1:
                from PySide6.QtGui import QTransform
                self.setTransform(QTransform().scale(ratio, 1))

    def boundingRect(self): return self.bounds

    def paint(self, painter, option, widget=None):
        if self.bounds.height() * QStyleOptionGraphicsItem.levelOfDetailFromTransform(painter.worldTransform()) < 7:
            return
        painter.setFont(self.font); painter.setPen(self.color)
        painter.drawText(self.bounds, Qt.AlignmentFlag.AlignCenter, self.text)


class BoardView(QGraphicsView):
    pad_clicked = Signal(str)
    cursor_changed = Signal(str)

    def __init__(self):
        super().__init__(); self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)
        self.board = None; self.report = None; self.layer = 'F.Cu'; self.field = 'geometry'
        self.selected_pad = None; self.range_text = ''; self.dark = True
        self.show_grid = True; self.show_labels = True; self.show_mesh = False
        self.visible_layers = {'F.Cu','B.Cu','F.SilkS','B.SilkS','Edge.Cuts'}
        self.value_range = None
        self.setBackgroundBrush(QColor('#171e28'))

    def set_light(self, light):
        self.dark = not light; self.setBackgroundBrush(QColor('#171e28' if self.dark else '#fbfcfd'))
        self.render_board()

    def add_shape(self, shape, fill, tooltip='', pen=None, pad=None):
        item = self.scene().addPath(painter_path(shape), pen or QPen(Qt.PenStyle.NoPen), QColor(fill))
        item.setToolTip(tooltip)
        if pad: item.setData(0, pad)
        return item

    def render_board(self, board=None, report=None, fit=False):
        if board is not None: self.board = board
        if report is not None: self.report = report
        scene = self.scene(); scene.clear(); self.value_range = None
        if self.board is None:
            text = scene.addText('导入 KiCad PCB\n显示文件中的实际板框、铜层、丝印与钻孔')
            text.setDefaultTextColor(QColor('#8f9aaa')); self.fitInView(scene.itemsBoundingRect(),Qt.AspectRatioMode.KeepAspectRatio)
            return
        if self.board.outline is not None:
            self.add_shape(self.board.outline,'#202b34' if self.dark else '#f1f5f5')
        copper_layers = [l.name for l in self.board.layers if l.name in self.visible_layers or l.name == self.layer]
        # Active copper is drawn last; inactive layers are dimmed, as in an EDA editor.
        copper_layers.sort(key=lambda layer: layer == self.layer)
        for layer in copper_layers:
            active = layer == self.layer
            hue = QColor(LAYER_COLORS.get(layer,'#b889cc'))
            hue.setAlpha(120 if active else 40)
            for (net,name), shape in self.board.copper.items():
                if name == layer:
                    item = scene.addPath(painter_path(shape),QPen(Qt.PenStyle.NoPen),hue)
                    item.setToolTip(f'{net or "未分配"} / {layer} · {shape.area:.3f} mm²')
            for track in self.board.tracks:
                if track['layer'] == layer:
                    c = QColor(LAYER_COLORS.get(layer,'#b889cc')); c.setAlpha(245 if active else 75)
                    item = scene.addPath(painter_path(track['geometry']),QPen(Qt.PenStyle.NoPen),c)
                    item.setToolTip(f"{track['net']} / {layer} · 线宽 {track['width_mm']:g} mm")
        self.range_text = f'{self.layer} · 文件几何 · 单位 mm'
        if self.report and self.field != 'geometry':
            if self.field == 'temperature' and self.report.get('thermal'):
                mesh = self.report['thermal']; triangles = mesh['triangles']; pts = mesh['points_mm']
                values = np.mean(np.array(mesh['temperatures_c'])[triangles],axis=1)
                indices = list(range(len(triangles))); unit = '°C · 实验性板温'
            else:
                mesh = self.report['mesh']; triangles,pts = mesh['triangles'],mesh['points_mm']
                values = np.asarray(mesh['current_density_a_mm2']) if self.field == 'current' else np.mean(np.array(mesh['voltage_v'])[triangles],axis=1)
                indices = [i for i,key in enumerate(mesh['triangle_keys']) if key[1] == self.layer]
                unit = 'A/mm²' if self.field == 'current' else 'V · 相对源负端'
            if indices:
                low,high = min(values[i] for i in indices),max(values[i] for i in indices)
                self.value_range = (low,high,unit)
                self.range_text = f'{low:.4g} → {high:.4g} {unit} · 仅已求解网络'
                for i in indices:
                    polygon = QPolygonF([QPointF(*pts[n]) for n in triangles[i]])
                    pen = QPen(QColor('#708399'),0.008) if self.show_mesh else QPen(Qt.PenStyle.NoPen)
                    item = scene.addPolygon(polygon,pen,QColor(color(values[i],low,high)))
                    item.setToolTip(f'{values[i]:.6g} {unit}')
            else:
                self.range_text = f'{self.layer} · 此层没有已求解数据'
        for g in self.board.graphics:
            if g['layer'] not in self.visible_layers: continue
            if g['layer'].startswith('F.') and self.layer == 'B.Cu' and g['layer'] != 'F.Cu': continue
            if g['layer'].startswith('B.') and self.layer != 'B.Cu' and g['layer'] != 'B.Cu': continue
            hue = LAYER_COLORS.get(g['layer'],'#a2abb6')
            if not self.dark and g['layer'].endswith('SilkS'): hue = '#52664a'
            if g['kind'] == 'shape':
                self.add_shape(g['geometry'],hue,g.get('reference',''))
            elif self.show_labels:
                text = PhysicalText(g['text'],g['size'][1],color=hue)
                text.setPos(g['x'],g['y']); text.setRotation(-g['angle'])
                if g['mirror']:
                    from PySide6.QtGui import QTransform
                    text.setTransform(QTransform().scale(-1,1))
                scene.addItem(text)
        for pad in self.board.pads:
            if self.layer not in pad.layers: continue
            fill = '#dfb97c' if self.field == 'geometry' or not self.report else '#00000000'
            self.add_shape(pad.geometry,fill,f'{pad.id} / {pad.net}',QPen(QColor('#f3d19a' if self.dark else '#9b752e'),0.018),pad.id)
            if self.show_labels:
                bounds = pad.geometry.bounds
                height = min(0.7,(bounds[3]-bounds[1])*0.42)
                text = PhysicalText(pad.number,height,max(0.1,(bounds[2]-bounds[0])*0.7),color='#282827' if fill != '#00000000' else '#526072')
                text.setPos(pad.x,pad.y); text.setData(0,pad.id); scene.addItem(text)
        for via in self.board.vias:
            if self.layer not in via.layers: continue
            from shapely.geometry import Point
            ring = Point(via.x,via.y).buffer(via.diameter_mm/2).difference(Point(via.x,via.y).buffer(via.drill_mm/2))
            self.add_shape(ring,'#b4a077',f'过孔 / {via.net} · 孔径 {via.drill_mm:g} mm')
        for hole in self.board.holes:
            if self.layer in hole['layers']:
                self.add_shape(hole['geometry'],'#101720' if self.dark else '#ffffff',f"钻孔 {hole['id']}")
        if self.board.outline is not None and 'Edge.Cuts' in self.visible_layers:
            scene.addPath(painter_path(self.board.outline),QPen(QColor('#dccf74' if self.dark else '#7f7b43'),0.07))
        if self.selected_pad:
            for pad in self.board.pads:
                if pad.id==self.selected_pad and self.layer in pad.layers:
                    scene.addPath(painter_path(pad.geometry.buffer(0.12)),QPen(QColor('#55c6ed'),0.06))
        bounds = QRectF(*self.board.outline.bounds[:2],self.board.outline.bounds[2]-self.board.outline.bounds[0],self.board.outline.bounds[3]-self.board.outline.bounds[1]) if self.board.outline is not None else scene.itemsBoundingRect()
        scene.setSceneRect(bounds.adjusted(-2,-2,2,2))
        if fit: self.fitInView(scene.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
        self.viewport().update()

    def drawBackground(self,painter,rect):
        super().drawBackground(painter,rect)
        if not self.show_grid or not self.board: return
        pixels = abs(self.transform().m11()); step = 0.5
        while step*pixels < 14: step *= 2
        painter.setPen(QPen(QColor('#35424f' if self.dark else '#d5dde4'),0))
        points = [QPointF(x,y) for x in np.arange(math.floor(rect.left()/step)*step,rect.right(),step)
                  for y in np.arange(math.floor(rect.top()/step)*step,rect.bottom(),step)]
        if points: painter.drawPoints(points)

    def drawForeground(self,painter,rect):
        if not self.board: return
        painter.save(); painter.resetTransform()
        painter.setFont(QFont('Helvetica',10)); painter.setPen(QColor('#a9b8c8' if self.dark else '#657382'))
        scale = abs(self.transform().m11()); length = 10**math.floor(math.log10(100/max(scale,1e-9)))
        if length*scale < 45: length *= 5
        x,y = 24,self.viewport().height()-24
        painter.drawLine(QPointF(x,y),QPointF(x+length*scale,y))
        painter.drawLine(QPointF(x,y-3),QPointF(x,y+3)); painter.drawLine(QPointF(x+length*scale,y-3),QPointF(x+length*scale,y+3))
        painter.drawText(QPointF(x,y-8),f'{length:g} mm')
        if self.value_range:
            lo,hi,unit = self.value_range; width=150; x=self.viewport().width()-width-24; y=22
            for i in range(width):
                painter.fillRect(x+i,y,1,7,QColor(color(i,0,width-1)))
            painter.drawText(QPointF(x,y+24),f'{lo:.4g}'); painter.drawText(QPointF(x+width-52,y+24),f'{hi:.4g}')
        painter.restore()

    def mousePressEvent(self,event):
        item = self.itemAt(event.position().toPoint())
        if item is not None and item.data(0):
            self.selected_pad = item.data(0); self.pad_clicked.emit(self.selected_pad); self.render_board()
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        p = self.mapToScene(event.position().toPoint()); self.cursor_changed.emit(f'X {p.x():.3f}  Y {p.y():.3f} mm')
        super().mouseMoveEvent(event)

    def wheelEvent(self,event):
        factor = 1.18 if event.angleDelta().y() > 0 else 1/1.18
        current = abs(self.transform().m11())
        if 0.2 < current*factor < 4000: self.scale(factor,factor)
        event.accept()
