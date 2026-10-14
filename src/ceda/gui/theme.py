"""Style A: white canvas, quiet navigation, restrained flat controls."""
from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer

STYLE = """
QWidget { background:#ffffff; color:#292d34; font-family:'.AppleSystemUIFont','Segoe UI','PingFang SC',sans-serif; font-size:12px; }
QMainWindow { background:#ffffff; }
QWidget#sidebar { background:#f9f9f9; border-right:1px solid #e8eaed; }
QWidget#sidebar QLabel { background:transparent; }
QLabel#brand { font-size:20px; font-weight:650; color:#272b31; }
QLabel#brandVersion { color:#999fa8; font-size:10px; }
QLabel#sectionLabel { color:#969da7; font-size:10px; }
QPushButton { background:#ffffff; border:1px solid #e4e7eb; border-radius:6px; padding:7px 11px; color:#444d59; }
QPushButton:hover { background:#f5f6f8; }
QPushButton:pressed { background:#edf0f3; }
QPushButton:disabled { color:#b1b6bf; border-color:#edf0f3; }
QPushButton#nav { background:transparent; border:0; text-align:left; padding:10px 12px; color:#79818c; border-radius:6px; }
QPushButton#nav:checked { background:#eceef1; color:#2b3038; font-weight:550; }
QPushButton#nav:hover { background:#f0f1f3; }
QPushButton#quiet { border:0; color:#77818e; background:transparent; }
QPushButton#run,QPushButton#export { background:#252a31; color:#ffffff; border:1px solid #252a31; font-weight:550; }
QPushButton#run:hover,QPushButton#export:hover { background:#3c424b; }
QPushButton#run:disabled { background:#aeb4bd; border-color:#aeb4bd; }
QLabel#breadcrumb { color:#828a96; font-size:11px; }
QWidget#topbar { border-bottom:1px solid #e9ebef; }
QLabel#title { font-size:24px; font-weight:600; color:#272d35; }
QLabel#subtitle { color:#8d95a1; font-size:11px; }
QLabel#metric { color:#8a929d; font-size:11px; }
QLabel#metric[verdict="fail"] { color:#aa6a35; }
QLabel#metric[verdict="pass_scoped"] { color:#527b64; }
QFrame#canvas { border:1px solid #edf0f3; border-radius:5px; background:#ffffff; }
QGraphicsView { border:0; background:#ffffff; }
QWidget#inspectorPanel { border-left:1px solid #e9ebef; }
QLabel#inspectorTitle { font-size:12px; font-weight:600; color:#39424e; }
QLabel#muted,QLabel#legend { color:#969eaa; font-size:10px; }
QLabel#sectionTitle { font-size:11px; font-weight:550; color:#697584; }
QFrame#divider { color:#e9ecf0; background:#e9ecf0; max-height:1px; border:0; }
QGroupBox { border:0; border-top:1px solid #edf0f3; margin-top:19px; padding-top:16px; font-weight:500; color:#657080; }
QGroupBox::title { subcontrol-origin:margin; left:0; padding:0 0 0 0; }
QLineEdit,QComboBox,QDoubleSpinBox,QSpinBox { background:#ffffff; border:1px solid #e5e8ed; border-radius:5px; min-height:25px; padding:2px 7px; selection-background-color:#e9eef5; selection-color:#333c49; }
QComboBox::drop-down { border:0; width:18px; }
QDoubleSpinBox::up-button,QDoubleSpinBox::down-button { width:14px; border:0; }
QComboBox QAbstractItemView { border:1px solid #e3e7ec; selection-background-color:#eef1f5; selection-color:#333c49; }
QTabBar::tab { color:#9199a5; background:#ffffff; border:0; border-bottom:2px solid #ffffff; padding:11px 0; margin-right:20px; font-size:11px; }
QTabBar::tab:selected { color:#343c47; border-bottom:2px solid #333b47; font-weight:550; }
QTabBar::tab:hover { color:#566274; }
QTextEdit { background:#ffffff; border:0; border-radius:0; color:#7b8492; font-size:10px; selection-background-color:#e7edf6; }
QTableWidget { background:#ffffff; border:0; gridline-color:#eff1f4; selection-background-color:#f1f4f8; selection-color:#333b47; font-size:11px; }
QHeaderView::section { background:#ffffff; border:0; border-bottom:1px solid #e9ecf0; color:#939ba7; font-size:10px; padding:9px 6px; font-weight:400; }
QTableCornerButton::section { background:#ffffff; border:0; }
QCheckBox { color:#8390a0; font-size:10px; spacing:6px; }
QScrollArea { border:0; background:#ffffff; }
QScrollBar:vertical { background:#ffffff; width:7px; margin:0; }
QScrollBar::handle:vertical { background:#dfe4eb; border-radius:3px; min-height:25px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { background:#ffffff; height:7px; margin:0; }
QScrollBar::handle:horizontal { background:#dfe4eb; border-radius:3px; min-width:25px; }
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal { width:0; }
QStatusBar { background:#ffffff; border-top:1px solid #eceef2; color:#969eaa; font-size:10px; }
QStatusBar::item { border:0; }
QToolTip { color:#525f70; background:#ffffff; border:1px solid #e2e6ed; padding:6px; }
"""

PATHS = {
    "board":'<rect x="2.5" y="2.5" width="11" height="11" rx="2"/><path d="M5.5 5h3v3h3M5.5 8v3M8 11h3"/>',
    "wave":'<path d="M1 9h3l2-5 3 9 2-6h4"/>',
    "layers":'<path d="m8 2 6 3-6 3-6-3 6-3Z"/><path d="m2 8 6 3 6-3M2 11l6 3 6-3"/>',
    "models":'<rect x="2" y="4" width="12" height="10" rx="1.5"/><path d="M5 4V2h6v2M2 8h12"/>',
    "report":'<path d="M4 1.5h6l3 3v10H4zM10 1.5v3h3M6 8h5M6 11h5"/>',
    "plus":'<path d="M8 3v10M3 8h10"/>',
    "download":'<path d="M8 2v8m-3-3 3 3 3-3M3 11v3h10v-3"/>',
    "play":'<path d="m5 3 8 5-8 5Z"/>',
    "fit":'<path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"/>',
}


def glyph(name,color="#7d8794"):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 16 16"><g fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</g></svg>'
    pixmap=QPixmap(32,32)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter
    pixmap.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    return QIcon(pixmap)
