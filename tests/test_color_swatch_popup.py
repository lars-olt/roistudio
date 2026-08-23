import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_widgets():
    class Widget:
        def mousePressEvent(self, _event):
            pass

        def mouseReleaseEvent(self, _event):
            pass

    class Timer:
        callbacks = []

        @classmethod
        def singleShot(cls, _delay, callback):
            cls.callbacks.append(callback)

    qt = SimpleNamespace(LeftButton=1, Popup=2)
    core = _module(
        'PyQt5.QtCore', Qt=qt,
        pyqtSignal=lambda *_args: MagicMock(),
        QPoint=object, QSize=object, QMimeData=object, QRectF=object,
        QTimer=Timer,
    )
    widgets = _module(
        'PyQt5.QtWidgets',
        **{name: Widget for name in (
            'QLabel', 'QPushButton', 'QComboBox', 'QWidget', 'QVBoxLayout',
            'QGridLayout', 'QFrame', 'QToolButton', 'QSizePolicy', 'QListView',
        )},
    )
    gui = _module(
        'PyQt5.QtGui',
        **{name: type(name, (), {}) for name in (
            'QIcon', 'QMovie', 'QPainter', 'QPainterPath', 'QPen', 'QPixmap',
            'QColor', 'QDrag',
        )},
    )
    pyqt = _module('PyQt5')
    pyqt.__path__ = []
    utils = _module('utils')
    utils.__path__ = []
    scale = _module(
        'utils.scale',
        Scale=SimpleNamespace(changed=MagicMock()),
        capped_scaled=lambda value, maximum: min(value, maximum),
        physical=lambda value: value,
        scaled=lambda value: value,
        scaled_font=lambda value: value,
    )
    stand_ins = {
        'PyQt5': pyqt,
        'PyQt5.QtCore': core,
        'PyQt5.QtWidgets': widgets,
        'PyQt5.QtGui': gui,
        'utils': utils,
        'utils.paths': _module('utils.paths', _resource_path=lambda path: path),
        'utils.scale': scale,
    }
    path = Path(__file__).parents[1] / 'views' / 'widgets.py'
    spec = importlib.util.spec_from_file_location('widgets_under_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stand_ins):
        spec.loader.exec_module(module)
    return module, Timer


widgets_module, Timer = _load_widgets()


class SwatchPopupClickTests(unittest.TestCase):
    def setUp(self):
        Timer.callbacks.clear()

    def test_toolbar_button_growth_is_capped(self):
        with patch.object(
            widgets_module, 'capped_scaled',
            side_effect=lambda value, maximum: min(value * 10, maximum),
        ):
            self.assertEqual(widgets_module.toolbar_button_size(), (56, 46))

    def test_toolbar_button_default_base_is_compact(self):
        self.assertEqual(widgets_module.toolbar_button_size(), (34, 28))

    def test_swatch_consumes_press_and_emits_only_after_release(self):
        swatch = widgets_module.ColorSwatchButton.__new__(
            widgets_module.ColorSwatchButton
        )
        swatch._pressed = False
        swatch._color = (255, 0, 0)
        swatch._name = 'red'
        swatch.clicked = SimpleNamespace(emit=MagicMock())
        swatch.rect = lambda: SimpleNamespace(contains=lambda _pos: True)
        event = SimpleNamespace(
            button=lambda: widgets_module.Qt.LeftButton,
            pos=lambda: object(),
            accept=MagicMock(),
        )

        swatch.mousePressEvent(event)
        swatch.clicked.emit.assert_not_called()
        swatch.mouseReleaseEvent(event)

        self.assertEqual(event.accept.call_count, 2)
        swatch.clicked.emit.assert_called_once_with((255, 0, 0), 'red')

    def test_palette_closes_after_the_release_event_turn(self):
        grid = widgets_module.ColorSwatchGrid.__new__(
            widgets_module.ColorSwatchGrid
        )
        grid.color_selected = SimpleNamespace(emit=MagicMock())
        grid.hide = MagicMock()

        grid._on_swatch_clicked((255, 0, 0), 'red')

        grid.color_selected.emit.assert_not_called()
        grid.hide.assert_not_called()
        self.assertEqual(len(Timer.callbacks), 1)

        Timer.callbacks.pop()()
        grid.color_selected.emit.assert_called_once_with((255, 0, 0), 'red')
        grid.hide.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
