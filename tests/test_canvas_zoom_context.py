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


class _RectF:
    def __init__(self, x, y, width, height):
        self._x = x
        self._y = y
        self._width = width
        self._height = height

    def adjusted(self, left, top, right, bottom):
        return _RectF(
            self._x + left,
            self._y + top,
            self._width + right - left,
            self._height + bottom - top,
        )


class _PointF:
    def __init__(self, x=0, y=0):
        self._x = x
        self._y = y

    def x(self):
        return self._x

    def y(self):
        return self._y

    def setX(self, value):
        self._x = value

    def setY(self, value):
        self._y = value


def _load_canvas_module():
    class QWidget:
        pass

    pyqt = _module("PyQt5")
    pyqt.__path__ = []
    qt_core = _module(
        "PyQt5.QtCore",
        Qt=SimpleNamespace(),
        pyqtSignal=lambda *_args: MagicMock(),
        QPointF=_PointF,
        QPoint=type("QPoint", (), {}),
        QRectF=_RectF,
        QRect=type("QRect", (), {}),
        QTimer=MagicMock,
        QEvent=type("QEvent", (), {}),
    )
    qt_widgets = _module(
        "PyQt5.QtWidgets",
        QWidget=QWidget,
        QHBoxLayout=type("QHBoxLayout", (), {}),
        QSplitter=type("QSplitter", (), {}),
    )
    qt_gui = _module(
        "PyQt5.QtGui",
        **{
            name: type(name, (), {})
            for name in (
                "QPainter", "QColor", "QKeyEvent", "QMouseEvent", "QWheelEvent",
                "QPen", "QFont", "QFontMetrics", "QPainterPath",
            )
        },
    )

    utils = _module("utils")
    utils.__path__ = []
    converters = _module(
        "utils.converters",
        move_rect_on_pixel_grid=MagicMock(),
        snap_rect=MagicMock(),
    )
    scale = _module(
        "utils.scale",
        scaled=lambda value: value,
        scaled_font=lambda value: value,
        bar_height=lambda: 24,
    )

    stand_ins = {
        "cv2": _module("cv2"),
        "numpy": _module("numpy"),
        "PyQt5": pyqt,
        "PyQt5.QtCore": qt_core,
        "PyQt5.QtWidgets": qt_widgets,
        "PyQt5.QtGui": qt_gui,
        "utils": utils,
        "utils.converters": converters,
        "utils.scale": scale,
    }
    module_path = Path(__file__).parents[1] / "views" / "canvas.py"
    spec = importlib.util.spec_from_file_location("canvas_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stand_ins):
        spec.loader.exec_module(module)
    return module


canvas_module = _load_canvas_module()
CanvasContainer = canvas_module.CanvasContainer
DualCanvasContainer = canvas_module.DualCanvasContainer


class SingleEyeCanvasMappingTests(unittest.TestCase):
    def test_absent_eye_is_filtered_without_losing_logical_index(self):
        rois = [
            {"right_rect": (1, 2, 3, 4)},
            {"right_rect": None},
            {"right_rect": (5, 6, 7, 8)},
        ]

        canvas_rois, colors, names = DualCanvasContainer._rois_for_canvas(
            rois,
            "right_rect",
            [(255, 0, 0), (0, 255, 0), (0, 0, 255)],
            ["red", "green", "blue"],
        )

        self.assertEqual(
            canvas_rois,
            [
                {"roi": (1, 2, 3, 4), "_roi_index": 0},
                {"roi": (5, 6, 7, 8), "_roi_index": 2},
            ],
        )
        self.assertEqual(colors, [(255, 0, 0), (0, 0, 255)])
        self.assertEqual(names, ["red", "blue"])

    def test_canvas_translates_filtered_index_back_to_logical_roi(self):
        context = SimpleNamespace(roi_indices=[0, 2])

        self.assertEqual(CanvasContainer._logical_roi_index(context, 1), 2)


class NavigatorGeometryTests(unittest.TestCase):
    def _canvas(self, zoom):
        return SimpleNamespace(
            canvas=SimpleNamespace(
                image=object(),
                width=lambda: 100,
                height=lambda: 80,
            ),
            zoom_level=zoom,
            width=lambda: 200,
            height=lambda: 200,
        )

    def test_navigator_is_unavailable_while_scaled_canvas_fits_panel(self):
        self.assertIsNone(CanvasContainer._navigator_geometry(self._canvas(1.0)))

    def test_navigator_is_available_when_scaled_canvas_exceeds_panel(self):
        self.assertIsNotNone(CanvasContainer._navigator_geometry(self._canvas(2.1)))


class ZoomContextVisibilityTests(unittest.TestCase):
    def test_navigator_is_not_drawn_when_zoom_context_is_disabled(self):
        context = SimpleNamespace(
            zoom_context_visible=False,
            _navigator_geometry=MagicMock(),
        )
        painter = MagicMock()

        CanvasContainer._draw_navigator(context, painter)

        context._navigator_geometry.assert_not_called()
        painter.save.assert_not_called()

    def test_visibility_setter_updates_state_and_repaints(self):
        context = SimpleNamespace(
            zoom_context_visible=True,
            update=MagicMock(),
        )

        CanvasContainer.set_zoom_context_visible(context, False)

        self.assertFalse(context.zoom_context_visible)
        context.update.assert_called_once_with()

    def test_zoom_indicator_remains_visible_when_zoom_context_is_disabled(self):
        context = SimpleNamespace(
            zoom_context_visible=False,
            zoom_level=1.0,
            _zoom_indicator_rect=MagicMock(return_value=object()),
        )
        painter = MagicMock()

        with (
            patch.object(canvas_module, "QPainter", SimpleNamespace(Antialiasing=object())),
            patch.object(canvas_module, "QFont", MagicMock(return_value=object())),
            patch.object(canvas_module, "QColor", MagicMock(return_value=object())),
            patch.object(canvas_module, "QRectF", MagicMock(return_value=object())),
            patch.object(
                canvas_module,
                "Qt",
                SimpleNamespace(NoPen=object(), AlignCenter=object()),
            ),
        ):
            CanvasContainer._draw_zoom_indicator(context, painter)

        painter.drawText.assert_called_once()
        self.assertEqual(painter.drawText.call_args.args[2], "1.00x")

    def test_hidden_navigator_does_not_reserve_space_above_zoom_indicator(self):
        context = SimpleNamespace(
            zoom_context_visible=False,
            width=lambda: 300,
            height=lambda: 200,
            _navigator_geometry=MagicMock(),
        )
        metrics = MagicMock()
        metrics.horizontalAdvance.return_value = 50
        rect_factory = MagicMock(return_value=object())

        with (
            patch.object(canvas_module, "QFont", MagicMock(return_value=object())),
            patch.object(canvas_module, "QFontMetrics", MagicMock(return_value=metrics)),
            patch.object(canvas_module, "QRect", rect_factory),
        ):
            CanvasContainer._zoom_indicator_rect(context)

        context._navigator_geometry.assert_not_called()
        rect_factory.assert_called_once_with(234, 166, 56, 24)


if __name__ == "__main__":
    unittest.main()
