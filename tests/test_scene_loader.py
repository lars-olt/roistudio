import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class SceneSourceFolderTests(unittest.TestCase):
    def test_loader_retains_absolute_source_folder_for_gui_and_cli_exports(self):
        qt_core = types.ModuleType("PyQt5.QtCore")
        qt_core.QThread = object
        qt_core.pyqtSignal = lambda *_args: Mock()
        loading = types.ModuleType("sparc.data.loading")
        loading.load_cube = Mock()
        spec = importlib.util.spec_from_file_location(
            "scene_loader_under_test",
            Path(__file__).parents[1] / "workers" / "scene_loader.py",
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            "PyQt5.QtCore": qt_core, "sparc.data.loading": loading,
        }):
            spec.loader.exec_module(module)

        for folder in (Path("Mars data") / "scene A", Path.home() / "scene B"):
            with self.subTest(folder=folder):
                left_image = object()
                result = {
                    "id": "scene", "instrument": "ZCAM", "rgb_img": object(),
                    "left_rgb_img": left_image, "right_rgb_img": object(),
                    "left_band_keys": ['L0B', 'L0G', 'L0R'], "right_band_keys": [],
                }
                loading.load_cube.return_value = result
                worker = module.SceneLoadThread(folder, "sequence", 0, "ZCAM")
                worker.run()

                expected = str(folder.absolute())
                self.assertEqual(result["source_folder"], expected)
                self.assertEqual(loading.load_cube.call_args.kwargs["iof_path"], expected)
                self.assertIs(loading.load_cube.call_args.kwargs["crop_zcam"], False)
                self.assertIs(result['rgb_img'], left_image)
                worker.load_complete.emit.assert_called_with(result)
                worker.load_error.emit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
