from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .errors import CedaError


@dataclass
class Source:
    positive: str
    negative: str
    voltage_v: float


@dataclass
class Load:
    positive: str
    negative: str
    current_a: float
    minimum_voltage_v: float | None = None
    label: str = ""


@dataclass
class Settings:
    mesh_size_mm: float = 0.5
    max_nodes: int = 150000
    copper_thickness_mm: float | None = None
    via_plating_mm: float | None = None
    layer_positions_mm: dict[str, float] = field(default_factory=dict)
    resistivity_ohm_m: float = 1.724e-8
    ambient_c: float = 25.0
    temperature_coefficient: float = 0.00393
    mesh_refinement: bool = True
    voltage_tolerance_v: float = 0.001
    relative_tolerance: float = 0.02
    thermal_enabled: bool = False
    thermal_h_w_m2k: float | None = None
    thermal_fr4_k_w_mk: float | None = None
    thermal_iterations: int = 12
    thermal_tolerance_c: float = 0.2
    component_heat_w: dict[str, float] = field(default_factory=dict)


@dataclass
class AnalysisConfig:
    sources: list[Source]
    loads: list[Load]
    settings: Settings = field(default_factory=Settings)
    name: str = "供电工况"
    schema_version: int = 1

    @classmethod
    def from_dict(cls, data):
        try:
            if data.get("schema_version", 1) != 1:
                raise ValueError("不支持的工况版本")
            config = cls([Source(**s) for s in data["sources"]],
                         [Load(**s) for s in data["loads"]],
                         Settings(**data.get("settings", {})), data.get("name", "供电工况"))
            config.validate()
            return config
        except (KeyError, TypeError, ValueError) as exc:
            raise CedaError(f"工况文件无效：{exc}") from exc

    @classmethod
    def read(cls, path):
        try:
            return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise CedaError(f"无法读取工况文件：{exc}") from exc

    def to_dict(self):
        return asdict(self)

    def validate(self):
        def finite(value, label, positive=False):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (positive and value <= 0):
                raise CedaError(f"{label} 必须是{'正的' if positive else ''}有限数值。")
        if not self.sources or not self.loads:
            raise CedaError("至少配置一个电源和一个负载。")
        for source in self.sources:
            finite(source.voltage_v, "电源电压", True)
            if source.positive == source.negative:
                raise CedaError("电源正负端不能是同一焊盘。")
        for load in self.loads:
            finite(load.current_a, "负载电流", True)
            if load.positive == load.negative:
                raise CedaError("负载正负端不能是同一焊盘。")
            if load.minimum_voltage_v is not None:
                finite(load.minimum_voltage_v, "最低负载电压", True)
        s = self.settings
        for attr in ("mesh_size_mm", "resistivity_ohm_m", "voltage_tolerance_v", "relative_tolerance", "thermal_tolerance_c"):
            finite(getattr(s, attr), attr, True)
        for attr in ("copper_thickness_mm", "via_plating_mm", "thermal_h_w_m2k", "thermal_fr4_k_w_mk"):
            if getattr(s, attr) is not None:
                finite(getattr(s, attr), attr, True)
        finite(s.ambient_c, "环境温度")
        finite(s.temperature_coefficient, "电阻温度系数")
        if s.temperature_coefficient < 0:
            raise CedaError("铜温度系数不能为负数。")
        if not isinstance(s.max_nodes, int) or s.max_nodes < 100 or s.max_nodes > 2000000:
            raise CedaError("网格节点预算应在 100–2,000,000 之间。")
        if not isinstance(s.thermal_iterations, int) or not 1 <= s.thermal_iterations <= 100:
            raise CedaError("电热迭代次数应在 1–100 之间。")
        for name, position in s.layer_positions_mm.items():
            finite(position, f"{name} 层位置")
        for ref, power in s.component_heat_w.items():
            finite(power, f"{ref} 功耗")
            if power < 0:
                raise CedaError("器件热源不能为负。")
        if s.thermal_enabled and (s.thermal_h_w_m2k is None or s.thermal_fr4_k_w_mk is None):
            raise CedaError("热分析必须明确提供换热系数和 FR4 热导率。")
