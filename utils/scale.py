"""
Global UI scale manager.

With AA_EnableHighDpiScaling, Qt multiplies logical pixel values by
devicePixelRatio when rendering. Two scale factors handle the two cases:

  physical(value)  - for setFixedSize / setIconSize / pixmap.scaled().
      Pre-divides by DPR so Qt's upscaling lands at the intended size.
      Responds to Ctrl+/- but not to _DEFAULT_OFFSET, so toolbar buttons
      and cursor stay at their natural size regardless of the layout default.

  scaled(value)    - for margins, spacing, border radii.
      Qt does not upscale these; applies the full layout factor only.

  scaled_font(pt)  - font sizes in pt, scaled by the full layout factor.
"""

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication


_STEP           = 0.1
_MIN_FACTOR     = 0.5
_MAX_FACTOR     = 3.0
_DEFAULT_OFFSET = -0.3  # shifts layout scale at launch; does not affect physical()


def _dpr() -> float:
    screen = QApplication.primaryScreen()
    return screen.devicePixelRatio() if screen else 1.0


class _ScaleManager(QObject):

    changed = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self._user_offset     = 0.0
        self._layout_factor   = max(_MIN_FACTOR, min(_MAX_FACTOR,
                                    round(1.0 + _DEFAULT_OFFSET, 10)))
        self._physical_factor = 1.0

    def init(self):
        """Call once after QApplication is constructed."""
        QApplication.instance().primaryScreenChanged.connect(
            lambda _: self.changed.emit(self._layout_factor)
        )
        self.changed.emit(self._layout_factor)

    def set_window(self, qwindow):
        """Reserved for future per-screen DPI tracking."""
        pass

    def _update(self):
        self._layout_factor   = max(_MIN_FACTOR, min(_MAX_FACTOR,
                                    round(1.0 + _DEFAULT_OFFSET + self._user_offset, 10)))
        self._physical_factor = max(_MIN_FACTOR, min(_MAX_FACTOR,
                                    round(1.0 + self._user_offset, 10)))
        self.changed.emit(self._layout_factor)

    @property
    def factor(self) -> float:
        return self._layout_factor

    @property
    def physical_factor(self) -> float:
        return self._physical_factor

    def step_up(self):
        self._user_offset = round(self._user_offset + _STEP, 10)
        self._update()

    def step_down(self):
        self._user_offset = round(self._user_offset - _STEP, 10)
        self._update()

    def reset(self):
        """Reset Ctrl+/- steps; preserves _DEFAULT_OFFSET."""
        self._user_offset = 0.0
        self._update()


Scale = _ScaleManager()


def physical(value: float) -> int:
    """Fixed widget dimension — pre-divided by DPR, user-step-scaled."""
    return max(1, round(value * Scale.physical_factor / _dpr()))


def scaled(value: float) -> int:
    """Logical layout value — layout-factor-scaled, no DPR division."""
    return max(1, round(value * Scale.factor))


def scaled_font(pt: float) -> int:
    """Font size in pt, layout-factor-scaled."""
    return max(1, round(pt * Scale.factor))