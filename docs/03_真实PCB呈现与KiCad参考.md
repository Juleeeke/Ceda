# PCB 二维与三维呈现

本次交付把 PCB 呈现与数值结果分开。三维窗口用于检查文件中的机械与制造几何；它本身不代表已经执行电磁场、芯片功能或整板实物验证。

## 学习 KiCad 的具体部分

查阅时间：2026-10-15。没有将下列 GPL 源文件复制、翻译或链接进 Ceda；使用现有 Shapely、Qt 与 Gmsh 重新实现几何链路。

| 官方资料 | 对 Ceda 的直接影响 |
|---|---|
| [pcb_painter.cpp](https://github.com/KiCad/kicad-source-mirror/blob/master/pcbnew/pcb_painter.cpp) | 图层配色、活动层突出、铜区与走线分开、按缩放级别隐藏过小标签、钻孔与焊盘分别绘制 |
| [KiCad S-expression parser](https://github.com/KiCad/kicad-source-mirror/blob/master/pcbnew/pcb_io/kicad_sexpr/pcb_io_kicad_sexpr_parser.cpp) | pad 的 at 角度是板坐标系绝对角度；修复原有封装旋转被重复叠加的问题 |
| [board_adapter.cpp](https://github.com/KiCad/kicad-source-mirror/blob/master/3d-viewer/3d_canvas/board_adapter.cpp) | 依据叠层定位外铜层、区分板体与技术层、正反面器件坐标变换 |
| [3d_math.cpp](https://docs.kicad.org/doxygen/3d__math_8cpp_source.html) | 模型的缩放、负角度 X/Y/Z 旋转、偏移，再变换到封装位置 |
| [KiCad PCB 文档](https://docs.kicad.org/master/en/pcbnew/pcbnew.html) | 图层可见性、三维模型路径、实体检查与求解结果分别呈现 |
| [Qt Quick 3D Geometry](https://doc.qt.io/qt-6/qquick3dgeometry.html) | 本地 GPU 网格、深度遮挡、材质、抗锯齿；软件栅格器使用同一套毫米三角面用于无显示器验证 |

## 数据链路

`.kicad_pcb → 严格语法读取 → 电气铜域 + 显示对象 → 2D 或毫米实体网格 → 原生视口`

- 电气铜域仍由已保存的 filled_polygon、走线、焊盘与过孔并集得到，求解器不使用绘图颜色或显示网格。
- 保留显示对象：走线宽度/网络/图层、封装和板上图形、可见位号文字、钻孔/槽形非镀铜孔、阻焊开窗、模型路径及变换。
- 板框圆弧离散后保留精确起止点，避免本来闭合的线段因为浮点末位误差不能闭合。
- 普通矩形、圆形、椭圆形、圆角矩形及带受支持 primitives 的 custom 焊盘可读取；其他不支持对象明确报错。
- 导入尚不支持的镀铜槽孔/偏心钻孔时仍会阻断，不会静默换成圆孔。

## 二维

白色工作台内提供深色工程画布，也可切换浅色。显示真实毫米位置的板框、活动铜层、其他铜层的弱化叠加、走线、焊盘、过孔、钻孔、丝印、可选 Fab/Courtyard。支持拖动平移、光标位置缩放、坐标、动态网格、比例尺、引脚选择与可选求解网格。

数值热图只使用求解报告中的网络和层；未求解部分保留几何，不插值成“整板通过”。三维模式明确说明未叠加场结果。

## 三维

- 真实板框（含内切口）和文件板厚；板厚未知时不代填 1.6 mm。
- 板体、外铜、阻焊开窗、丝印与通孔内壁使用实际二维几何构造；三角剖分保留孔洞。
- 显示坐标为右手系 `(pcb_x, -pcb_y, z)`，单位毫米，正交投影避免透视造成尺寸误判。
- STEP/STP：Gmsh 内含的 OpenCASCADE 转换真实表面；在独立子进程主线程执行，避免 CAD 读取库故障影响主窗口。解析警告会显示“模型完整性待核实”。
- VRML 2：支持 IndexedFaceSet、Coordinate、DEF/USE、材质颜色、Group/Transform 变换；KiCad WRL 的 0.1 英寸单位换算为 2.54 mm。
- `${KIPRJMOD}`、系统环境变量和用户选择的 KiCad 模型库根目录用于定位实际模型文件。WRL 缺失时只尝试同路径、同名 STEP；不猜测近似器件。
- 缺失模型列出位号和路径，不生成猜测高度的替代盒子。
- 支持等轴、俯视、背面，拖动旋转，Shift/右键拖动平移，滚轮缩放与适应窗口。

## 准确性边界

这是面向 PCB 的几何视口，还不能称为 KiCad 全功能查看器或实物扫描复原：

1. 缺少阻焊颜色时使用绿色显示预设；金属外观为显示预设，不能推断实际表面处理。系统字体近似丝印字形，不能替代 KiCad 原始笔画字体或制造文件。
2. 技术层有微小绘图分离量以避免深度闪烁，不作为制造/求解尺寸。内层铜的三维剖切、盲埋孔完整腔体、焊锡堆积与透明材质尚未完整实现；当前实体模式不用于这些特征的尺寸判定。
3. 不支持任意 VRML 场景、纹理和所有 STEP 材质语义。曲面三角化会产生显示离散误差，不能据此测量接触/间隙公差。
4. 三维形状是否和实际采购器件一致，仍取决于设计文件关联的模型及供应商资料。
5. 官方测试板本身出现铜超板框预检提示。显示可检查该文件，求解仍保持阻断；没有把“能显示”当作“可以打板”。

## 本地真实板验证

使用 [KiCad 官方 StickHub 示例](https://github.com/KiCad/kicad-source-mirror/tree/master/demos/stickhub)：2 层、94 个封装、273 个电气焊盘、87 个过孔，板框外包尺寸 16.5 × 40 mm，文件板厚 1.6 mm。

本机验证素材放在 `outputs/reference`，原始 PCB 未修改。模型加载结果以界面为准：本次已找到并读取 86/93 个模型引用，其余路径缺失和未关联模型被列明；部分 STEP 文件有读取器引用警告，不计为完整性认证。

原始 PCB 和项目模型使用作者的 CC BY-NC-SA 4.0 及附加例外条款，标准模型使用 KiCad 库的 CC BY-SA 4.0 及库例外。验证素材保留来源/许可并仅留在被忽略的本地 outputs 中，不随 Ceda MIT 源码或应用包重新分发。截图用于本地检查，不作为无条件可商用的素材。

打开方式：导入 `outputs/reference/StickHub.kicad_pcb`，选择“三维实体”，通过“模型目录”选择 `outputs/reference/library`。不安装 KiCad 也可以使用已有模型；Ceda 不会自动联网寻找芯片模型。
