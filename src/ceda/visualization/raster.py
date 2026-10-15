"""Orthographic, depth-tested triangle rasterizer for portable CAD inspection.

World dimensions remain in millimetres. A z buffer resolves occlusion, including
parts over drilled board geometry; this is not an isometric drawing of boxes.
"""
import numpy as np
from scipy.spatial.transform import Rotation


def render(triangles, colors, size, center, span, yaw=-22, tilt=48, zoom=1, pan=(0,0)):
    width,height=size
    image=np.empty((height,width,3),np.uint8)
    ramp=np.linspace(247,230,height,dtype=np.uint8)
    image[:]=ramp[:,None,None]
    depth=np.full((height,width),-np.inf,np.float32)
    ids=np.full((height,width),-1,np.int32)
    if not len(triangles):return image,ids
    matrix=Rotation.from_euler('x',tilt,degrees=True).as_matrix()@Rotation.from_euler('z',yaw,degrees=True).as_matrix()
    camera=(triangles-center)@matrix.T
    scale=min(width,height)*0.9/span*zoom
    screen=camera.copy();screen[:,:,0]=camera[:,:,0]*scale+width/2+pan[0]*width
    screen[:,:,1]=-camera[:,:,1]*scale+height/2+pan[1]*height
    normals=np.cross(camera[:,1]-camera[:,0],camera[:,2]-camera[:,0])
    normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-20)
    # Two-sided surface lighting also handles imported CAD face winding.
    normals*=np.where(normals[:,2,None]<0,-1,1)
    light=np.array([-0.3,0.5,0.82]);light/=np.linalg.norm(light)
    diffuse=np.maximum(normals@light,0)
    rgb=np.clip(colors*(0.45+0.55*diffuse[:,None]),0,1)*255
    # Large faces first improve rejection efficiency; the z buffer sets visibility.
    for index in np.argsort(np.mean(camera[:,:,2],axis=1)):
        tri=screen[index]
        left=max(0,int(np.floor(tri[:,0].min())));right=min(width-1,int(np.ceil(tri[:,0].max())))
        top=max(0,int(np.floor(tri[:,1].min())));bottom=min(height-1,int(np.ceil(tri[:,1].max())))
        if left>right or top>bottom:continue
        a,b,c=tri;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-10:continue
        x=np.arange(left,right+1)[None,:]+0.5;y=np.arange(top,bottom+1)[:,None]+0.5
        u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den
        v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den
        w=1-u-v;z=u*a[2]+v*b[2]+w*c[2]
        region=depth[top:bottom+1,left:right+1]
        visible=(u>=-1e-8)&(v>=-1e-8)&(w>=-1e-8)&(z>=region)
        region[visible]=z[visible]
        image[top:bottom+1,left:right+1][visible]=rgb[index]
        ids[top:bottom+1,left:right+1][visible]=index
    return image,ids
