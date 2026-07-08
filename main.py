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

import argparse
import sys
from pathlib import Path
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QColor, QPalette, QKeySequence, QFont, QIcon
from PyQt5.QtWidgets import QApplication, QShortcut

from models import Model
from views import View
from controllers import Controller
from colors import Colors
from utils.paths import _resource_path
from utils.scale import Scale, scaled_font


def _parse_args():
    parser = argparse.ArgumentParser(
        description="ROIStudio - multispectral image ROI tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('iof_folder',   nargs='?', help='Path to the IOF data folder')
    parser.add_argument('seq_id',       nargs='?', help='Sequence ID (e.g. zcam03391)')
    parser.add_argument('obs_ix',       nargs='?', type=int, default=0,
                        help='Observation index within the sequence (default: 0)')
    parser.add_argument('instrument',   nargs='?', default='ZCAM',
                        choices=['ZCAM', 'PCAM'],
                        help='Instrument (default: ZCAM)')
    parser.add_argument('roi_file',     nargs='?', help='Optional .sel or .fits ROI file to load after the scene')
    parser.add_argument('--notes',      default=None,
                        help='Observation-level science notes shown in the toolbar')
    # strip Qt's own args before parsing so --style etc. don't confuse argparse
    args, _ = parser.parse_known_args()
    return args


def _make_app_icon():
    icon = QIcon()
    icon.addFile(_resource_path("graphics/logo/logo.png"),    QSize(500,  500))
    icon.addFile(_resource_path("graphics/logo/logo@2x.png"), QSize(1000, 1000))
    icon.addFile(_resource_path("graphics/logo/logo@3x.png"), QSize(1500, 1500))
    return icon


def _set_app_font(_factor=None):
    QApplication.instance().setFont(QFont("Segoe UI", scaled_font(9)))


if __name__ == '__main__':
    args = _parse_args()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(_make_app_icon())

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
    palette.setColor(QPalette.Disabled, QPalette.Text,       QColor(Colors.TEXT_DISABLED))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(Colors.TEXT_DISABLED))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(Colors.TEXT_DISABLED))
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

    QShortcut(QKeySequence(Qt.Key_S),           view).activated.connect(
        lambda: view.action_sync_views.trigger()
    )
    QShortcut(QKeySequence(Qt.CTRL + Qt.Key_S), view).activated.connect(
        view.export_sel_signal.emit
    )

    shortcut_v = QShortcut(QKeySequence(Qt.Key_V), view)
    shortcut_v.setContext(Qt.ApplicationShortcut)
    shortcut_v.activated.connect(lambda: view.panel_image_editing.select_tool("selection"))

    shortcut_r = QShortcut(QKeySequence(Qt.Key_R), view)
    shortcut_r.setContext(Qt.ApplicationShortcut)
    shortcut_r.activated.connect(lambda: view.panel_image_editing.select_tool("rectangle"))

    shortcut_f = QShortcut(QKeySequence(Qt.Key_F), view)
    shortcut_f.setContext(Qt.ApplicationShortcut)
    shortcut_f.activated.connect(view.panel_image_editing.fit_focused_canvas)

    view.show()
    Scale.set_window(view.windowHandle())

    if args.notes:
        view.set_science_notes(args.notes)

    if args.iof_folder:
        def _auto_load():
            view.show_status_message(
                f"Opening {args.instrument} scene {args.seq_id or ''} obs {args.obs_ix} "
                f"from {args.iof_folder}"
            )
            view.start_loading()

            def _on_load_complete(_load_result):
                controller.scene_controller.load_complete.disconnect(_on_load_complete)
                view._set_mode('roi_processing')
                if args.roi_file:
                    if Path(args.roi_file).suffix.lower() == '.fits':
                        controller._load_fits(fits_path=args.roi_file)
                    else:
                        controller._load_sel(sel_path=args.roi_file)

            controller.scene_controller.load_complete.connect(_on_load_complete)
            controller.scene_controller.load_direct(
                args.iof_folder, args.seq_id, args.obs_ix, args.instrument
            )

        QTimer.singleShot(0, _auto_load)

    sys.exit(app.exec_())