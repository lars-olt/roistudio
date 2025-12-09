def _bootstrap_torch():
    """
    Import torch early so its DLLs are loaded before other heavy libraries.

    On Windows, this avoids conflicts where later-loaded DLLs
    can cause `c10.dll` initialization to fail.
    """
    try:
        import torch  # noqa: F401
    except Exception as e:
        print("Warning: torch failed to import at startup:", repr(e))

_bootstrap_torch()

from roi_controller import Controller
from colors import Colors

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication

from roi_model import Model
from roi_view import View

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # use fusion style for modern look
    app.setStyle("Fusion")

    # apply dark theme inspired by premiere pro
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(Colors.APP_BACKGROUND))
    palette.setColor(QPalette.WindowText, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.Base, QColor(Colors.PANEL_BACKGROUND))
    palette.setColor(QPalette.AlternateBase, QColor(Colors.SUBTLE_PANEL_ACCENT))
    palette.setColor(QPalette.ToolTipBase, QColor(Colors.PANEL_BACKGROUND))
    palette.setColor(QPalette.ToolTipText, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.Text, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.Button, QColor(Colors.PANEL_ACCENT))
    palette.setColor(QPalette.ButtonText, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(Colors.ACCENT))
    palette.setColor(QPalette.Highlight, QColor(Colors.ACCENT))
    palette.setColor(QPalette.HighlightedText, Qt.white)
    app.setPalette(palette)

    model = Model()
    view = View()
    controller = Controller(model, view)

    view.show()

    sys.exit(app.exec_())