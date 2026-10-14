# 工况格式

桌面可打开/保存 JSON 工况；初始示例见 `src/ceda/resources/demo.json`。焊盘端口采用 `器件位号.焊盘号`，网络名仅用于识别，电流路径取决于真实铜连接。

```json
{
  "schema_version": 1,
  "name": "MCU 满载",
  "sources": [{"positive":"J1.1","negative":"J1.2","voltage_v":3.3}],
  "loads": [{"positive":"U1.1","negative":"U1.2","current_a":0.5,"minimum_voltage_v":3.0}],
  "settings": {
    "mesh_size_mm": 0.5,
    "max_nodes": 150000,
    "copper_thickness_mm": null,
    "via_plating_mm": 0.025,
    "ambient_c": 25,
    "mesh_refinement": true,
    "thermal_enabled": false
  }
}
```

示例参数是说明格式，不代表用户实际板卡材料。`copper_thickness_mm=null` 使用 PCB 叠层；没有叠层数据时分析会报错。有镀铜孔需要明确 `via_plating_mm`；缺少层 Z 位置时可明确指定 `layer_positions_mm`，单位 mm，不能自动猜测。

`minimum_voltage_v=null` 表示没有工程判定阈值，对应未验证。恒流负载只代表规定工况，不模拟任意 MCU 功耗状态或稳压器行为。默认两级网格比较：h 与 h/2，负载电压差需小于 `max(voltage_tolerance_v, relative_tolerance × DC 压降)`，默认 1mV 或压降的 2%。这是初始数值门槛，不能替代精度校准。

实验性热场需要显式设置：

```json
{
  "thermal_enabled": true,
  "thermal_h_w_m2k": 10,
  "thermal_fr4_k_w_mk": 0.3,
  "component_heat_w": {"U1": 0.1},
  "thermal_iterations": 20,
  "thermal_tolerance_c": 0.2
}
```

以上是设置字段片段，应放进完整工况的 `settings` 中；换热和功耗必须来自实际项目。`component_heat_w` 之外的器件没有自动热模型，报告会列出未配置器件。热场给出实验性平均板温，不给出可信结温。

通过 `--netlist` 提供 KiCad 导出的 XML 网表，可增加原理图引脚网络与 PCB 分配的一致性检查。原始 `.kicad_sch` 自动转模型仍在路线图。
