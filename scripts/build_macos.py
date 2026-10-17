"""Build the SwiftUI app and its independent local analysis engine on macOS."""
from __future__ import annotations
import os,plistlib,shutil,subprocess,sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
if sys.platform!='darwin':raise SystemExit('SwiftUI packaging must run on macOS; use build_desktop.py for other platforms.')
cache=root/'build'/'clang-cache';cache.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,CLANG_MODULE_CACHE_PATH=str(cache),SWIFT_MODULECACHE_PATH=str(cache),PYINSTALLER_CONFIG_DIR=str(root/'build'/'pyinstaller-cache-native'))
subprocess.run(['swift','build','--package-path',str(root/'native/macos'),'--scratch-path',str(root/'build/swiftpm'),
    '--cache-path',str(root/'build/swift-cache'),'--config-path',str(root/'build/swift-config'),
    '--security-path',str(root/'build/swift-security'),'--disable-sandbox','-c','release',
    '-Xswiftc','-module-cache-path','-Xswiftc',str(cache)],cwd=root,env=env,check=True)
import gmsh
args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--name','CedaEngine','--console',
    '--paths',str(root/'src'),'--distpath',str(root/'build/native-engine'),'--workpath',str(root/'build/native-worker'),
    '--specpath',str(root/'build/native-spec'),'--add-binary',f'{gmsh.libpath}:.',
    '--add-data',f'{root}/src/ceda/resources/demo.kicad_pcb:ceda/resources',
    '--add-data',f'{root}/src/ceda/resources/demo.json:ceda/resources']
for name in ('ceda','numpy','scipy','shapely','gmsh'):args+=['--copy-metadata',name]
for name in ('ceda.gui','PySide6.QtWidgets','PySide6.QtQuick3D','PySide6.QtQuickWidgets','PySide6.QtQml','PySide6.QtQuick',
    'PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtPdf','PySide6.QtPdfWidgets','tkinter','matplotlib'):
    args+=['--exclude-module',name]
args+=[str(root/'scripts/native_engine_entry.py')]
subprocess.run(args,cwd=root,env=env,check=True)
app=root/'dist'/'Ceda SwiftUI.app'
if app.exists():shutil.rmtree(app)
contents=app/'Contents';macos=contents/'MacOS';resources=contents/'Resources'
macos.mkdir(parents=True);resources.mkdir()
shutil.copy2(root/'build/swiftpm/release/CedaNative',macos/'CedaNative')
shutil.copy2(root/'src/ceda/resources/icons/ceda.icns',resources/'ceda.icns')
shutil.copytree(root/'build/native-engine/CedaEngine',resources/'Engine/CedaEngine',symlinks=True)
(resources/'Demo').mkdir()
for name in ('demo.json','demo.kicad_pcb'):shutil.copy2(root/'src/ceda/resources'/name,resources/'Demo'/name)
shutil.copy2(root/'THIRD_PARTY_NOTICES.md',resources/'THIRD_PARTY_NOTICES.md')
info={'CFBundleExecutable':'CedaNative','CFBundleIdentifier':'io.juleeeke.ceda.native','CFBundleName':'Ceda',
    'CFBundleDisplayName':'Ceda','CFBundlePackageType':'APPL','CFBundleShortVersionString':'0.2.0','CFBundleVersion':'2',
    'CFBundleIconFile':'ceda.icns','LSMinimumSystemVersion':'14.0','NSHighResolutionCapable':True,
    'NSPrincipalClass':'NSApplication','NSSupportsAutomaticGraphicsSwitching':True}
with (contents/'Info.plist').open('wb') as stream:plistlib.dump(info,stream)
subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True)
subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
print('Built native SwiftUI application:',app)
