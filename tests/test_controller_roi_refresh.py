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


def _load_controller():
    class QObject:
        pass

    controllers = _module('controllers')
    controllers.__path__ = []
    utils = _module('utils')
    utils.__path__ = []
    roi_controller = _module(
        'controllers.roi_controller',
        on_roi_created=MagicMock(),
        on_roi_changed=MagicMock(return_value={'right_rect': (1, 2, 3, 4)}),
    )
    stand_ins = {
        'PyQt5': _module('PyQt5'),
        'PyQt5.QtCore': _module('PyQt5.QtCore', QObject=QObject),
        'yaml': _module('yaml', safe_load=MagicMock(), dump=MagicMock()),
        'controllers': controllers,
        'controllers.scene_controller': _module(
            'controllers.scene_controller', SceneController=MagicMock,
        ),
        'controllers.sparc_controller': _module(
            'controllers.sparc_controller', SparcController=MagicMock,
        ),
        'controllers.color_manager': _module(
            'controllers.color_manager', ColorManager=MagicMock,
        ),
        'controllers.scene_callbacks': _module('controllers.scene_callbacks'),
        'controllers.sparc_callbacks': _module('controllers.sparc_callbacks'),
        'controllers.roi_controller': roi_controller,
        'controllers.sel_controller': _module('controllers.sel_controller'),
        'utils': utils,
        'utils.rendering': _module('utils.rendering', render_images=MagicMock()),
        'utils.paths': _module('utils.paths', _get_config_path=MagicMock()),
        'presets': _module('presets', INSTRUMENT_PRESETS={}),
    }
    stand_ins['PyQt5'].__path__ = []

    path = Path(__file__).parents[1] / 'controllers' / 'controller.py'
    spec = importlib.util.spec_from_file_location(
        'controllers.controller_under_test', path
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stand_ins):
        spec.loader.exec_module(module)
    return module, roi_controller


controller_module, roi_controller = _load_controller()


class RoiRefreshTests(unittest.TestCase):
    def test_geometry_change_does_not_rebuild_canvas_or_metadata(self):
        controller = controller_module.Controller.__new__(
            controller_module.Controller
        )
        controller._model = SimpleNamespace(
            sparc_load_result={'instrument': 'ZCAM'}
        )
        controller._view = SimpleNamespace(show_status_message=MagicMock())
        controller._current_rois_data = [{'right_rect': (0, 0, 2, 2)}]
        controller._get_instrument_config = MagicMock(return_value={})
        controller._has_dual_cubes = MagicMock(return_value=True)
        controller.sparc_controller = MagicMock()
        controller._update_roi_view = MagicMock()

        controller._on_roi_changed(0, (1, 2, 3, 4), 'right')

        controller._update_roi_view.assert_called_once_with(
            refresh_canvas=False, refresh_metadata=False
        )
        self.assertEqual(
            controller._current_rois_data[0],
            {'right_rect': (1, 2, 3, 4)},
        )

    def test_split_color_advances_only_after_drawing_in_both_eyes(self):
        controller = controller_module.Controller.__new__(
            controller_module.Controller
        )
        controller._model = SimpleNamespace(
            sparc_load_result={'instrument': 'ZCAM'}
        )
        controller._view = SimpleNamespace(
            set_export_enabled=MagicMock(),
            show_status_message=MagicMock(),
        )
        controller._current_rois_data = []
        controller._current_colors = []
        controller._current_color_names = []
        controller._split_pair_color_name = None
        controller._split_pair_eyes = set()
        controller._get_instrument_config = MagicMock(return_value={})
        controller._has_dual_cubes = MagicMock(return_value=True)
        controller.sparc_controller = MagicMock()
        controller._update_roi_view = MagicMock()
        controller.color_manager = MagicMock()
        controller.color_manager.next.side_effect = [
            ((255, 0, 0), 'red'),
            ((255, 0, 0), 'red'),
        ]
        roi_controller.on_roi_created.side_effect = [
            {'left_rect': (1, 2, 3, 4), 'right_rect': None},
            {'left_rect': None, 'right_rect': (5, 6, 3, 4)},
        ]

        controller._on_roi_created((1, 2, 3, 4), 'left')

        self.assertEqual(controller._split_pair_color_name, 'red')
        self.assertEqual(controller._split_pair_eyes, {'left'})
        controller.color_manager.set_next.assert_called_once_with('red')

        controller._on_roi_created((5, 6, 3, 4), 'right')

        self.assertIsNone(controller._split_pair_color_name)
        self.assertEqual(controller._split_pair_eyes, set())
        # Completion consumes the second red draw without putting red back.
        controller.color_manager.set_next.assert_called_once_with('red')

    def test_choosing_another_color_finishes_a_single_eye_cycle(self):
        controller = controller_module.Controller.__new__(
            controller_module.Controller
        )
        controller._pending_recolor_index = None
        controller._split_pair_color_name = 'red'
        controller._split_pair_eyes = {'left'}
        controller.color_manager = MagicMock()
        controller._refresh_swatch = MagicMock()

        controller._on_color_selected((0, 255, 0), 'green')

        controller.color_manager.consume.assert_called_once_with('red')
        controller.color_manager.set_next.assert_called_once_with('green')
        self.assertIsNone(controller._split_pair_color_name)
        self.assertEqual(controller._split_pair_eyes, set())


if __name__ == '__main__':
    unittest.main()
