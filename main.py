def _bootstrap_torch():
    """Import torch early to avoid DLL conflicts on Windows."""
    try:
        import torch
    except Exception as e:
        print("Warning: torch failed to import at startup:", repr(e))

_bootstrap_torch()

import sys
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication

from models import Model
from views import View
from controllers import Controller
from colors import Colors


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    app.setStyle("Fusion")
    
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