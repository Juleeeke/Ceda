"""Build locally on each target OS. No shell commands or fixed system paths."""
from __future__ import annotations

import importlib.util
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import gmsh

root = Path(__file__).resolve().parents[1]
icon_directory=root/"src"/"ceda"/"resources"/"icons"
icon_path=icon_directory/("ceda.icns" if sys.platform=="darwin" else "ceda.ico" if sys.platform=="win32" else "ceda-icon.png")
if not icon_path.is_file():
    raise SystemExit("Native icon missing; run python scripts/make_icons.py first")
separator = ";" if sys.platform == "win32" else ":"
library = Path(gmsh.libpath)
if not library.is_file():
    raise SystemExit(f"Gmsh shared library not found: {library}")
args = [sys.executable,"-m","PyInstaller","--noconfirm","--clean","--name","Ceda",
        "--windowed","--icon",str(icon_path),"--paths",str(root/"src"),
        "--add-data",f"{root/'src'/'ceda'/'resources'}{separator}ceda/resources",
        "--add-binary",f"{library}{separator}.",
        "--specpath",str(root/"build"),
        "--copy-metadata","ceda","--copy-metadata","numpy","--copy-metadata","scipy",
        "--copy-metadata","shapely","--copy-metadata","gmsh",
        "--exclude-module","PySide6.QtWebEngineCore","--exclude-module","PySide6.QtWebEngineWidgets",
        "--exclude-module","PySide6.QtPdf","--exclude-module","PySide6.QtPdfWidgets",
        "--exclude-module","tkinter","--exclude-module","matplotlib",
        "--osx-bundle-identifier","io.juleeeke.ceda",str(root/"scripts"/"desktop_entry.py")]
if sys.platform != "darwin":
    index = args.index("--osx-bundle-identifier")
    del args[index:index+2]
environment = dict(os.environ,PYINSTALLER_CONFIG_DIR=str(root/"build"/"pyinstaller-cache"))
subprocess.run(args,cwd=root,env=environment,check=True)
if sys.platform == "darwin":
    from ceda import __version__
    bundle = root/"dist"/"Ceda.app"
    plist_path = bundle/"Contents"/"Info.plist"
    with plist_path.open("rb") as stream:
        metadata = plistlib.load(stream)
    metadata["CFBundleShortVersionString"] = __version__
    metadata["CFBundleVersion"] = __version__
    with plist_path.open("wb") as stream:
        plistlib.dump(metadata,stream)
    # Updating Info.plist invalidates the development bundle signature.
    subprocess.run(["codesign","--force","--deep","--sign","-",str(bundle)],check=True)
print("Built desktop app under",root/"dist")
