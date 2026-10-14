"""Native Qt layout for the user-selected white workbench preview (A)."""
from PySide6.QtCore import QSize,Qt
from PySide6.QtGui import QIcon,QPixmap
from PySide6.QtWidgets import (QApplication,QButtonGroup,QCheckBox,QComboBox,QDoubleSpinBox,
    QFormLayout,QFrame,QGroupBox,QHBoxLayout,QHeaderView,QLabel,QPushButton,QScrollArea,
    QTabBar,QTableWidget,QTextEdit,QVBoxLayout,QWidget)

from ceda.resources import app_icon
from .boardview import BoardView
from .theme import STYLE,glyph


def number(value,minimum=0.000001,maximum=100000,decimals=5):
    control=QDoubleSpinBox()
    control.setRange(minimum,maximum);control.setDecimals(decimals);control.setValue(value)
    return control


def label(text,name="muted"):
    widget=QLabel(text);widget.setObjectName(name)
    return widget


def divider():
    line=QFrame();line.setObjectName("divider");line.setFrameShape(QFrame.Shape.HLine)
    return line


def button(text,callback,name=None,symbol=None):
    widget=QPushButton(text)
    if name:widget.setObjectName(name)
    if symbol:widget.setIcon(glyph(symbol,"#ffffff" if name in {"run","export"} else "#828d9c"));widget.setIconSize(QSize(15,15))
    widget.clicked.connect(callback)
    return widget


def build_workbench(w):
    app=QApplication.instance();app.setStyleSheet(STYLE)
    identity=QIcon(str(app_icon()));app.setWindowIcon(identity);w.setWindowIcon(identity)
    w.resize(1440,930);w.setMinimumSize(1120,760)
    central=QWidget();overall=QHBoxLayout(central);overall.setContentsMargins(0,0,0,0);overall.setSpacing(0)
    sidebar=QWidget();sidebar.setObjectName("sidebar");sidebar.setFixedWidth(205)
    sidebar_layout=QVBoxLayout(sidebar);sidebar_layout.setContentsMargins(15,23,15,16);sidebar_layout.setSpacing(7)
    identity_row=QHBoxLayout();identity_row.setSpacing(8)
    image=QLabel();image.setPixmap(QPixmap(str(app_icon())).scaled(35,35,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    identity_row.addWidget(image);identity_row.addWidget(label("Ceda","brand"));identity_row.addWidget(label("0.1","brandVersion"));identity_row.addStretch()
    sidebar_layout.addLayout(identity_row);sidebar_layout.addSpacing(15)
    sidebar_layout.addWidget(button("导入 PCB",w.open_board,symbol="plus"));sidebar_layout.addSpacing(27)
    sidebar_layout.addWidget(label("工作空间","sectionLabel"));sidebar_layout.addSpacing(5)
    w.navigation=QButtonGroup(w);w.navigation.setExclusive(True)
    def overview():
        w.field.setCurrentIndex(2)
        if w.board:
            w.inspector.setPlainText(f"{w.board.path.name}\n\n{len(w.board.layers)} 个铜层\n{len(w.board.pads)} 个焊盘\n{len(w.board.vias)} 个过孔\n\n"+"\n".join(i.message for i in w.board.issues))
    def analysis():
        w.field.setCurrentIndex(0)
    def materials():
        w.advanced.setChecked(True)
        w.mesh_size.setFocus()
    for title,symbol,callback,enabled in [("板卡概览","board",overview,True),("供电分析","wave",analysis,True),
        ("叠层与材料","layers",materials,True),("器件模型","models",lambda:None,False),("分析报告","report",w.open_report,True)]:
        item=button(title,callback,"nav",symbol);item.setCheckable(True);item.setEnabled(enabled)
        if not enabled:item.setToolTip("器件模型库将在后续版本接入。")
        if title=="供电分析":item.setChecked(True)
        w.navigation.addButton(item);sidebar_layout.addWidget(item)
    sidebar_layout.addSpacing(26);sidebar_layout.addWidget(label("项目","sectionLabel"));sidebar_layout.addSpacing(3)
    w.project_button=button("演示板",lambda:overview() if w.board else w.open_demo(),"quiet","board")
    w.project_button.setToolTip("查看当前板卡；未导入时打开内置演示板")
    sidebar_layout.addWidget(w.project_button);sidebar_layout.addStretch()
    sidebar_layout.addWidget(label("本地工作空间","sectionLabel"));sidebar_layout.addWidget(label("数据与计算保留在本机"))
    overall.addWidget(sidebar)
    main=QWidget();main_layout=QVBoxLayout(main);main_layout.setContentsMargins(0,0,0,0);main_layout.setSpacing(0)
    top=QWidget();top.setObjectName("topbar");top.setFixedHeight(58)
    top_row=QHBoxLayout(top);top_row.setContentsMargins(25,0,24,0);top_row.setSpacing(8)
    w.breadcrumb=label("项目  ／  未导入板卡  ›  供电分析","breadcrumb");top_row.addWidget(w.breadcrumb);top_row.addStretch()
    top_row.addWidget(button("打开工况",w.open_config,"quiet"));top_row.addWidget(button("保存工况",w.save_config))
    top_row.addWidget(button("导出报告",w.export_results,"export","download"));main_layout.addWidget(top)
    workspace=QHBoxLayout();workspace.setContentsMargins(0,0,0,0);workspace.setSpacing(0)
    canvas_column=QWidget();canvas_layout=QVBoxLayout(canvas_column);canvas_layout.setContentsMargins(27,27,27,22);canvas_layout.setSpacing(0)
    heading=QHBoxLayout();text=QVBoxLayout();text.setSpacing(7);text.addWidget(label("供电完整性","title"))
    w.subtitle=label("导入保存后的 KiCad PCB，配置电源和本地回流。","subtitle");text.addWidget(w.subtitle)
    heading.addLayout(text);heading.addStretch();w.metric_label=label("等待导入","metric");heading.addWidget(w.metric_label,0,Qt.AlignmentFlag.AlignTop)
    canvas_layout.addLayout(heading);canvas_layout.addSpacing(22);canvas_layout.addWidget(divider())
    viewbar=QHBoxLayout();viewbar.setSpacing(12)
    w.field=QTabBar();w.field.setDrawBase(False);w.field.setExpanding(False)
    for name in ("电流密度","电压分布","铜层几何","板温（实验性）"):w.field.addTab(name)
    w.field.currentChanged.connect(w.update_view)
    viewbar.addWidget(w.field);viewbar.addStretch()
    w.layer=QComboBox();w.layer.setFixedWidth(74);w.layer.setAccessibleName("铜层");w.layer.currentTextChanged.connect(w.update_view)
    viewbar.addWidget(w.layer)
    fit=button("",lambda:w.view.render_board(fit=True),"quiet","fit");fit.setFixedWidth(28);fit.setToolTip("适应画布");fit.setAccessibleName("适应画布");viewbar.addWidget(fit)
    canvas_layout.addLayout(viewbar);canvas_layout.addWidget(divider());canvas_layout.addSpacing(18)
    canvas_frame=QFrame();canvas_frame.setObjectName("canvas");inside=QVBoxLayout(canvas_frame);inside.setContentsMargins(12,9,12,9);inside.setSpacing(4)
    inside.addWidget(label("PCB 铜层  /  供电与回流网络"));w.view=BoardView();w.view.pad_clicked.connect(w.select_pad)
    inside.addWidget(w.view,1);canvas_layout.addWidget(canvas_frame,1);canvas_layout.addSpacing(11)
    legend_row=QHBoxLayout();w.legend=label("几何预览 · 尚未求解","legend");legend_row.addWidget(w.legend);legend_row.addStretch();legend_row.addWidget(label("点击焊盘定位 · 滚轮缩放"));canvas_layout.addLayout(legend_row)
    canvas_layout.addSpacing(20);canvas_layout.addWidget(divider());canvas_layout.addSpacing(16)
    result_header=QHBoxLayout();result_header.addWidget(label("负载端供电","inspectorTitle"));result_header.addStretch()
    result_header.addWidget(button("查看完整报告 ↗",w.open_report,"quiet"));canvas_layout.addLayout(result_header)
    w.result_table=QTableWidget(0,4);w.result_table.setHorizontalHeaderLabels(["负载 / 引脚","本地 VDD–GND","最低电压 / V","判定"])
    w.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);w.result_table.verticalHeader().setVisible(False)
    w.result_table.setShowGrid(False);w.result_table.setFixedHeight(116);w.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    canvas_layout.addWidget(w.result_table);workspace.addWidget(canvas_column,1)
    panel=QWidget();panel.setObjectName("inspectorPanel");panel.setFixedWidth(288)
    panel_outer=QVBoxLayout(panel);panel_outer.setContentsMargins(0,0,0,0);panel_outer.setSpacing(0)
    scroller=QScrollArea();scroller.setWidgetResizable(True);scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    inspector_body=QWidget();form_layout=QVBoxLayout(inspector_body);form_layout.setContentsMargins(20,26,20,18);form_layout.setSpacing(13)
    inspector_head=QHBoxLayout();inspector_head.addWidget(label("分析工况","inspectorTitle"));inspector_head.addStretch();inspector_head.addWidget(label("DC / 稳态"));form_layout.addLayout(inspector_head)
    form_layout.addSpacing(10);form_layout.addWidget(label("电源端口","sectionTitle"))
    source=QFormLayout();source.setVerticalSpacing(8)
    w.source_p,w.source_n=QComboBox(),QComboBox();w.voltage=number(3.3)
    source.addRow("正极焊盘",w.source_p);source.addRow("回流焊盘",w.source_n);source.addRow("电压 / V",w.voltage)
    form_layout.addLayout(source);form_layout.addSpacing(6);form_layout.addWidget(divider());form_layout.addSpacing(5)
    form_layout.addWidget(label("负载端口","sectionTitle"))
    load=QFormLayout();load.setVerticalSpacing(8);w.load_p,w.load_n=QComboBox(),QComboBox();w.current=number(0.1);w.minimum=number(3.0,minimum=0)
    load.addRow("VDD 焊盘",w.load_p);load.addRow("本地 GND",w.load_n);load.addRow("电流 / A",w.current);load.addRow("最低电压 / V",w.minimum)
    form_layout.addLayout(load)
    w.loads=QTableWidget(0,4);w.loads.setHorizontalHeaderLabels(["VDD","GND","A","最低 V"])
    w.loads.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);w.loads.verticalHeader().setVisible(False);w.loads.setShowGrid(False);w.loads.setFixedHeight(79)
    form_layout.addWidget(w.loads)
    load_actions=QHBoxLayout();load_actions.addWidget(button("添加负载",w.add_load,"quiet","plus"));load_actions.addStretch()
    load_actions.addWidget(button("删除",lambda:w.loads.removeRow(w.loads.currentRow()),"quiet"));form_layout.addLayout(load_actions)
    form_layout.addWidget(divider());form_layout.addSpacing(3)
    w.advanced=QGroupBox("网格与材料");w.advanced.setCheckable(True);w.advanced.setChecked(False)
    advanced_contents=QWidget();advanced=QFormLayout(advanced_contents);advanced.setContentsMargins(0,4,0,0);advanced.setVerticalSpacing(8)
    w.mesh_size=number(0.5,minimum=0.02,maximum=5,decimals=3);w.copper=number(0,minimum=0,maximum=1,decimals=4)
    w.plating=number(0,minimum=0,maximum=0.2,decimals=4);w.ambient=number(25,minimum=-50,maximum=150,decimals=1)
    advanced.addRow("网格 / mm",w.mesh_size);advanced.addRow("铜厚 / mm",w.copper);advanced.addRow("孔镀层 / mm",w.plating);advanced.addRow("环境 / °C",w.ambient)
    note=label("铜厚 0：使用文件叠层。\n有镀铜孔时，孔镀层厚度必填。");note.setWordWrap(True);advanced.addRow(note)
    group=QVBoxLayout(w.advanced);group.setContentsMargins(0,6,0,0);group.addWidget(advanced_contents)
    w.advanced.toggled.connect(advanced_contents.setVisible);advanced_contents.setVisible(False);form_layout.addWidget(w.advanced)
    w.refine=QCheckBox("使用细化网格复核");w.refine.setChecked(True);form_layout.addWidget(w.refine)
    form_layout.addWidget(divider());form_layout.addSpacing(4);form_layout.addWidget(label("对象与计算质量","sectionTitle"))
    w.inspector=QTextEdit();w.inspector.setReadOnly(True);w.inspector.setMinimumHeight(100);w.inspector.setMaximumHeight(180);form_layout.addWidget(w.inspector)
    form_layout.addStretch()
    scroller.setWidget(inspector_body);panel_outer.addWidget(scroller,1)
    bottom=QWidget();bottom_layout=QVBoxLayout(bottom);bottom_layout.setContentsMargins(20,12,20,18);bottom_layout.setSpacing(8)
    w.run_button=button("开始供电分析",w.run,"run","play");w.run_button.setMinimumHeight(35)
    w.cancel_button=button("取消计算",w.cancel,"quiet");w.cancel_button.setEnabled(False)
    controls=QHBoxLayout();controls.setSpacing(7);controls.addWidget(w.run_button,1);controls.addWidget(w.cancel_button)
    bottom_layout.addLayout(controls);scope=label("规定工况 DC · 芯片功能与实测校准未验证");scope.setWordWrap(True);bottom_layout.addWidget(scope)
    w.log=QTextEdit();w.log.setReadOnly(True);w.log.setFixedHeight(48);bottom_layout.addWidget(w.log)
    panel_outer.addWidget(bottom);workspace.addWidget(panel)
    main_layout.addLayout(workspace,1);overall.addWidget(main,1);w.setCentralWidget(central)
    w.status=QLabel("本地工作空间 · 等待导入 PCB");w.status.setObjectName("muted");w.statusBar().addWidget(w.status,1)
    w.statusBar().addPermanentWidget(label("F.Cu  ·  Ceda 0.1"));w.statusBar().setSizeGripEnabled(False)
    w.view.render_board()
