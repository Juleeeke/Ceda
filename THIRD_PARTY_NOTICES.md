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
