import os
import time

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PySide6.QtWidgets import QApplication
from ceda.gui.app import Workbench


def test_desktop_worker_and_config_roundtrip(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Workbench()
    window.open_demo()
    config = window.config()
    assert config.sources[0].positive == "J1.1"
    assert config.loads[0].minimum_voltage_v == 3.295
    window.run()
    deadline = time.monotonic()+30
    while window.report is None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.report is not None,window.log.toPlainText()
    assert window.report["verdict"] == "fail"
    assert window.run_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    assert window.result_table.rowCount() == 1
    window.show(); app.processEvents()
    assert window.grab().save(str(tmp_path/"desktop.png"))
    window.close()


def test_three_dimensional_model_worker_and_renderer_complete():
    app = QApplication.instance() or QApplication([])
    window = Workbench();window.open_demo();window.show()
    window.dimension.setCurrentIndex(1)
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
        view=window.view3d
        if view.image and view.note.startswith('真实模型') and not view.pending and not (view.raster and view.raster.isRunning()):break
    assert window.view3d.image is not None
    assert window.view3d.note.startswith('真实模型 0/0')
    assert len(window.view3d.scene_data.warnings)==2
    assert window.report is None
    window.set_pose('bottom');app.processEvents()
    next(b for b in window.navigation.buttons() if b.text()=='供电分析').click()
    assert window.dimension.currentIndex()==0
    assert window.field.currentIndex()==0
    window.close()


def test_duplicate_pad_number_remains_inspectable():
    from dataclasses import replace
    app=QApplication.instance() or QApplication([])
    window=Workbench();window.open_demo()
    pad=window.board.pads[0]
    window.board.pads.append(replace(pad))
    window.view.selected_pad=pad.id
    window.select_pad(pad.id);window.view.render_board()
    assert '2 个同号焊盘' in window.inspector.toPlainText()
    window.close()
