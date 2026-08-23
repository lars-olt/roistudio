import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_roi_controller():
    sparc = _module("sparc")
    sparc.__path__ = []
    sparc_utils = _module("sparc.utils")
    sparc_utils.__path__ = []
    geometry = _module(
        "sparc.utils.geometry",
        right_rect_to_left_inscribed=MagicMock(side_effect=AssertionError(
            "missing opposite eye should not be re-derived while editing"
        )),
    )
    converters = _module(
        "utils.converters",
        snap_rect=lambda x, y, w, h, bounds=None: (x, y, w, h),
    )
    cv2 = _module("cv2", perspectiveTransform=MagicMock())
    stand_ins = {
        "cv2": cv2,
        "sparc": sparc,
        "sparc.utils": sparc_utils,
        "sparc.utils.geometry": geometry,
        "utils.converters": converters,
    }
    path = Path(__file__).parents[1] / "controllers" / "roi_controller.py"
    spec = importlib.util.spec_from_file_location("roi_controller_under_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stand_ins):
        spec.loader.exec_module(module)
    return module


def _load_sparc_controller():
    class QObject:
        pass

    qt_core = _module(
        "PyQt5.QtCore",
        QObject=QObject,
        pyqtSignal=lambda *_args, **_kwargs: MagicMock(),
    )
    pyqt = _module("PyQt5")
    pyqt.__path__ = []
    workers = _module("workers")
    workers.__path__ = []
    runner = _module("workers.sparc_runner", SparcRunThread=MagicMock)
    path = Path(__file__).parents[1] / "controllers" / "sparc_controller.py"
    spec = importlib.util.spec_from_file_location("sparc_controller_under_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        "PyQt5": pyqt,
        "PyQt5.QtCore": qt_core,
        "workers": workers,
        "workers.sparc_runner": runner,
    }):
        spec.loader.exec_module(module)
    return module


roi_controller = _load_roi_controller()
sparc_controller_module = _load_sparc_controller()


# Drawing or editing one eye should never invent a rectangle in the other eye.
class EyeLocalEditingTests(unittest.TestCase):
    def setUp(self):
        self.load_result = {
            "instrument": "ZCAM",
            "rgb_img": np.zeros((30, 40, 3), dtype=np.uint8),
            "homography_matrix": None,
        }
        self.spectra = MagicMock()
        self.spectra.update_roi_spectrum_dual.return_value = {"spectrum": [1.0]}
        self.roi = {
            "roi": (10, 11, 4, 5),
            "left_rect": (1, 2, 4, 5),
            "right_rect": (10, 11, 4, 5),
        }

    def test_single_screen_creation_builds_a_pair(self):
        created = roi_controller.on_roi_created(
            (10, 11, 4, 5), "single", self.load_result, {}, self.spectra, True
        )
        self.assertEqual(created["left_rect"], (10, 11, 4, 5))
        self.assertEqual(created["right_rect"], (10, 11, 4, 5))
        self.assertEqual(created["roi"], (10, 11, 4, 5))

    def test_split_screen_creation_stores_only_the_active_eye(self):
        left = roi_controller.on_roi_created(
            (1, 2, 4, 5), "left", self.load_result, {}, self.spectra, True
        )
        right = roi_controller.on_roi_created(
            (10, 11, 4, 5), "right", self.load_result, {}, self.spectra, True
        )

        self.assertEqual(left["left_rect"], (1, 2, 4, 5))
        self.assertIsNone(left["right_rect"])
        self.assertIsNone(left["roi"])
        self.assertIsNone(right["left_rect"])
        self.assertEqual(right["right_rect"], (10, 11, 4, 5))
        self.assertEqual(right["roi"], (10, 11, 4, 5))

    def test_editing_single_eye_does_not_recreate_missing_eye(self):
        right_only = {**self.roi, "left_rect": None}
        self.load_result["homography_matrix"] = object()

        changed = roi_controller.on_roi_changed(
            0, (12, 13, 6, 7), "single", [right_only],
            self.load_result, {}, self.spectra, True,
        )

        self.assertIsNone(changed["left_rect"])
        self.assertEqual(changed["right_rect"], (12, 13, 6, 7))


class _Metadata:
    def __init__(self, wavelengths):
        self._wavelengths = wavelengths

    def set_index(self, _key):
        return self

    def __getitem__(self, _key):
        return self

    def to_dict(self):
        return self._wavelengths


# Spectra should use the available eye and leave the missing bands clearly empty.
class SingleEyeSpectrumTests(unittest.TestCase):
    def setUp(self):
        self.controller = sparc_controller_module.SparcController()
        left_cube = np.stack([
            np.full((2, 2), 2.0),
            np.full((2, 2), 4.0),
        ])
        right_cube = np.stack([
            np.full((2, 2), 10.0),
            np.full((2, 2), 20.0),
        ])
        self.load_result = {
            "left_cube": left_cube,
            "right_cube": right_cube,
            "left_band_keys": ["L0", "L1"],
            "right_band_keys": ["R0", "R1"],
            "merged_band_recipe": [
                ("stereo", "S", "L0", "R0"),
                ("left_only", "L", "L1", None),
                ("right_only", "R", None, "R1"),
            ],
            "bandset": SimpleNamespace(metadata=_Metadata({
                "L0": 500, "R0": 500, "L1": 600, "R1": 700,
            })),
        }

    def test_left_only_uses_left_stereo_value_and_marks_right_band_missing(self):
        (merged, _std), left, right = self.controller.compute_dual_spectrum(
            self.load_result, (0, 0, 2, 2), None
        )

        np.testing.assert_allclose(merged[:2], [2.0, 4.0])
        self.assertTrue(np.isnan(merged[2]))
        self.assertEqual(left[0], [2.0, 4.0])
        self.assertEqual(right, ([], [], []))

    def test_right_only_uses_right_stereo_value_and_marks_left_band_missing(self):
        (merged, _std), left, right = self.controller.compute_dual_spectrum(
            self.load_result, None, (0, 0, 2, 2)
        )

        self.assertEqual(merged[0], 10.0)
        self.assertTrue(np.isnan(merged[1]))
        self.assertEqual(merged[2], 20.0)
        self.assertEqual(left, ([], [], []))
        self.assertEqual(right[0], [10.0, 20.0])

    def test_same_color_rectangles_use_the_union_without_double_counting_overlap(self):
        cube = np.array([[[1.0, 2.0, 100.0],
                          [3.0, 4.0, 200.0]]])
        spectrum, std = self.controller._slice_cube(
            cube,
            [(0, 0, 2, 2), (1, 0, 1, 2)],
        )

        np.testing.assert_allclose(spectrum, [2.5])
        np.testing.assert_allclose(std, [np.std([1.0, 2.0, 3.0, 4.0])])


if __name__ == "__main__":
    unittest.main()
