def _bootstrap_torch():
    """Import torch early to avoid DLL conflicts on Windows."""
    try:
        import torch
    except Exception as e:
        print(f"Warning: torch import failed: {e!r}")


def _bootstrap_pipeline():
    """Pre-import heavy pipeline modules to avoid cold-start lag on first scene scan."""
    try:
        import rapid.helpers
        import asdf.scan
        import asdf.zcam_bandset
        import asdf_settings.rapidlooks
        import marslab.imgops.imgutils
    except Exception as e:
        print(f"Warning: pipeline pre-import failed: {e!r}")


_bootstrap_torch()
_bootstrap_pipeline()

import sys
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette, QKeySequence, QFont
from PyQt5.QtWidgets import QApplication, QShortcut

from models import Model
from views import View
from controllers import Controller
from colors import Colors


def _set_app_font(_factor=None):
    from utils.scale import scaled_font
    QApplication.instance().setFont(QFont("Segoe UI", scaled_font(9)))


if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    from utils.scale import Scale
    Scale.init()

    _set_app_font()
    Scale.changed.connect(_set_app_font)

    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor(Colors.APP_BACKGROUND))
    palette.setColor(QPalette.WindowText,      QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.Base,            QColor(Colors.PANEL_BACKGROUND))
    palette.setColor(QPalette.AlternateBase,   QColor(Colors.SUBTLE_PANEL_ACCENT))
    palette.setColor(QPalette.ToolTipBase,     QColor(Colors.PANEL_BACKGROUND))
    palette.setColor(QPalette.ToolTipText,     QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.Text,            QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.Button,          QColor(Colors.PANEL_ACCENT))
    palette.setColor(QPalette.ButtonText,      QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.BrightText,      Qt.red)
    palette.setColor(QPalette.Link,            QColor(Colors.ACCENT))
    palette.setColor(QPalette.Highlight,       QColor(Colors.ACCENT))
    palette.setColor(QPalette.HighlightedText, Qt.white)
    app.setPalette(palette)

    model      = Model()
    view       = View()
    controller = Controller(model, view)

    # Ctrl/Cmd +/-/0 adjusts UI scale. Key_Equal is the unshifted + key.
    QShortcut(QKeySequence(Qt.CTRL + Qt.Key_Equal), view).activated.connect(Scale.step_up)
    QShortcut(QKeySequence(Qt.CTRL + Qt.Key_Plus),  view).activated.connect(Scale.step_up)
    QShortcut(QKeySequence(Qt.CTRL + Qt.Key_Minus), view).activated.connect(Scale.step_down)
    QShortcut(QKeySequence(Qt.CTRL + Qt.Key_0),     view).activated.connect(Scale.reset)

    view.show()
    Scale.set_window(view.windowHandle())

    sys.exit(app.exec_())