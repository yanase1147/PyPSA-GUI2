import sys

# Fix pandas 3.0 ArrowStringArray / xarray incompatibility
# (PyPSA optimizer uses xarray which doesn't support Arrow-backed strings yet)
try:
    import pandas as pd
    pd.options.future.infer_string = False
except (AttributeError, TypeError):
    pass

import matplotlib
import matplotlib.font_manager as _fm

# Set a Japanese-compatible font for matplotlib charts
_jp_fonts = ["Yu Gothic", "Yu Gothic UI", "Meiryo", "Meiryo UI",
             "MS Gothic", "MS UI Gothic", "IPAGothic", "Noto Sans CJK JP"]
_available = {f.name for f in _fm.fontManager.ttflist}
for _f in _jp_fonts:
    if _f in _available:
        matplotlib.rcParams["font.family"] = _f
        break

from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtGui import QFont, QFontDatabase, QPixmap, QColor, QPainter
from PyQt6.QtCore import Qt, QRect
from src.main_window import MainWindow
from src.i18n import load_language, load_saved_language


_MSG_FLAGS = Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
_MSG_COLOR = QColor("#ffffff")


def _make_splash_pixmap(w: int = 480, h: int = 240) -> QPixmap:
    pix = QPixmap(w, h)
    pix.fill(QColor("#1b3a5c"))
    p = QPainter(pix)
    # Title
    f = QFont()
    f.setPointSize(22)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#ffffff"))
    p.drawText(QRect(0, 45, w, 60), Qt.AlignmentFlag.AlignCenter, "PyPSA GUI")
    # Subtitle
    f2 = QFont()
    f2.setPointSize(9)
    p.setFont(f2)
    p.setPen(QColor("#99bbdd"))
    p.drawText(QRect(0, 110, w, 30), Qt.AlignmentFlag.AlignCenter,
               "v0.1.0  \u00a9 2026 Takashi YANASE")
    p.end()
    return pix


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PyPSA GUI")
    app.setStyle("Fusion")

    # Load saved language BEFORE creating any windows
    load_language(load_saved_language())

    # Set a Japanese-compatible font on Windows
    for font_name in ["Yu Gothic UI", "Meiryo UI", "Meiryo", "MS UI Gothic", "Segoe UI"]:
        if font_name in QFontDatabase.families():
            app.setFont(QFont(font_name, 9))
            break

    splash = QSplashScreen(_make_splash_pixmap())
    splash.show()
    app.processEvents()

    splash.showMessage("初期化中...", _MSG_FLAGS, _MSG_COLOR)
    app.processEvents()

    splash.showMessage("UI を構築中...", _MSG_FLAGS, _MSG_COLOR)
    app.processEvents()
    window = MainWindow()

    splash.showMessage("project.xlsx を読み込み中...", _MSG_FLAGS, _MSG_COLOR)
    app.processEvents()
    window._load_default_project()

    splash.showMessage("完了", _MSG_FLAGS, _MSG_COLOR)
    app.processEvents()

    window.show()
    splash.finish(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
