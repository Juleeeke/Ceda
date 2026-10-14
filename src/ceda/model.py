from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    objects: list[str] = field(default_factory=list)


@dataclass
class CopperLayer:
    name: str
    thickness_mm: float | None
    z_mm: float | None


@dataclass
class Pad:
    id: str
    reference: str
    number: str
    net: str
    layers: list[str]
    geometry: BaseGeometry
    x: float
    y: float
    drill_mm: float | None = None
    plated: bool = False


@dataclass
class Via:
    id: str
    net: str
    layers: list[str]
    x: float
    y: float
    diameter_mm: float
    drill_mm: float


@dataclass
class Board:
    path: Path
    sha256: str
    version: int
    layers: list[CopperLayer]
    pads: list[Pad]
    vias: list[Via]
    copper: dict[tuple[str, str], BaseGeometry]
    outline: BaseGeometry | None
    issues: list[Issue]
    components: dict[str, dict[str, Any]]
    board_thickness_mm: float | None

    def pad(self, identifier: str) -> Pad:
        matches = [p for p in self.pads if p.id == identifier]
        if len(matches) != 1:
            from .errors import CedaError
            raise CedaError(f"焊盘 {identifier!r} 应唯一，实际找到 {len(matches)} 个。")
        return matches[0]

    def summary(self) -> dict:
        return {
            "path": str(self.path), "sha256": self.sha256, "version": self.version,
            "layers": [asdict(layer) for layer in self.layers],
            "nets": sorted({net for net, _ in self.copper if net}),
            "pad_count": len(self.pads), "via_count": len(self.vias),
            "components": self.components,
            "pads": [{"id": p.id, "net": p.net, "layers": p.layers,
                      "x_mm": p.x, "y_mm": p.y} for p in self.pads],
            "copper": [{"net": net, "layer": layer, "area_mm2": shape.area,
                        "islands": len(shape.geoms) if hasattr(shape, "geoms") else 1}
                       for (net, layer), shape in self.copper.items()],
            "outline_area_mm2": self.outline.area if self.outline is not None else None,
            "board_thickness_mm": self.board_thickness_mm,
            "issues": [asdict(issue) for issue in self.issues],
        }
