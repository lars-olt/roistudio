import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


class _QtObject:
    def __init__(self, *_args, **_kwargs):
        pass


class _Signal:
    def __init__(self):
        self.calls = 0

    def emit(self, *_args):
        self.calls += 1

    def connect(self, *_args):
        pass


def _load_stretch_bar():
    qt = SimpleNamespace(
        NoFocus=0, PointingHandCursor=1, ArrowCursor=2, NoBrush=3,
        AlignLeft=4, AlignVCenter=8, AlignCenter=16, NoPen=32,
    )
    core = _module(
        'PyQt5.QtCore', Qt=qt, pyqtSignal=lambda *_args: _Signal(),
        QPoint=_QtObject, QRectF=_QtObject, QSize=_QtObject,
        QTimer=SimpleNamespace(singleShot=lambda *_args: None),
    )
    widgets = _module(
        'PyQt5.QtWidgets',
        QWidget=_QtObject, QHBoxLayout=_QtObject, QLabel=_QtObject,
        QComboBox=_QtObject, QFrame=_QtObject,
    )
    gui = _module(
        'PyQt5.QtGui', QColor=_QtObject, QPainter=_QtObject, QPen=_QtObject,
        QFont=_QtObject, QPainterPath=_QtObject,
    )

    views = _module('views')
    views.__path__ = []
    panels = _module('views.panels')
    panels.__path__ = []
    pyqt = _module('PyQt5')
    pyqt.__path__ = []
    utils = _module('utils')
    utils.__path__ = []
    stand_ins = {
        'PyQt5': pyqt,
        'PyQt5.QtCore': core,
        'PyQt5.QtWidgets': widgets,
        'PyQt5.QtGui': gui,
        'colors': _module('colors', Colors=SimpleNamespace()),
        'utils': utils,
        'utils.scale': _module(
            'utils.scale', Scale=SimpleNamespace(changed=_Signal()),
            scaled=lambda value: value, scaled_font=lambda value: value,
            bar_height=lambda: 30,
        ),
        'views': views,
        'views.panels': panels,
        'views.canvas': _module('views.canvas', CanvasContainer=_QtObject),
        'views.widgets': _module('views.widgets', BandComboBox=_QtObject),
    }

    path = Path(__file__).parents[1] / 'views' / 'panels' / 'stretch_bar.py'
    spec = importlib.util.spec_from_file_location(
        'views.panels.stretch_bar_under_test', path
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stand_ins):
        spec.loader.exec_module(module)
    return module


stretch_bar = _load_stretch_bar()


class _Control:
    def __init__(self):
        self.visible = True
        self.enabled = True

    def setVisible(self, visible):
        self.visible = visible

    def setEnabled(self, enabled):
        self.enabled = enabled

    def update(self):
        pass


class _Label(_Control):
    def __init__(self, text):
        super().__init__()
        self.text = text

    def setText(self, text):
        self.text = text


class _Combo(_Control):
    def __init__(self, items=(), current=0):
        super().__init__()
        self.items = list(items)
        self.current = current
        self.active = True

    def addItem(self, text):
        self.items.append(text)

    def addItems(self, items):
        self.items.extend(items)

    def clear(self):
        self.items.clear()
        self.current = -1

    def count(self):
        return len(self.items)

    def blockSignals(self, _blocked):
        pass

    def setCurrentIndex(self, index):
        self.current = index

    def itemText(self, index):
        return self.items[index]

    def currentText(self):
        return self.items[self.current] if self.current >= 0 else ''

    def findText(self, text):
        try:
            return self.items.index(text)
        except ValueError:
            return -1

    def setCurrentText(self, text):
        index = self.findText(text)
        if index >= 0:
            self.current = index

    def set_active(self, active):
        self.active = active


class _CheckBox(_Control):
    def __init__(self, checked=True):
        super().__init__()
        self.checked = checked

    def setChecked(self, checked):
        self.checked = checked

    def isChecked(self):
        return self.checked

    def blockSignals(self, _blocked):
        pass


def _make_bar():
    bar = stretch_bar.StretchBar.__new__(stretch_bar.StretchBar)
    bar._loaded = True
    bar._bands_available = True
    bar._mono_mode = False
    bar._named_presets = {}
    bar.combo_preset = _Combo(('None', 'Mono'))
    bands = ('R0R', 'R0G', 'R0B', 'R6')
    bar.combo_r = _Combo(bands, 0)
    bar.combo_g = _Combo(bands, 1)
    bar.combo_b = _Combo(bands, 2)
    bar._band_labels = [_Label('R:'), _Label('G:'), _Label('B:')]
    bar._sep_dcs = _Control()
    bar.chk_dcs = _CheckBox(checked=True)
    bar.changed = _Signal()
    bar.adjustSize = lambda: None
    bar._reposition = lambda: None
    return bar


class StretchBarMonoTests(unittest.TestCase):
    def test_mono_is_available_alongside_instrument_presets(self):
        bar = _make_bar()
        presets = {
            'right': {
                'RGB': {'r': 'R0R', 'g': 'R0G', 'b': 'R0B', 'dcs': False},
                'DCS': {'r': 'R6', 'g': 'R0G', 'b': 'R0B', 'dcs': True},
            }
        }

        bar.set_presets('right', presets)

        self.assertEqual(bar.combo_preset.items, ['None', 'Mono', 'RGB', 'DCS'])

    def test_mono_shows_one_filter_and_uses_it_for_every_channel(self):
        bar = _make_bar()
        bar.combo_preset.setCurrentIndex(1)

        bar._on_preset_selected(1)

        self.assertEqual(bar._band_labels[0].text, 'Filter:')
        self.assertFalse(bar._band_labels[1].visible)
        self.assertFalse(bar.combo_g.visible)
        self.assertFalse(bar._band_labels[2].visible)
        self.assertFalse(bar.combo_b.visible)
        self.assertFalse(bar.chk_dcs.visible)
        self.assertEqual(bar.get_selection(), ('R0R', 'R0R', 'R0R', False))
        self.assertEqual(bar.changed.calls, 1)

        bar.combo_r.setCurrentText('R6')
        self.assertEqual(bar.get_selection(), ('R6', 'R6', 'R6', False))

    def test_leaving_mono_restores_the_three_manual_selections(self):
        bar = _make_bar()
        bar.combo_preset.setCurrentIndex(1)
        bar._on_preset_selected(1)
        bar.combo_preset.setCurrentIndex(0)

        bar._on_preset_selected(0)

        self.assertEqual(bar._band_labels[0].text, 'R:')
        self.assertTrue(all(label.visible for label in bar._band_labels))
        self.assertTrue(bar.combo_g.visible)
        self.assertTrue(bar.combo_b.visible)
        self.assertTrue(bar.chk_dcs.visible)
        self.assertEqual(bar.get_selection(), ('R0R', 'R0G', 'R0B', False))
        self.assertEqual(bar.changed.calls, 2)

    def test_rgb_or_dcs_action_replaces_mono_mode(self):
        bar = _make_bar()
        bar.combo_preset.setCurrentIndex(1)
        bar._on_preset_selected(1)

        applied = bar.apply_preset('R6', 'R0G', 'R0B', True)

        self.assertTrue(applied)
        self.assertFalse(bar._mono_mode)
        self.assertEqual(bar.combo_preset.currentText(), 'None')
        self.assertEqual(bar.get_selection(), ('R6', 'R0G', 'R0B', True))


if __name__ == '__main__':
    unittest.main()
