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

from .theme import STYLE
from .layout import build_workbench


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
        build_workbench(self)

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
        self.view3d.stop_workers();self.view3d.board=None;self.view3d.scene_data=None;self.view3d.image=None
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
        self.metric_label.setProperty("verdict","")
        self.breadcrumb.setText(f"项目  ／  {self.board.path.stem}  ›  供电分析")
        self.project_button.setText(self.board.path.stem)
        self.field.setCurrentIndex(2)
        self.view.render_board(self.board,fit=True); self.legend.setText(self.view.range_text)
        if self.dimension.currentIndex()==1:self.view3d.set_board(self.board)

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
        self.metric_label.setProperty("verdict",self.report["verdict"])
        self.metric_label.style().unpolish(self.metric_label)
        self.metric_label.style().polish(self.metric_label)
        diag = self.report["diagnostics"]
        self.status.setText(f"计算完成 · {diag['nodes']:,} 节点 · {diag['copper_loss_w']*1000:.3f} mW 铜损 · 网格复核：{self.report['mesh_refinement']['status']}")
        self.result_table.setRowCount(len(self.report["loads"]))
        for row,load in enumerate(self.report["loads"]):
            for col,value in enumerate((load["positive"],f"{load['voltage_v']:.6f} V",load["minimum_voltage_v"],load["verdict"])):
                display={"fail":"低于设定值","pass":"当前工况通过","unverified":"待验证"}.get(str(value),str(value)) if col==3 else str(value)
                self.result_table.setItem(row,col,QTableWidgetItem(display))
        quality = self.report["mesh_refinement"]
        unverified = "\n".join(f"• {item}" for item in self.report["unverified"])
        self.inspector.setPlainText(f"数值质量\n\n网格节点：{diag['nodes']:,}\n三角形：{diag['triangles']:,}\n电流残差：{diag['max_residual_a']:.3g} A\n功率不平衡：{diag['power_balance_relative']:.3%}\n网格细化：{quality['status']}\n\n{unverified}\n\n完整模型假设与复现记录见报告。")
        if self.dimension.currentIndex()==0:self.field.setCurrentIndex(0)
        self.view.render_board(report=self.report)
        if self.dimension.currentIndex()==0:self.legend.setText(self.view.range_text)

    def cancel(self):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def update_view(self,*args):
        if hasattr(self,"view"):
            self.view.layer = self.layer.currentText()
            self.view.field = ["current","voltage","geometry","temperature"][self.field.currentIndex()]
            if self.view.field == "temperature" and self.report and not self.report.get("thermal"):
                self.status.setText("此工况未运行热分析。请在工况 JSON 中明确热边界后启用。")
                self.view.field = "current"
            self.view.render_board(); self.legend.setText(self.view.range_text)

    def update_dimension(self,index):
        if not hasattr(self,'views'):return
        self.views.setCurrentIndex(index)
        self.field.setEnabled(index==0);self.layer.setEnabled(index==0)
        if index==1:
            self.cursor.setText('拖动旋转 · Shift 拖动平移 · 滚轮缩放')
            if self.board and self.view3d.board is not self.board:self.view3d.set_board(self.board)
            self.legend.setText('三维实体检查 · 未叠加电磁场或温度结果')
        else:
            self.cursor.setText('点击焊盘 · 滚轮缩放');self.legend.setText(self.view.range_text)

    def fit_view(self):
        if self.dimension.currentIndex():self.view3d.fit()
        else:self.view.render_board(fit=True)

    def toggle_layer(self,layer,enabled):
        if not hasattr(self,'view'):return
        if enabled:self.view.visible_layers.add(layer)
        else:self.view.visible_layers.discard(layer)
        self.view.render_board()

    def toggle_display(self,attribute,enabled):
        if hasattr(self,'view'):setattr(self.view,attribute,enabled);self.view.render_board()

    def toggle_3d(self,category,enabled):
        if enabled:self.view3d.enabled_categories.add(category)
        else:self.view3d.enabled_categories.discard(category)
        self.view3d.schedule()

    def set_pose(self,pose):
        self.dimension.setCurrentIndex(1);self.view3d.pose(pose)

    def choose_models(self):
        path=QFileDialog.getExistingDirectory(self,'选择 KiCad 3D 模型库根目录（包含 .3dshapes 文件夹）')
        if path:self.view3d.set_library(path)

    def model_status(self,message):
        blocked=self.board and any(i.severity=='error' for i in self.board.issues)
        self.status.setText(message+(' · 导入预检仍有阻断项' if blocked else ''))
        if self.view3d.scene_data:
            details='\n'.join(self.view3d.scene_data.warnings)
            self.inspector.setPlainText(f'{message}\n\n{details}\n\n缺失模型不会生成替代实体。阻焊颜色未指定时使用绿色显示预设；文字使用系统字体。')

    def show_model_details(self):
        scene=self.view3d.scene_data
        message=QMessageBox(self);message.setWindowTitle('模型与呈现诊断')
        message.setText(self.view3d.note if scene else '先切换三维实体，读取当前 PCB 的模型关联。')
        if scene:
            message.setDetailedText('\n'.join(scene.warnings) or '当前没有模型读取提示；这不代表已完成机械或实物验证。')
            message.setInformativeText('模型缺失会保留为空。显示外观预设、字体及未实现的几何特征见呈现说明。')
        message.exec()

    def select_pad(self,identifier):
        matches=[p for p in self.board.pads if p.id==identifier]
        if len(matches)!=1:
            self.inspector.setPlainText(f'{identifier} 对应 {len(matches)} 个同号焊盘几何。\n\n可查看并高亮这些铜对象；当前求解端口要求唯一焊盘，不能自动选择其中一个。')
            return
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
        self.view3d.stop_workers()
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill(); self.process.waitForFinished(3000)
        self.workspace.cleanup()
        super().closeEvent(event)


def launch(demo=False,screenshot=None,board_path=None,view='2d',model_library=None):
    # Keep diagnostics available in a windowed packaged app (which has no terminal).
    if getattr(sys,'frozen',False):
        diagnostic=Path(tempfile.gettempdir())/'ceda-desktop.log'
        stream=diagnostic.open('a',encoding='utf-8',buffering=1)
        if sys.stderr is None:sys.stderr=stream
        if sys.stdout is None:sys.stdout=stream
    app = QApplication.instance() or QApplication(["Ceda"])
    app.setApplicationName("Ceda"); app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    window = Workbench(); window.show()
    if demo:
        window.open_demo()
    elif board_path:window.load(board_path)
    if model_library:window.view3d.library_root=Path(model_library).resolve()
    if view=='3d':window.dimension.setCurrentIndex(1)
    if screenshot:
        if demo:
            QTimer.singleShot(100,window.run)
        attempts = [0]
        def capture():
            attempts[0] += 1
            if demo and window.report is None and attempts[0] < 300:
                QTimer.singleShot(100,capture)
                return
            if view=='3d' and attempts[0]<1800:
                viewport=window.view3d
                loading=viewport.loader and viewport.loader.isRunning()
                drawing=viewport.raster and viewport.raster.isRunning()
                if loading or drawing or viewport.pending or (not viewport.image and not viewport.gpu):
                    QTimer.singleShot(100,capture);return
            try:
                if not window.grab().save(screenshot):
                    raise CedaError("截图保存失败。")
            finally:
                window.close()
                app.quit()
        QTimer.singleShot(1000,capture)
    return app.exec()
