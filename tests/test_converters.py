import importlib.util
from pathlib import Path
import sys
import types
import unittest


try:
    from PyQt5.QtGui import QImage, QPixmap  # noqa: F401
except ImportError:
    qt_gui = types.ModuleType("PyQt5.QtGui")
    qt_gui.QImage = type("QImage", (), {})
    qt_gui.QPixmap = type("QPixmap", (), {})
    pyqt = types.ModuleType("PyQt5")
    pyqt.QtGui = qt_gui
    sys.modules["PyQt5"] = pyqt
    sys.modules["PyQt5.QtGui"] = qt_gui

module_path = Path(__file__).parents[1] / "utils" / "converters.py"
spec = importlib.util.spec_from_file_location("converters_under_test", module_path)
converters = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converters)

move_rect_on_pixel_grid = converters.move_rect_on_pixel_grid
snap_rect = converters.snap_rect


class MoveRectOnPixelGridTests(unittest.TestCase):
    def test_move_changes_by_one_source_pixel_at_rounding_boundary(self):
        rect = (10.0, 20.0, 8.0, 6.0)

        self.assertEqual(
            move_rect_on_pixel_grid(rect, 0.49, 0.49),
            rect,
        )
        self.assertEqual(
            move_rect_on_pixel_grid(rect, 0.51, 0.51),
            (11.0, 21.0, 8.0, 6.0),
        )

    def test_release_snap_does_not_move_pixel_aligned_drag_result(self):
        moved = move_rect_on_pixel_grid((10.0, 20.0, 8.0, 6.0), 3.7, -2.6)

        self.assertEqual(snap_rect(*moved), moved)

    def test_bounds_clamp_position_without_resizing(self):
        rect = (90.0, 90.0, 10.0, 8.0)

        self.assertEqual(
            move_rect_on_pixel_grid(rect, 20.0, 20.0, bounds=(100, 100)),
            (90.0, 92.0, 10.0, 8.0),
        )

    def test_bounds_keep_origin_aligned_for_fractional_size(self):
        moved = move_rect_on_pixel_grid(
            (90.0, 90.0, 8.4, 6.4),
            20.0,
            20.0,
            bounds=(100, 100),
        )

        self.assertEqual(moved, (91.0, 93.0, 8.4, 6.4))


if __name__ == "__main__":
    unittest.main()
