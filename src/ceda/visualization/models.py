"""Explicit KiCad model resolution and actual VRML/STEP tessellation.

No footprint-shaped replacement solids are synthesized for missing models.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from ceda.errors import CedaError


def resolve_model(filename, board_path, library_root=None):
    project = Path(board_path).parent
    if library_root: library_root = Path(library_root).resolve()
    def variable(match):
        name = match.group(1)
        if name == 'KIPRJMOD': return str(project)
        if library_root and (re.fullmatch(r'KICAD\d+_3DMODEL_DIR',name) or name == 'KISYS3DMOD'):
            return str(library_root)
        return os.environ.get(name, match.group(0))
    expanded = re.sub(r'\$\{([^}]+)\}',variable,filename)
    expanded = os.path.expandvars(expanded)
    if '$' in expanded: return None
    path = Path(expanded).expanduser()
    if not path.is_absolute(): path = project / path
    if path.is_file(): return path.resolve()
    # The matching standard STEP model may exist where a board refers to WRL.
    if path.suffix.lower() == '.wrl':
        for suffix in ('.step','.stp','.STEP'):
            alternate = path.with_suffix(suffix)
            if alternate.is_file(): return alternate.resolve()
    return None


class VRMLReader:
    arity = {'translation':3,'scale':3,'center':3,'rotation':4,'scaleOrientation':4,
             'diffuseColor':3,'specularColor':3,'emissiveColor':3}
    def __init__(self,text):
        if not text.lstrip().startswith('#VRML V2.0'):
            raise CedaError('只支持 VRML 2.0 IndexedFaceSet 模型。')
        self.tokens = re.findall(r'"[^"\n]*"|[^\s{}\[\],#]+|[{}\[\]]',re.sub(r'#[^\n]*','',text))
        self.index=0;self.definitions={}
    def pop(self):
        if self.index>=len(self.tokens): raise CedaError('VRML 模型意外结束。')
        value=self.tokens[self.index];self.index+=1;return value
    def value(self,key=''):
        token=self.pop()
        if token=='DEF':
            name=self.pop(); node=self.value();self.definitions[name]=node;return node
        if token=='USE':
            name=self.pop()
            if name not in self.definitions: raise CedaError(f'VRML 未定义的 USE {name}')
            return self.definitions[name]
        if token=='[':
            result=[]
            while self.tokens[self.index]!=']': result.append(self.value())
            self.pop();return result
        if self.index<len(self.tokens) and self.tokens[self.index]=='{':
            self.pop();node={'type':token}
            while self.tokens[self.index]!='}':
                field=self.pop();node[field]=self.value(field)
            self.pop();return node
        try:
            first=float(token)
            return [first,*[float(self.pop()) for _ in range(self.arity[key]-1)]] if key in self.arity else first
        except ValueError:
            return token
    def read(self):
        nodes=[]
        while self.index<len(self.tokens): nodes.append(self.value())
        return nodes


def vrml_mesh(path):
    nodes=VRMLReader(Path(path).read_text(encoding='utf-8')).read();triangles=[];colors=[]
    def visit(node,matrix):
        if not isinstance(node,dict): return
        kind=node['type']
        if kind=='Transform':
            translate=np.eye(4);translate[:3,3]=node.get('translation',[0,0,0])
            center=np.eye(4);center[:3,3]=node.get('center',[0,0,0])
            def axis_rotate(key):
                value=node.get(key,[0,0,1,0]);axis=np.asarray(value[:3],float);length=np.linalg.norm(axis)
                result=np.eye(4)
                if length>0: result[:3,:3]=Rotation.from_rotvec(axis/length*value[3]).as_matrix()
                return result
            orient=axis_rotate('scaleOrientation');scale=np.eye(4);scale[:3,:3]=np.diag(node.get('scale',[1,1,1]))
            matrix=matrix@translate@center@axis_rotate('rotation')@orient@scale@orient.T@np.linalg.inv(center)
        if kind=='Shape' and isinstance(node.get('geometry'),dict):
            geometry=node['geometry']
            if geometry['type']!='IndexedFaceSet': raise CedaError(f"VRML 几何 {geometry['type']} 尚未支持。")
            coordinate=geometry.get('coord',{})
            if coordinate.get('type')!='Coordinate': raise CedaError('VRML 缺少 Coordinate。')
            points=np.asarray(coordinate['point'],float).reshape(-1,3)
            points=(np.c_[points,np.ones(len(points))]@matrix.T)[:,:3]*2.54
            material=node.get('appearance',{}).get('material',{})
            rgb=np.asarray(material.get('diffuseColor',[0.55,0.58,0.61]),float)
            face=[]
            for index in geometry.get('coordIndex',[]):
                index=int(index)
                if index==-1:
                    if len(face)>3 and geometry.get('convex','TRUE')=='FALSE':
                        raise CedaError('非凸 VRML 多边形尚未支持，不能用扇形伪造表面。')
                    for j in range(1,len(face)-1):
                        tri=points[[face[0],face[j],face[j+1]]]
                        if geometry.get('ccw','TRUE')=='FALSE': tri=tri[::-1]
                        triangles.append(tri);colors.append(rgb)
                    face=[]
                else:
                    if index<0 or index>=len(points): raise CedaError('VRML 顶点索引越界。')
                    face.append(index)
        for sub in node.get('children',[]): visit(sub,matrix)
    for node in nodes: visit(node,np.eye(4))
    if not triangles: raise CedaError('VRML 文件没有可用的三角面。')
    return np.asarray(triangles),np.asarray(colors)


def step_mesh(path):
    # Called only by the isolated CLI process, on its main thread.
    import gmsh
    gmsh.initialize(readConfigFiles=False,interruptible=False)
    try:
        gmsh.option.setNumber('General.Terminal',0)
        gmsh.option.setString('Geometry.OCCTargetUnit','MM')
        gmsh.model.add('ceda-display-model');gmsh.model.occ.importShapes(str(path));gmsh.model.occ.synchronize()
        gmsh.option.setNumber('Mesh.MeshSizeMin',0.08);gmsh.option.setNumber('Mesh.MeshSizeMax',0.35)
        gmsh.option.setNumber('Mesh.MeshSizeFromCurvature',12)
        gmsh.model.mesh.generate(2)
        tags,coords,_=gmsh.model.mesh.getNodes();points=np.asarray(coords).reshape(-1,3)
        lookup={int(tag):i for i,tag in enumerate(tags)};triangles=[];colors=[]
        for _,tag in gmsh.model.getEntities(2):
            rgba=gmsh.model.getColor(2,tag)
            rgb=np.asarray(rgba[:3],float)/255
            # Gmsh's generic unassigned color is a tessellator default, not STEP material.
            if tuple(rgba[:3]) in {(0,0,255),(0,0,0)}: rgb=np.array([0.58,0.61,0.65])
            types,_,nodes=gmsh.model.mesh.getElements(2,tag)
            for kind,indices in zip(types,nodes):
                if kind!=2: raise CedaError('STEP 显示网格包含未支持的面类型。')
                mapped=np.array([lookup[int(n)] for n in indices]).reshape(-1,3)
                triangles.extend(points[mapped]);colors.extend([rgb]*len(mapped))
        if not triangles: raise CedaError('STEP 模型没有可用表面。')
        return np.asarray(triangles),np.asarray(colors)
    finally: gmsh.finalize()


def isolated_step_mesh(path,cancelled=lambda:False):
    import subprocess,sys,tempfile,time
    with tempfile.TemporaryDirectory(prefix='ceda-model-') as directory:
        output=Path(directory)/'mesh.npz';log=Path(directory)/'reader.log'
        command=[sys.executable]
        if not getattr(sys,'frozen',False):command+=['-m','ceda']
        command+=['model-mesh',str(path),str(output)]
        with log.open('wb') as stream:
            process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,
                env=dict(os.environ,OMP_NUM_THREADS='1'))
            deadline=time.monotonic()+90
            while process.poll() is None:
                if cancelled() or time.monotonic()>deadline:
                    process.kill();process.wait();raise CedaError('STEP 读取已取消或超时。')
                time.sleep(0.05)
        diagnostics=log.read_text(encoding='utf-8',errors='replace')
        if process.returncode or not output.is_file():
            raise CedaError(f'STEP 独立读取进程失败 ({process.returncode})：{diagnostics[-300:]}')
        with np.load(output,allow_pickle=False) as data:
            triangles,colors=data['triangles'],data['colors']
        warning='STEP 阅读器报告引用/解析警告，模型完整性待核实' if re.search(r'ERR|Error|Unresolved',diagnostics) else ''
        return triangles,colors,warning


def place_model(triangles, component, specification, board_thickness):
    # All coordinates here are millimetres in a right-handed x, -board_y, z frame.
    points=triangles*np.asarray(specification['scale'])
    matrix=np.eye(3)
    # KiCad model rotations are negative, applied X then Y then Z to points.
    for axis,angle in zip('xyz',specification['rotate']):
        matrix=Rotation.from_euler(axis,-angle,degrees=True).as_matrix()@matrix
    points=points@matrix.T+np.asarray(specification['offset'])
    bottom=component.get('side')=='B.Cu'
    if bottom: points=points*np.array([1,-1,-1])
    rotation=Rotation.from_euler('z',component.get('rotation_deg',0),degrees=True).as_matrix()
    points=points@rotation.T
    return points+np.array([component['x_mm'],-component['y_mm'],(-1 if bottom else 1)*board_thickness/2])
