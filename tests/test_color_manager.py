import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_color_manager():
    names = [
        'green', 'yellow', 'blue', 'red', 'magenta', 'cyan', 'orange',
        'azure', 'purple', 'lime', 'rust', 'green+2', 'green-1', 'green-2',
        'yellow-2', 'blue+2', 'blue-1', 'blue-2', 'red+2', 'red-1',
        'red-2', 'magenta+2', 'magenta+1', 'magenta-1', 'magenta-2',
        'magenta-3', 'cyan+2', 'cyan+1', 'cyan-1', 'cyan-2', 'cyan-3',
        'orange+2', 'orange+1', 'orange-1', 'orange-2', 'orange-3',
        'azure+2', 'azure+1',
    ]
    mappings = {name: '#336699' for name in names}
    marslab = _module('marslab')
    marslab.__path__ = []
    compat = _module('marslab.compat')
    compat.__path__ = []
    mertools = _module(
        'marslab.compat.mertools',
        MERSPECT_M20_COLOR_MAPPINGS=mappings,
    )
    converters = _module(
        'utils.converters',
        hex_to_rgb=lambda value: tuple(
            int(value[index:index + 2], 16) for index in (1, 3, 5)
        ),
    )
    path = Path(__file__).parents[1] / 'controllers' / 'color_manager.py'
    spec = importlib.util.spec_from_file_location('color_manager_under_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        'marslab': marslab,
        'marslab.compat': compat,
        'marslab.compat.mertools': mertools,
        'utils.converters': converters,
    }):
        spec.loader.exec_module(module)
    return module


color_manager_module = _load_color_manager()


# A manually reused color should only interrupt the normal color order once.
class OneShotColorSelectionTests(unittest.TestCase):
    def test_reusing_a_color_once_then_resumes_automatic_rotation(self):
        manager = color_manager_module.ColorManager('ZCAM')
        first_color, first_name = manager.next()
        _second_color, second_name = manager.next()
        expected_resume = manager.peek()

        manager.set_next(first_name)

        self.assertEqual(manager.next(), (first_color, first_name))
        self.assertEqual(manager.peek(), expected_resume)
        self.assertEqual((first_name, second_name), ('red', 'magenta'))


if __name__ == '__main__':
    unittest.main()
