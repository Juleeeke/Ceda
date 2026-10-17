# Third-party dependencies and distribution

Ceda's own sources use MIT, as stated in LICENSE. Dependencies retain their own terms.

| Dependency | License / source |
|---|---|
| Python | PSF, https://www.python.org/psf/license/ |
| PySide6 / Qt | LGPLv3/GPLv3 or commercial depending on modules, https://doc.qt.io/qtforpython-6/licenses.html |
| Gmsh | GPL v2 or later with exception; commercial options, https://gmsh.info/#Licensing |
| NumPy | BSD-3-Clause, https://github.com/numpy/numpy/blob/main/LICENSE.txt |
| SciPy | BSD-3-Clause plus bundled library notices, https://github.com/scipy/scipy/blob/main/LICENSE.txt |
| Shapely / GEOS | BSD-3-Clause / LGPL respectively, https://github.com/shapely/shapely/blob/main/LICENSE.txt |
| ngspice (optional external) | Primarily modified BSD with component exceptions, https://ngspice.sourceforge.io/devel.html |
| PyInstaller (build tooling) | GPL with exception for generated executables, https://pyinstaller.org/en/stable/license.html |

The current desktop build is a local development artifact. Redistributing a bundle containing Gmsh/Qt and other libraries requires the appropriate notices, source/relinking materials and terms for the exact built versions. An independent process boundary alone does not establish license compliance. Do not describe the entire binary bundle as MIT-only. No vendor semiconductor model is bundled with this release.

## PCB viewport addition

The native 3D viewport uses Qt Quick 3D, which has GPLv3/commercial licensing (not the general LGPL option applicable to some other Qt modules): https://doc.qt.io/qt-6/qtquick3d-index.html#licenses-and-attributions. Its use does not change the license notice of independently authored Ceda source files, but binary redistribution must follow the applicable combined-work terms. See the local development-artifact scope above.

KiCad source was read for format semantics and rendering architecture, without copying/translating or linking KiCad implementation. Local third-party PCB/model verification fixtures under ignored `outputs/reference` retain their original licenses and are not bundled with this application. Details: `docs/03_真实PCB呈现与KiCad参考.md`.

## SwiftUI macOS client

The new macOS frontend uses Apple's system SwiftUI, AppKit and MetalKit frameworks, without a third-party Swift package. It does not embed Qt Widgets/Quick/Quick3D. The bundled engine retains Gmsh, SciPy, GEOS and QtGui/Core (for 3D font outlines), with their existing obligations. The native binary bundle must not be described as MIT-only. The real-board verification fixtures and vendor models remain local-only; only the Ceda synthetic demo and original generated Ceda icon are included in the bundle.
