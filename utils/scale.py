"""Global scaling helpers for Qt dimensions, layout values, and fonts."""

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QFont, QFontMetrics
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

    @property
    def user_offset(self) -> float:
        return self._user_offset

    def set_user_offset(self, offset: float):
        """Set the user's Ctrl+/- adjustment, clamped to the supported range."""
        minimum = _MIN_FACTOR - 1.0
        maximum = _MAX_FACTOR - 1.0
        self._user_offset = max(minimum, min(maximum, round(float(offset), 10)))
        self._update()

    def set_scale(self, factor: float):
        """Set the user-facing scale multiplier used by Ctrl+/-."""
        self.set_user_offset(float(factor) - 1.0)

    def step_up(self):
        self.set_user_offset(self._user_offset + _STEP)

    def step_down(self):
        self.set_user_offset(self._user_offset - _STEP)

    def reset(self):
        """Reset Ctrl+/- steps; preserves _DEFAULT_OFFSET."""
        self.set_user_offset(0.0)


Scale = _ScaleManager()


def physical(value: float) -> int:
    """Fixed widget dimension - pre-divided by DPR, user-step-scaled."""
    return max(1, round(value * Scale.physical_factor / _dpr()))


def scaled(value: float) -> int:
    """Logical layout value - layout-factor-scaled, no DPR division."""
    return max(1, round(value * Scale.factor))


def capped_scaled(value: float, maximum: float) -> int:
    """Logical layout value that stops growing at ``maximum`` pixels."""
    return min(scaled(value), max(1, round(maximum)))


def scaled_font(pt: float) -> int:
    """Font size in pt, layout-factor-scaled."""
    return max(1, round(pt * Scale.factor))


def bar_height() -> int:
    """Height of the stretch bar and zoom indicator - derived from the scaled font."""
    font = QFont()
    font.setPointSize(scaled_font(9))
    return QFontMetrics(font).height() + scaled(6) + 2 * scaled(5)
