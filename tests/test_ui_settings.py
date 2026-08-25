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


def _load_ui_settings():
    class QByteArray:
        pass

    utils = _module('utils')
    utils.__path__ = []
    scale = _module('utils.scale', Scale=SimpleNamespace(user_offset=0.0))
    qt_core = _module(
        'PyQt5.QtCore',
        QByteArray=QByteArray,
        QSettings=MagicMock(),
    )
    pyqt = _module('PyQt5')
    pyqt.__path__ = []
    stand_ins = {
        'PyQt5': pyqt,
        'PyQt5.QtCore': qt_core,
        'utils': utils,
        'utils.scale': scale,
    }
    path = Path(__file__).parents[1] / 'utils' / 'ui_settings.py'
    spec = importlib.util.spec_from_file_location(
        'utils.ui_settings_under_test', path
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stand_ins):
        spec.loader.exec_module(module)
    return module


class _Settings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        return type(value) if type is not None else value

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        pass


ui_settings = _load_ui_settings()


def _view(panel):
    return SimpleNamespace(
        mode='settings',
        panel_settings=panel,
        main_splitter=SimpleNamespace(
            restoreState=MagicMock(), saveState=MagicMock(return_value=b'main')
        ),
        left_splitter=SimpleNamespace(
            restoreState=MagicMock(), saveState=MagicMock(return_value=b'left')
        ),
        action_roi_labels=SimpleNamespace(isChecked=MagicMock(return_value=False)),
        restoreGeometry=MagicMock(),
        saveGeometry=MagicMock(return_value=b'geometry'),
        set_mode=MagicMock(),
        set_roi_labels_visible=MagicMock(),
    )


class PairedRoiPreferenceTests(unittest.TestCase):
    def _panel(self, paired=True):
        return SimpleNamespace(
            section_states=MagicMock(return_value={}),
            apply_section_states=MagicMock(),
            display_preferences=MagicMock(return_value={
                'y_min': 0.0,
                'y_max': 0.4,
                'merge_spectra': True,
                'line_width': 0.75,
            }),
            apply_display_preferences=MagicMock(),
            paired_roi_drawing_enabled=MagicMock(return_value=paired),
            set_paired_roi_drawing_enabled=MagicMock(),
        )

    def test_restore_uses_saved_single_eye_mode(self):
        settings = _Settings({
            'version': 1,
            'editing/paired_roi_drawing': False,
        })
        panel = self._panel()

        ui_settings.UISettings(settings=settings).restore_view(_view(panel))

        panel.set_paired_roi_drawing_enabled.assert_called_once_with(False)

    def test_save_persists_paired_mode(self):
        settings = _Settings()
        panel = self._panel(paired=False)

        ui_settings.UISettings(settings=settings).save(_view(panel))

        self.assertFalse(settings.values['editing/paired_roi_drawing'])


if __name__ == '__main__':
    unittest.main()
