from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication,QCheckBox,QComboBox,QDoubleSpinBox,QFileDialog,
    QFormLayout,QGroupBox,QHBoxLayout,QHeaderView,QLabel,QMainWindow,QMessageBox,QPushButton,
    QSplitter,QTableWidget,QTableWidgetItem,QTextEdit,QVBoxLayout,QWidget)

from ceda.config import AnalysisConfig,Load,Settings,Source
from ceda.errors import CedaError
from ceda.kicad import load_board
from ceda.resources import demo_board,demo_config
from .boardview import BoardView

STYLE = """
QMainWindow,QWidget { background:#101923; color:#dce6ee; font-family:'.AppleSystemUIFont','Segoe UI',sans-serif; font-size:13px; }
QGroupBox { border:1px solid #2b3e50; border-radius:9px; margin-top:16px; padding:13px 9px 8px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:11px; color:#b0c8d8; }
QPushButton { background:#243b4d; border:1px solid #385468; border-radius:7px; padding:8px 13px; }
QPushButton:hover { background:#355366; } QPushButton:disabled { color:#617483; background:#1b2a37; }
QPushButton#run { background:#218e80; border:0; color:white; font-weight:700; padding:11px; }
QComboBox,QDoubleSpinBox,QTextEdit,QTableWidget { background:#172532; border:1px solid #324959; border-radius:5px; padding:5px; }
QHeaderView::section { background:#223747; border:0; padding:8px; color:#a7c0d1; }
QTableWidget { gridline-color:#293d4d; }
QLabel#title { font-size:24px; font-weight:700; color:#e8f5fa; }
QLabel#subtitle { color:#96b0c3; }
QLabel#metric { font-size:19px; font-weight:650; color:#91e0d0; }
QSplitter::handle { background:#243747; }
"""


def numeric(value,minimum=0.000001,maximum=100000,decimals=5):
    widget = QDoubleSpinBox()
    widget.setRange(minimum,maximum)
    widget.setDecimals(decimals)
    widget.setValue(value)
    return widget


class Workbench(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ceda · PCB 后布局工作台")
        self.resize(1420,900)
        self.board = None
        self.report = None
        self.loaded_config = None
        self.workspace = tempfile.TemporaryDirectory(prefix="ceda-")
        self.run_path = Path(self.workspace.name)/"run"
        self.process = None
        self.buffer = ""
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(22,18,22,16)
        top = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Ceda  /  PCB 后布局工作台")
        title.setObjectName("title")
        self.subtitle = QLabel("本地计算 · 真实铜几何 · 电源与回流联合分析")
        self.subtitle.setObjectName("subtitle")
        titles.addWidget(title); titles.addWidget(self.subtitle)
        top.addLayout(titles); top.addStretch()
        for text,callback in (("导入 PCB",self.open_board),("演示板",self.open_demo),("打开工况",self.open_config),("保存工况",self.save_config),("导出结果",self.export_results)):
            button = QPushButton(text); button.clicked.connect(callback); top.addWidget(button)
        root.addLayout(top)
        split = QSplitter()
        root.addWidget(split,1)
        side = QWidget(); side_layout = QVBoxLayout(side)
        source_box = QGroupBox("01  电源端口")
        form = QFormLayout(source_box)
        self.source_p,self.source_n = QComboBox(),QComboBox()
        self.voltage = numeric(3.3)
        form.addRow("正极焊盘",self.source_p); form.addRow("回流焊盘",self.source_n); form.addRow("电压 / V",self.voltage)
        side_layout.addWidget(source_box)
        load_box = QGroupBox("02  负载端口")
        form = QFormLayout(load_box)
        self.load_p,self.load_n = QComboBox(),QComboBox()
        self.current = numeric(0.1)
        self.minimum = numeric(3.0,minimum=0)
        form.addRow("VDD 焊盘",self.load_p); form.addRow("本地 GND",self.load_n)
        form.addRow("电流 / A",self.current); form.addRow("最低电压 / V",self.minimum)
        add = QPushButton("添加到负载列表"); add.clicked.connect(self.add_load); form.addRow(add)
        side_layout.addWidget(load_box)
        self.loads = QTableWidget(0,4)
        self.loads.setHorizontalHeaderLabels(["VDD","GND","A","最低 V"])
        self.loads.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.loads.verticalHeader().setVisible(False)
        self.loads.setMaximumHeight(150)
        side_layout.addWidget(self.loads)
        remove = QPushButton("删除选中负载"); remove.clicked.connect(lambda:self.loads.removeRow(self.loads.currentRow()))
        side_layout.addWidget(remove)
        solver_box = QGroupBox("03  几何与计算")
        form = QFormLayout(solver_box)
        self.mesh_size = numeric(0.5,minimum=0.02,maximum=5,decimals=3)
        self.copper = numeric(0,minimum=0,maximum=1,decimals=4)
        self.plating = numeric(0,minimum=0,maximum=0.2,decimals=4)
        self.ambient = numeric(25,minimum=-50,maximum=150,decimals=1)
        self.refine = QCheckBox("复核细化网格（推荐）"); self.refine.setChecked(True)
        form.addRow("网格尺度 / mm",self.mesh_size); form.addRow("铜厚 / mm¹",self.copper)
        form.addRow("孔镀层 / mm²",self.plating); form.addRow("环境 / °C",self.ambient); form.addRow(self.refine)
        note = QLabel("¹ 0 使用文件叠层；² 有镀铜孔时必填。\n热场等扩展参数可在工况 JSON 中配置。")
        note.setWordWrap(True); form.addRow(note)
        side_layout.addWidget(solver_box)
        self.run_button = QPushButton("开始供电分析"); self.run_button.setObjectName("run"); self.run_button.clicked.connect(self.run)
        self.cancel_button = QPushButton("取消计算"); self.cancel_button.setEnabled(False); self.cancel_button.clicked.connect(self.cancel)
        side_layout.addWidget(self.run_button); side_layout.addWidget(self.cancel_button); side_layout.addStretch()
        split.addWidget(side)
        middle = QWidget(); middle_layout = QVBoxLayout(middle)
        viewbar = QHBoxLayout()
        self.layer = QComboBox(); self.layer.currentTextChanged.connect(self.update_view)
        self.field = QComboBox(); self.field.addItems(["电流密度","节点电压","板温（实验性）"]); self.field.currentIndexChanged.connect(self.update_view)
        fit = QPushButton("适应视图"); fit.clicked.connect(lambda:self.view.render_board(fit=True))
        viewbar.addWidget(self.layer); viewbar.addWidget(self.field); viewbar.addStretch(); viewbar.addWidget(fit)
        middle_layout.addLayout(viewbar)
        self.view = BoardView(); self.view.pad_clicked.connect(self.select_pad)
        middle_layout.addWidget(self.view,1)
        self.legend = QLabel("几何预览 · 尚未求解"); middle_layout.addWidget(self.legend)
        self.result_table = QTableWidget(0,4); self.result_table.setHorizontalHeaderLabels(["负载","本地 VDD–GND","最低电压","判定"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.result_table.setMaximumHeight(135)
        middle_layout.addWidget(self.result_table)
        split.addWidget(middle)
        right = QWidget(); right_layout = QVBoxLayout(right)
        self.metric_label = QLabel("等待导入"); self.metric_label.setObjectName("metric"); right_layout.addWidget(self.metric_label)
        self.status = QLabel("加载保存后的 PCB 铜几何。"); self.status.setWordWrap(True); right_layout.addWidget(self.status)
        self.inspector = QTextEdit(); self.inspector.setReadOnly(True); right_layout.addWidget(self.inspector,1)
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(220); right_layout.addWidget(self.log)
        report_button = QPushButton("打开完整报告"); report_button.clicked.connect(self.open_report); right_layout.addWidget(report_button)
        right_layout.addWidget(QLabel("范围：规定工况 DC 供电\n实测校准：尚未完成\n芯片功能 / 固件：未验证"))
        split.addWidget(right)
        split.setSizes([310,800,310])
        self.setCentralWidget(central)
        self.view.render_board()

    def error(self,message):
        self.status.setText(message)
        self.log.append(message)
        QMessageBox.warning(self,"Ceda",message)

    def open_board(self):
        path,_ = QFileDialog.getOpenFileName(self,"选择 KiCad PCB","","KiCad PCB (*.kicad_pcb)")
        if path:
            self.load(path)

    def load(self,path):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.error("请等待或取消当前计算后再导入。")
            return
        try:
            self.board = load_board(path)
        except CedaError as exc:
            self.error(str(exc)); return
        self.report = None; self.loaded_config = None; self.view.report = None; self.view.selected_pad = None
        self.loads.setRowCount(0); self.result_table.setRowCount(0)
        self.layer.clear(); self.layer.addItems([l.name for l in self.board.layers])
        for combo in (self.source_p,self.source_n,self.load_p,self.load_n):
            combo.clear()
            for pad in self.board.pads:
                combo.addItem(f"{pad.id}  ·  {pad.net or '未分配'}",pad.id)
        self.subtitle.setText(f"{self.board.path.name}  ·  {len(self.board.layers)} 铜层  ·  {len(self.board.components)} 器件  ·  {len(self.board.pads)} 焊盘")
        materials = "\n".join(f"{l.name}：{l.thickness_mm if l.thickness_mm is not None else '待提供'} mm 铜厚" for l in self.board.layers)
        issues = "\n".join(f"• {i.message}" for i in self.board.issues) or "未发现导入阻断问题。"
        self.inspector.setPlainText(f"板卡概览\n\n文件：{self.board.path.name}\n器件：{len(self.board.components)}\n焊盘：{len(self.board.pads)}\n过孔：{len(self.board.vias)}\n\n叠层材料\n{materials}\n\n导入检查\n{issues}\n\n点击板上焊盘可查看网络与位置。")
        self.status.setText("预检有阻断问题，请查看右侧。" if any(i.severity == "error" for i in self.board.issues) else "几何导入完成；请确认电源、负载和材料。")
        self.metric_label.setText("几何已导入")
        self.view.render_board(self.board,fit=True); self.legend.setText(self.view.range_text)

    def open_demo(self):
        self.load(str(demo_board()))
        if self.board:
            self.apply_config(AnalysisConfig.read(demo_config()))
            self.status.setText("演示数据：3.3 V、0.5 A、0.3 mm 狭颈。属于合成算例。")

    def combo_select(self,combo,identifier):
        index = combo.findData(identifier)
        if index < 0:
            raise CedaError(f"工况焊盘 {identifier} 不在当前 PCB 中。")
        combo.setCurrentIndex(index)

    def apply_config(self,config):
        if not self.board:
            self.error("请先导入 PCB。 "); return
        if len(config.sources) != 1:
            self.error("桌面编辑器当前支持一个电源；多电源配置请使用命令行。 "); return
        try:
            for source in config.sources:
                self.combo_select(self.source_p,source.positive); self.combo_select(self.source_n,source.negative); self.voltage.setValue(source.voltage_v)
            for load in config.loads:
                self.board.pad(load.positive); self.board.pad(load.negative)
            if config.loads:
                first = config.loads[0]
                self.combo_select(self.load_p,first.positive); self.combo_select(self.load_n,first.negative)
                self.current.setValue(first.current_a); self.minimum.setValue(first.minimum_voltage_v or 0)
            self.loaded_config = config
            self.loads.setRowCount(0)
            for load in config.loads:
                self.append_load(load)
            self.mesh_size.setValue(config.settings.mesh_size_mm); self.copper.setValue(config.settings.copper_thickness_mm or 0)
            self.plating.setValue(config.settings.via_plating_mm or 0); self.ambient.setValue(config.settings.ambient_c)
            self.refine.setChecked(config.settings.mesh_refinement)
        except CedaError as exc:
            self.error(str(exc))

    def open_config(self):
        path,_ = QFileDialog.getOpenFileName(self,"打开工况","","Ceda 工况 (*.json)")
        if path:
            try:
                self.apply_config(AnalysisConfig.read(path))
            except CedaError as exc:
                self.error(str(exc))

    def append_load(self,load):
        row = self.loads.rowCount(); self.loads.insertRow(row)
        for col,value in enumerate((load.positive,load.negative,load.current_a,load.minimum_voltage_v if load.minimum_voltage_v is not None else "")):
            self.loads.setItem(row,col,QTableWidgetItem(str(value)))

    def add_load(self):
        if self.board:
            self.append_load(Load(self.load_p.currentData(),self.load_n.currentData(),self.current.value(),self.minimum.value() or None))

    def config(self):
        if not self.board:
            raise CedaError("请先导入 PCB。")
        from dataclasses import replace
        settings = replace(self.loaded_config.settings) if self.loaded_config else Settings()
        settings.mesh_size_mm = self.mesh_size.value(); settings.copper_thickness_mm = self.copper.value() or None
        settings.via_plating_mm = self.plating.value() or None; settings.ambient_c = self.ambient.value(); settings.mesh_refinement = self.refine.isChecked()
        loads = []
        for row in range(self.loads.rowCount()):
            fields = [self.loads.item(row,col).text() if self.loads.item(row,col) else "" for col in range(4)]
            loads.append(Load(fields[0],fields[1],float(fields[2]),float(fields[3]) if fields[3] else None))
        config = AnalysisConfig([Source(self.source_p.currentData(),self.source_n.currentData(),self.voltage.value())],loads,settings,
                                self.loaded_config.name if self.loaded_config else self.board.path.stem)
        config.validate()
        return config

    def save_config(self):
        try:
            config = self.config()
            path,_ = QFileDialog.getSaveFileName(self,"保存工况","scenario.json","JSON (*.json)")
            if path:
                Path(path).write_text(json.dumps(config.to_dict(),ensure_ascii=False,indent=2),encoding="utf-8")
        except (CedaError,ValueError,OSError) as exc:
            self.error(str(exc))

    def run(self):
        try:
            config = self.config()
            blockers = [i.message for i in self.board.issues if i.severity == "error"]
            if blockers:
                raise CedaError("；".join(blockers))
        except (CedaError,ValueError) as exc:
            self.error(str(exc)); return
        self.report = None; self.view.report = None; self.result_table.setRowCount(0)
        self.view.render_board(); self.metric_label.setText("计算中")
        if self.run_path.exists():
            shutil.rmtree(self.run_path)
        config_path = Path(self.workspace.name)/"config.json"
        config_path.write_text(json.dumps(config.to_dict(),ensure_ascii=False),encoding="utf-8")
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_progress)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        args = ["worker",str(self.board.path),"--config",str(config_path),"--output",str(self.run_path)]
        if getattr(sys,"frozen",False):
            self.process.start(sys.executable,args)
        else:
            self.process.start(sys.executable,["-m","ceda",*args])
        self.run_button.setEnabled(False); self.cancel_button.setEnabled(True)
        self.log.clear(); self.buffer = ""; self.status.setText("独立进程正在分析；可取消。")

    def read_progress(self):
        self.buffer += bytes(self.process.readAllStandardOutput()).decode("utf-8",errors="replace")
        while "\n" in self.buffer:
            line,self.buffer = self.buffer.split("\n",1)
            try:
                event = json.loads(line)
                message = event.get("message",event.get("event",line))
            except ValueError:
                message = line
            self.log.append(str(message)); self.status.setText(str(message))

    def process_error(self,error):
        self.run_button.setEnabled(True); self.cancel_button.setEnabled(False)
        self.status.setText("计算进程启动失败或异常退出。")

    def finished(self,code,status):
        self.read_progress()
        self.run_button.setEnabled(True); self.cancel_button.setEnabled(False)
        if code != 0:
            self.metric_label.setText("未完成")
            self.status.setText("计算失败或已取消；未产生通过结论。请查看日志。")
            return
        try:
            self.report = json.loads((self.run_path/"result.json").read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            self.error(str(exc)); return
        self.metric_label.setText({"fail":"供电低于设定值","pass_scoped":"当前 DC 工况通过","unverified":"数值结果待核"}[self.report["verdict"]])
        diag = self.report["diagnostics"]
        self.status.setText(f"{diag['nodes']:,} 节点 · {diag['copper_loss_w']*1000:.3f} mW 铜损\n网格复核：{self.report['mesh_refinement']['status']}\n未包含芯片功能与实测校准。")
        self.result_table.setRowCount(len(self.report["loads"]))
        for row,load in enumerate(self.report["loads"]):
            for col,value in enumerate((load["positive"],f"{load['voltage_v']:.6f} V",load["minimum_voltage_v"],load["verdict"])):
                self.result_table.setItem(row,col,QTableWidgetItem(str(value)))
        quality = self.report["mesh_refinement"]
        unverified = "\n".join(f"• {item}" for item in self.report["unverified"])
        self.inspector.setPlainText(f"数值质量\n\n网格节点：{diag['nodes']:,}\n三角形：{diag['triangles']:,}\n电流残差：{diag['max_residual_a']:.3g} A\n功率不平衡：{diag['power_balance_relative']:.3%}\n网格细化：{quality['status']}\n\n{unverified}\n\n完整模型假设与复现记录见报告。")
        self.view.render_board(report=self.report); self.legend.setText(self.view.range_text)

    def cancel(self):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def update_view(self,*args):
        if hasattr(self,"view"):
            self.view.layer = self.layer.currentText()
            self.view.field = ["current","voltage","temperature"][self.field.currentIndex()]
            if self.view.field == "temperature" and self.report and not self.report.get("thermal"):
                self.status.setText("此工况未运行热分析。请在工况 JSON 中明确热边界后启用。")
                self.view.field = "current"
            self.view.render_board(); self.legend.setText(self.view.range_text)

    def select_pad(self,identifier):
        pad = self.board.pad(identifier)
        self.inspector.setPlainText(f"焊盘：{pad.id}\n网络：{pad.net}\n层：{', '.join(pad.layers)}\n位置：{pad.x:.4f}, {pad.y:.4f} mm\n铜面积：{pad.geometry.area:.5f} mm²")
        self.combo_select(self.load_p,identifier)

    def export_results(self):
        if not self.report:
            self.error("请先完成一次分析。 "); return
        parent = QFileDialog.getExistingDirectory(self,"选择结果保存目录")
        if not parent:
            return
        from datetime import datetime
        destination = Path(parent)/f"Ceda-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        try:
            shutil.copytree(self.run_path,destination)
            self.status.setText(f"已保存：{destination}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(destination/"report.html")))
        except OSError as exc:
            self.error(str(exc))

    def open_report(self):
        if self.report:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.run_path/"report.html")))

    def closeEvent(self,event):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill(); self.process.waitForFinished(3000)
        self.workspace.cleanup()
        super().closeEvent(event)


def launch(demo=False,screenshot=None):
    app = QApplication.instance() or QApplication(["Ceda"])
    app.setApplicationName("Ceda"); app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    window = Workbench(); window.show()
    if demo:
        window.open_demo()
    if screenshot:
        if demo:
            QTimer.singleShot(100,window.run)
        attempts = [0]
        def capture():
            attempts[0] += 1
            if demo and window.report is None and attempts[0] < 300:
                QTimer.singleShot(100,capture)
                return
            try:
                if not window.grab().save(screenshot):
                    raise CedaError("截图保存失败。")
            finally:
                window.close()
                app.quit()
        QTimer.singleShot(1000,capture)
    return app.exec()
