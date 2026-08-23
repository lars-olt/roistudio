import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path

from editions import FULL, LITE


ROOT = Path(__file__).parents[1]


def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class LiteEditionTests(unittest.TestCase):
    def test_product_identity_and_capability_are_distinct(self):
        self.assertEqual(FULL.product_name, 'ROIStudio')
        self.assertTrue(FULL.algorithm_enabled)
        self.assertEqual(LITE.product_name, 'ROIStudio Lite')
        self.assertFalse(LITE.algorithm_enabled)
        self.assertNotEqual(FULL.settings_name, LITE.settings_name)

    def test_shared_controller_has_no_static_algorithm_import(self):
        imports = _imported_modules(ROOT / 'controllers' / 'controller.py')
        self.assertNotIn('controllers.algorithm_controller', imports)
        self.assertNotIn('controllers.sparc_callbacks', imports)
        self.assertNotIn('workers.sparc_runner', imports)

    def test_shared_spectrum_controller_has_no_worker_import(self):
        imports = _imported_modules(ROOT / 'controllers' / 'sparc_controller.py')
        self.assertNotIn('workers.sparc_runner', imports)

    def test_lite_entrypoint_selects_lite(self):
        source = (ROOT / 'main_lite.py').read_text(encoding='utf-8')
        self.assertIn('run(LITE)', source)

    def test_lite_uses_sparc_base_package_without_install_workarounds(self):
        workflow = (ROOT / '.github' / 'workflows' / 'build.yml').read_text(
            encoding='utf-8',
        )
        self.assertFalse((ROOT / 'sparc_imports.py').exists())
        self.assertFalse((ROOT / 'packaging' / 'lite-requirements.txt').exists())
        self.assertNotIn('uv pip install --no-deps', workflow)
        self.assertIn('sparc[algorithm] @ git+ssh', workflow)
        self.assertIn('uv pip install "sparc @ git+ssh', workflow)

    @unittest.skipUnless(
        sys.version_info[:2] == (3, 11),
        'ROIStudio runtime tests require Python 3.11',
    )
    def test_lite_import_succeeds_with_algorithm_dependencies_blocked(self):
        script = r'''
import importlib.abc
import sys

banned = {'torch', 'torchvision', 'segment_anything', 'sklearn', 'kneed', 'psutil'}

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in banned:
            raise ModuleNotFoundError(f'blocked Lite dependency: {fullname}')

sys.meta_path.insert(0, Blocker())
import main_lite
leaked = sorted(name for name in sys.modules if name.split('.')[0] in banned)
if leaked:
    raise RuntimeError(f'algorithm modules loaded by Lite: {leaked}')

from PyQt5.QtWidgets import QApplication
from controllers import Controller
from editions import LITE
from models import Model
from views import View

app = QApplication.instance() or QApplication([])
view = View(edition=LITE)
controller = Controller(Model(), view)
assert view.windowTitle() == 'ROIStudio Lite'
assert view.action_set_sam_path is None
assert view.panel_image_editing.run_button is None
assert not view.panel_settings.algorithm_enabled
assert controller.algorithm_controller is None
view.close()
'''
        result = subprocess.run(
            [sys.executable, '-c', script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        )
        self.assertEqual(
            result.returncode, 0,
            msg=f'{result.stdout}\n{result.stderr}',
        )


if __name__ == '__main__':
    unittest.main()
