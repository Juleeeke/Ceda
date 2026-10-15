"""Native Qt Quick 3D viewport; the same millimetre triangles feed CPU validation."""
import numpy as np
from scipy.spatial.transform import Rotation
from PySide6.QtCore import QObject,Property,Signal,QByteArray,QUrl,Qt
from PySide6.QtGui import QColor,QQuaternion,QVector3D
from PySide6.QtQuick3D import QQuick3DGeometry
from PySide6.QtQuickWidgets import QQuickWidget
from ceda.resources import files


class Geometry(QQuick3DGeometry):
    def __init__(self,triangles):
        super().__init__()
        normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-20)
        data=np.concatenate([triangles,np.repeat(normals[:,None,:],3,axis=1)],axis=2).astype(np.float32)
        self.setVertexData(QByteArray(data.tobytes()));self.setStride(24)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        self.addAttribute(QQuick3DGeometry.Attribute.Semantic.PositionSemantic,0,QQuick3DGeometry.Attribute.ComponentType.F32Type)
        self.addAttribute(QQuick3DGeometry.Attribute.Semantic.NormalSemantic,12,QQuick3DGeometry.Attribute.ComponentType.F32Type)
        points=triangles.reshape(-1,3)
        self.setBounds(QVector3D(*points.min(axis=0)),QVector3D(*points.max(axis=0)))


class Controller(QObject):
    partsChanged=Signal();cameraChanged=Signal();visibilityChanged=Signal()
    def __init__(self,parent):
        super().__init__(parent);self._parts=[];self._rotation=QQuaternion();self._scale=1;self._pan=QVector3D();self._visible=[];self.geometries=[]
    @Property('QVariantList',notify=partsChanged)
    def parts(self):return self._parts
    @Property(QQuaternion,notify=cameraChanged)
    def orientation(self):return self._rotation
    @Property(float,notify=cameraChanged)
    def magnification(self):return self._scale
    @Property(QVector3D,notify=cameraChanged)
    def pan(self):return self._pan
    @Property('QStringList',notify=visibilityChanged)
    def enabled(self):return self._visible
    def load(self,scene,center):
        triangles,colors=scene.arrays();groups={}
        for i,(rgb,category) in enumerate(zip(colors,scene.categories)):
            key=(category,tuple(np.round(rgb,3)))
            groups.setdefault(key,[]).append(i)
        old=self.geometries;self.geometries=[];parts=[]
        for (category,rgb),indices in groups.items():
            geometry=Geometry(triangles[indices]-center);self.geometries.append(geometry)
            parts.append({'geometry':geometry,'color':QColor.fromRgbF(*rgb),'category':category})
        self._parts=parts;self.partsChanged.emit()
        for geometry in old:geometry.deleteLater()
    def camera(self,yaw,tilt,scale,pan,width,height,enabled):
        matrix=Rotation.from_euler('x',tilt,degrees=True).as_matrix()@Rotation.from_euler('z',yaw,degrees=True).as_matrix()
        x,y,z,w=Rotation.from_matrix(matrix).as_quat();self._rotation=QQuaternion(w,x,y,z)
        self._scale=scale;self._pan=QVector3D(pan[0]*width/scale,-pan[1]*height/scale,0);self.cameraChanged.emit()
        self._visible=list(enabled);self.visibilityChanged.emit()


class GPUView(QQuickWidget):
    def __init__(self,parent):
        super().__init__(parent);self.control=Controller(self)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.rootContext().setContextProperty('boardScene',self.control)
        self.setSource(QUrl.fromLocalFile(str(files('ceda').joinpath('resources/board3d.qml'))))
        if self.status()==QQuickWidget.Status.Error:
            from ceda.errors import CedaError
            raise CedaError('; '.join(error.toString() for error in self.errors()))
        self.setClearColor(QColor('#eef1f2'))
