from __future__ import annotations

from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QThread,Signal,QTimer,Slot
from PySide6.QtGui import QColor,QFont,QImage,QPainter,QGuiApplication
from PySide6.QtWidgets import QWidget

from ceda.errors import CedaError
from ceda.visualization.scene import build_scene
from ceda.visualization.models import resolve_model,vrml_mesh,isolated_step_mesh,place_model
from ceda.visualization.raster import render


class ModelLoader(QThread):
    completed=Signal(object)
    def __init__(self,board,library_root,parent):
        super().__init__(parent);self.board=board;self.library_root=library_root
    def run(self):
        cache={};parts=[];warnings=[];loaded=0;total=0
        for ref,component in self.board.components.items():
            specifications=component.get('models',[])
            if not specifications:warnings.append(f'{ref}：文件未关联三维模型')
            for spec in specifications:
                total+=1
                if self.isInterruptionRequested():self.completed.emit(([],[],0,0));return
                path=resolve_model(spec['path'],self.board.path,self.library_root)
                if not path:
                    warnings.append(f"{ref}：模型文件未找到 {spec['path']}");continue
                try:
                    if path not in cache:
                        extension=path.suffix.lower()
                        if extension=='.wrl':cache[path]=vrml_mesh(path)
                        elif extension in {'.step','.stp'}:
                            t,c,warning=isolated_step_mesh(path,self.isInterruptionRequested)
                            cache[path]=(t,c)
                            if warning:warnings.append(f'{ref} / {path.name}：{warning}')
                        else:raise CedaError(f'未支持模型格式 {extension}')
                    triangles,colors=cache[path]
                    parts.append((place_model(triangles,component,spec,self.board.board_thickness_mm),colors,ref))
                    loaded+=1
                except Exception as exc:
                    warnings.append(f'{ref}：{path.name} 读取失败：{exc}')
        self.completed.emit((parts,warnings,loaded,total))


class RasterTask(QThread):
    completed=Signal(object)
    def __init__(self,args,parent):super().__init__(parent);self.args=args
    def run(self):
        try:
            pixels,ids=render(**self.args)
            image=QImage(pixels.data,pixels.shape[1],pixels.shape[0],pixels.strides[0],QImage.Format.Format_RGB888).copy()
            self.completed.emit((image,ids))
        except Exception as exc:self.completed.emit(str(exc))


class Board3D(QWidget):
    pad_clicked=Signal(str)
    model_status=Signal(str)
    def __init__(self):
        super().__init__();self.board=None;self.scene_data=None;self.library_root=None
        self.yaw=-65;self.tilt=48;self.zoom=1;self.pan=[0,0];self.image=None;self.ids=None
        self.gpu=None;self.gpu_scene=None
        self.enabled_categories={'substrate','copper','mask','pads','silk','models'}
        self.loader=None;self.raster=None;self.pending=False;self.generation=0;self.draw_generation=-1
        self.last_pos=None;self.drag_distance=0;self.note='导入 PCB 后查看真实尺寸的三维板卡'
        self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.timeout.connect(self.start_render)
        self.setMinimumHeight(220);self.setMouseTracking(True)

    def set_board(self,board):
        self.stop_workers();self.board=board;self.image=None;self.ids=None;self.scene_data=None
        self.yaw=-65;self.tilt=48;self.zoom=1;self.pan=[0,0];self.gpu_scene=None
        try:
            self.scene_data=build_scene(board)
            bounds=board.outline.bounds;self.center=np.array([(bounds[0]+bounds[2])/2,-(bounds[1]+bounds[3])/2,0])
            self.span=max(bounds[2]-bounds[0],bounds[3]-bounds[1]);self.note='板卡实体已构建；元件模型待加载'
            self.schedule();self.load_models()
        except CedaError as exc:self.note=str(exc);self.model_status.emit(self.note)
        self.update()

    def load_models(self):
        if not self.board or not self.scene_data:return
        if self.loader and self.loader.isRunning():return
        self.loader=ModelLoader(self.board,self.library_root,self)
        self.loader.completed.connect(self.models_ready);self.loader.start()
        self.note='正在读取实际元件模型…';self.model_status.emit(self.note)

    @Slot(object)
    def models_ready(self,result):
        sender=self.sender()
        if sender is not None and sender.board is not self.board:return
        if not self.scene_data:return
        parts,warnings,loaded,total=result
        for triangles,colors,ref in parts:self.scene_data.add(triangles,colors,'models')
        self.scene_data.models_loaded=loaded;self.scene_data.models_total=total
        self.scene_data.warnings.extend(warnings)
        self.note=f'真实模型 {loaded}/{total} · {len(warnings)} 项模型/显示提示'
        self.gpu_scene=None;self.model_status.emit(self.note);self.schedule()

    def set_library(self,path):
        self.library_root=Path(path)
        if self.board:self.set_board(self.board)

    def schedule(self):
        self.generation+=1;self.debounce.start(40)

    def start_render(self):
        if not self.scene_data or not self.isVisible():return
        if self.gpu:
            try:
                if self.gpu_scene is not self.scene_data:
                    self.gpu.control.load(self.scene_data,self.center);self.gpu_scene=self.scene_data
                scale=min(self.width(),self.height())*0.9/self.span*self.zoom
                self.gpu.control.camera(self.yaw,self.tilt,scale,self.pan,self.width(),self.height(),self.enabled_categories)
                self.pending=False;self.update();return
            except Exception as exc:
                self.note=f'GPU 初始化失败，切换软件显示：{exc}'
                self.model_status.emit(self.note);self.gpu.hide();self.gpu.deleteLater();self.gpu=None
        if self.raster and self.raster.isRunning():self.pending=True;return
        triangles,colors=self.scene_data.arrays()
        keep=np.array([c in self.enabled_categories for c in self.scene_data.categories],dtype=bool)
        self.face_map=np.flatnonzero(keep)
        target_width=max(200,min(self.width()*2,1600));target_height=max(200,min(self.height()*2,1200))
        # Keep the physical viewport aspect ratio while capping high DPI work.
        factor=min(target_width/max(self.width(),1),target_height/max(self.height(),1))
        size=(max(1,int(self.width()*factor)),max(1,int(self.height()*factor)))
        args=dict(triangles=triangles[keep],colors=colors[keep],size=size,center=self.center,span=self.span,
                  yaw=self.yaw,tilt=self.tilt,zoom=self.zoom,pan=tuple(self.pan))
        self.draw_generation=self.generation;self.pending=False
        self.raster=RasterTask(args,self);self.raster.completed.connect(self.render_ready)
        self.raster.finished.connect(self.render_finished);self.raster.start()

    @Slot(object)
    def render_ready(self,result):
        if isinstance(result,str):self.note=f'三维绘制失败：{result}';self.model_status.emit(self.note)
        elif self.draw_generation==self.generation:self.image,self.ids=result;self.update()
        else:self.pending=True

    @Slot()
    def render_finished(self):
        if self.raster:self.raster.deleteLater();self.raster=None
        if self.pending:self.debounce.start(1)

    def fit(self):self.zoom=1;self.pan=[0,0];self.schedule()
    def pose(self,kind):
        self.yaw,self.tilt={'iso':(-65,48),'top':(0,0),'bottom':(0,180)}[kind];self.fit()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.gpu:self.gpu.setGeometry(0,34,self.width(),max(1,self.height()-68))
        self.schedule()
    def showEvent(self,event):
        super().showEvent(event)
        import os
        if not self.gpu and QGuiApplication.platformName() not in {'offscreen','minimal'} and os.environ.get('CEDA_SOFTWARE_3D')!='1':
            from .gpuview import GPUView
            try:
                self.gpu=GPUView(self);self.gpu.setGeometry(0,34,self.width(),max(1,self.height()-68));self.gpu.show()
            except Exception as exc:
                self.note=f'GPU 视口不可用，使用软件显示：{exc}';self.model_status.emit(self.note)
        self.schedule()
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#eef1f2'))
        if self.image:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);painter.drawImage(self.rect(),self.image)
        painter.setPen(QColor('#647380'));painter.setFont(QFont('Helvetica',10))
        painter.drawText(18,25,'3D  /  正交投影 · 毫米坐标')
        painter.drawText(18,self.height()-16,self.note)
        if not self.image and not self.gpu:
            painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,self.note)
        if self.scene_data:
            painter.drawText(self.width()-145,25,f'板厚 {self.board.board_thickness_mm:g} mm')
    def mousePressEvent(self,event):self.last_pos=event.position();self.drag_distance=0
    def mouseMoveEvent(self,event):
        if self.last_pos is None:return
        delta=event.position()-self.last_pos;self.last_pos=event.position();self.drag_distance+=abs(delta.x())+abs(delta.y())
        if event.buttons() & Qt.MouseButton.LeftButton and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.yaw+=delta.x()*0.5;self.tilt=np.clip(self.tilt+delta.y()*0.5,-180,180)
        else:
            self.pan[0]+=delta.x()/max(self.width(),1);self.pan[1]+=delta.y()/max(self.height(),1)
        self.schedule()
    def mouseReleaseEvent(self,event):
        if self.gpu and self.drag_distance<4 and self.scene_data:
            pad=self.pick_pad(event.position())
            if pad:self.pad_clicked.emit(pad)
        if self.drag_distance<4 and self.ids is not None and self.image:
            x=int(event.position().x()*self.ids.shape[1]/max(self.width(),1));y=int(event.position().y()*self.ids.shape[0]/max(self.height(),1))
            if 0<=x<self.ids.shape[1] and 0<=y<self.ids.shape[0]:
                index=self.ids[y,x]
                if index>=0:
                    pad=self.scene_data.pad_ids[self.face_map[index]]
                    if pad:self.pad_clicked.emit(pad)
        self.last_pos=None
    def pick_pad(self,position):
        from scipy.spatial.transform import Rotation
        triangles,_=self.scene_data.arrays()
        keep=np.array([c in self.enabled_categories for c in self.scene_data.categories],bool)
        mapping=np.flatnonzero(keep);triangles=triangles[keep]
        rotation=Rotation.from_euler('x',self.tilt,degrees=True).as_matrix()@Rotation.from_euler('z',self.yaw,degrees=True).as_matrix()
        camera=(triangles-self.center)@rotation.T
        scale=min(self.width(),self.height())*0.9/self.span*self.zoom
        x=(position.x()-self.width()/2-self.pan[0]*self.width())/scale
        y=-(position.y()-self.height()/2-self.pan[1]*self.height())/scale
        a,b,c=camera[:,0],camera[:,1],camera[:,2]
        den=(b[:,1]-c[:,1])*(a[:,0]-c[:,0])+(c[:,0]-b[:,0])*(a[:,1]-c[:,1])
        valid=np.abs(den)>1e-10;den=np.where(valid,den,1)
        u=((b[:,1]-c[:,1])*(x-c[:,0])+(c[:,0]-b[:,0])*(y-c[:,1]))/den
        v=((c[:,1]-a[:,1])*(x-c[:,0])+(a[:,0]-c[:,0])*(y-c[:,1]))/den
        w=1-u-v;depth=u*a[:,2]+v*b[:,2]+w*c[:,2]
        hit=np.flatnonzero(valid&(u>=0)&(v>=0)&(w>=0))
        if not len(hit):return None
        return self.scene_data.pad_ids[mapping[hit[np.argmax(depth[hit])]]]
    def wheelEvent(self,event):
        self.zoom=float(np.clip(self.zoom*(1.15 if event.angleDelta().y()>0 else 1/1.15),0.15,20));self.schedule();event.accept()
    def stop_workers(self):
        self.debounce.stop()
        for worker in (self.loader,self.raster):
            if worker:
                worker.blockSignals(True)
                if worker.isRunning():worker.requestInterruption();worker.wait()
                worker.deleteLater()
        self.loader=None;self.raster=None;self.pending=False
    def closeEvent(self,event):self.stop_workers();super().closeEvent(event)
