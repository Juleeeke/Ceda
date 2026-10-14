# Ceda

跨平台、本地运行的 KiCad 后布局供电分析工作台。macOS / Apple Silicon 为当前首发验证平台，Qt/PySide6 桌面与 Python 计算核心同样面向 Windows/Linux。

当前版本 **0.1.0**：真实铜几何导入、2.5D 有限元 DC 供电/回流分析、两级网格复核、布局定位与可复现报告。提供实验性板级热扩散与电热迭代、单端口布局电阻回注 ngspice 的 RC 上电/负载瞬态。详见 [能力边界](docs/CAPABILITIES.md)。

## 开始使用

需要 Python 3.11 或更新版本。

```sh
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ceda gui --demo
```

也可使用 uv：`uv sync --extra dev`，然后 `uv run ceda gui --demo`。

桌面中选择 `.kicad_pcb`，配置电源与负载的正负焊盘、铜厚/网格及最低供电电压，运行后查看每层电流密度和本地 VDD–GND。点击焊盘可定位对象；报告导出包括 HTML、JSON、CSV、SVG、输入快照及配置。

```sh
ceda inspect your-board.kicad_pcb
ceda demo --output outputs/demo
ceda analyze your-board.kicad_pcb --config scenario.json --output outputs/my-board
ceda analyze your-board.kicad_pcb --config scenario.json --netlist exported.xml --output outputs/my-board
ceda transient outputs/demo/result.json --output outputs/transient
```

`transient` 需要可在 PATH 中找到的 ngspice。其单电源单负载限制是为避免把共享回流错误等效成独立串联电阻。这个 RC 示例不覆盖稳压器或 MCU 内部启动行为。

## 开发与验证

```sh
python -m pytest
python scripts/build_desktop.py
```

每个 OS/架构应在对应平台打包；macOS 输出 `dist/Ceda.app`，Windows/Linux 使用同一构建入口。GUI 和长时间求解使用独立进程，求解失败及取消不会阻塞编辑界面。

数据输入遵循 KiCad 官方文件格式；目前读取保存后的铜结果，不自动修改或重新铺铜。尚未支持的铜对象会阻止分析。模型来源、工况、网格与求解范围随报告保留。

本版本尚未达到原设计中的全部 P1 能力。完整器件模型、原理图原生联动、AC/高速互连、专业封装热模型和固件协同列于 [路线图](docs/ROADMAP.md)。数值验证与实测精度是不同证据；当前 `hardware_verified=false`。

## 文档与许可

- [架构决策](docs/architecture/adr-001-portable-desktop.md)
- [能力和限制](docs/CAPABILITIES.md)
- [工况格式](docs/SCENARIOS.md)
- [原始需求](docs/01_需求与完整链路设计.md)
- [生态调研](docs/02_开源与商业工具调研.md)
- [第三方许可](THIRD_PARTY_NOTICES.md)

Ceda 自有代码遵循仓库 MIT 许可证；Gmsh、Qt、数值库和外部模型分别遵循其许可证，桌面分发包不能只按 MIT 描述全部依赖。
