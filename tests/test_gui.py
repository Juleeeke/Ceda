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
