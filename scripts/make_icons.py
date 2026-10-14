"""Encode the unmodified imagegen artwork into native app icon formats."""
from pathlib import Path
import struct
import subprocess
import sys

from PySide6.QtCore import QBuffer,QIODevice,Qt
from PySide6.QtGui import QImage

root=Path(__file__).resolve().parents[1]
directory=root/"src"/"ceda"/"resources"/"icons"
image=QImage(str(directory/"ceda-icon.png"))
if image.isNull():
    raise SystemExit("Missing generated Ceda icon")

def scaled(size):
    return image.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)

# PNG-compressed ICO frames are supported by Windows Vista and later.
sizes=[16,24,32,48,64,128,256]
frames=[]
for size in sizes:
    buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not scaled(size).save(buffer,"PNG"):
        raise SystemExit("Failed to encode icon frame")
    frames.append(bytes(buffer.data()))
offset=6+16*len(frames)
header=struct.pack("<HHH",0,1,len(frames))
entries=[]
for size,frame in zip(sizes,frames):
    entries.append(struct.pack("<BBBBHHII",0 if size==256 else size,0 if size==256 else size,0,0,1,32,len(frame),offset))
    offset+=len(frame)
(directory/"ceda.ico").write_bytes(header+b"".join(entries)+b"".join(frames))
if sys.platform=="darwin":
    iconset=root/"build"/"Ceda.iconset";iconset.mkdir(parents=True,exist_ok=True)
    for size in (16,32,128,256,512):
        for ratio in (1,2):
            name=f"icon_{size}x{size}"+("@2x" if ratio==2 else "")+".png"
            if not scaled(size*ratio).save(str(iconset/name)):
                raise SystemExit("Failed to save native icon frame")
    subprocess.run(["iconutil","-c","icns",str(iconset),"-o",str(directory/"ceda.icns")],check=True)
print("Icon files ready:",directory)
