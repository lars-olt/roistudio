"""Stretch bar overlay - floating band selector parented to a canvas."""

from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRectF, QSize, QTimer
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QFrame
from PyQt5.QtGui import (QColor, QPainter, QPen, QFont,
                         QPainterPath)

from colors import Colors
from utils.scale import Scale, scaled, scaled_font, bar_height
from ..canvas import CanvasContainer
from ..widgets import BandComboBox

_OVERLAY_BG = QColor(40, 40, 40, 180)
_MONO_PRESET = "Mono"


def _row_h() -> int:
    """Inner row height - bar height minus vertical padding."""
    return bar_height() - 2 * scaled(5)


class _Separator(QWidget):
    """Painted vertical line - geometric centering, no font metric dependency."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(QColor(Colors.PANEL_ACCENT), 1))
        inset = self.height() // 4
        painter.drawLine(0, inset, 0, self.height() - inset)
        painter.end()


class _CenteredCheckBox(QWidget):
    """Checkbox that paints its indicator and label on the widget's geometric center."""

    toggled = pyqtSignal(bool)

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label   = label
        self._checked = False
        self._enabled = True
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def setRowHeight(self, h: int):
        self.setFixedHeight(h)
        self.updateGeometry()
        self.update()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, value: bool):
        if value != self._checked:
            self._checked = value
            self.update()

    def setEnabled(self, value: bool):
        self._enabled = value
        self.setCursor(Qt.PointingHandCursor if value else Qt.ArrowCursor)
        self.update()

    def isEnabled(self) -> bool:
        return self._enabled

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(scaled(12) + scaled(4) + fm.horizontalAdvance(self._label) + 2,
                     self.height() or fm.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setRenderHint(QPainter.Antialiasing)

        sz      = scaled(12)
        spacing = scaled(4)

        if self._enabled:
            border = QColor(Colors.PANEL_ACCENT)
            fill   = QColor(Colors.ACCENT)
            text_c = QColor("white")
        else:
            border = QColor(Colors.DISABLED_BORDER)
            fill   = QColor(Colors.DISABLED_BORDER)
            text_c = QColor(Colors.TEXT_OVERLAY_LABEL)

        cy         = self.height() / 2
        check_rect = QRectF(0.5, cy - sz / 2 + 0.5, sz - 1, sz - 1)

        painter.setPen(QPen(border, 1))
        painter.setBrush(fill if self._checked else Qt.NoBrush)
        painter.drawRect(check_rect)

        painter.setPen(text_c)
        painter.drawText(
            QRectF(sz + spacing, 0, self.width() - sz - spacing, self.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._label,
        )
        painter.end()

    def mousePressEvent(self, event):
        if self._enabled and event.button() == Qt.LeftButton:
            self._checked = not self._checked
            self.toggled.emit(self._checked)
            self.update()


class StretchBar(QWidget):
    """
    Floating R/G/B + DCS band selector parented to a CanvasContainer.
    Positioned at the bottom center of the canvas.

    Named presets own and disable the R/G/B selections.  Mono is a special
    manual mode: it shows one filter selector and uses that band for all three
    rendered channels.
    """

    changed = pyqtSignal()

    def __init__(self, parent: CanvasContainer):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self._focused          = False
        self._loaded           = False
        self._bands_available  = True   # whether the manual band combos are usable
        self._mono_mode        = False
        self._default_r = None
        self._default_g = None
        self._default_b = None
        self._named_presets = {}  # {label: bands dict} for this camera, set via set_presets()

        self._row = QHBoxLayout()
        self.setLayout(self._row)

        self._preset_label = QLabel("Preset:")
        self._row.addWidget(self._preset_label, 0, Qt.AlignVCenter)

        self.combo_preset = QComboBox()
        self.combo_preset.setFocusPolicy(Qt.NoFocus)
        self.combo_preset.addItems(("None", _MONO_PRESET))
        self.combo_preset.setToolTip(
            "Apply a named color stretch preset, or use one filter in Mono mode."
        )
        self.combo_preset.activated.connect(self._on_preset_selected)
        self.combo_preset.showPopup = self._show_preset_popup
        self._row.addWidget(self.combo_preset, 0, Qt.AlignVCenter)

        self._sep_preset = _Separator()
        self._row.addWidget(self._sep_preset, 0, Qt.AlignVCenter)

        self.combo_r = BandComboBox()
        self.combo_g = BandComboBox()
        self.combo_b = BandComboBox()
        self._band_labels = []

        for text, combo in (("R:", self.combo_r), ("G:", self.combo_g), ("B:", self.combo_b)):
            lbl = QLabel(text)
            self._band_labels.append(lbl)
            self._row.addWidget(lbl, 0, Qt.AlignVCenter)
            self._row.addWidget(combo, 0, Qt.AlignVCenter)
            combo.currentTextChanged.connect(self.changed.emit)

        self._sep_dcs = _Separator()
        self._row.addWidget(self._sep_dcs, 0, Qt.AlignVCenter)

        self.chk_dcs = _CenteredCheckBox("DCS")
        self.chk_dcs.setToolTip("Apply decorrelation stretch to selected bands.")
        self.chk_dcs.toggled.connect(self.changed.emit)
        self._row.addWidget(self.chk_dcs, 0, Qt.AlignVCenter)

        self._apply_scale()
        Scale.changed.connect(self._apply_scale)
        self.adjustSize()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_presets(self, camera: str, presets: dict):
        """Populate the preset combo from the instrument preset dict for this camera."""
        self._named_presets = presets.get(camera, {})
        self.combo_preset.blockSignals(True)
        self.combo_preset.clear()
        self.combo_preset.addItem("None")
        self.combo_preset.addItem(_MONO_PRESET)
        for label in self._named_presets:
            if label != _MONO_PRESET:
                self.combo_preset.addItem(label)
        self.combo_preset.setCurrentIndex(0)
        self.combo_preset.blockSignals(False)
        self._set_mono_mode(False)
        self._style_band_controls(enabled=self._loaded and self._bands_available)

    def set_focused(self, focused: bool):
        if focused != self._focused:
            self._focused = focused
            self.update()

    def set_loaded(self, loaded: bool):
        self._loaded = loaded
        self._apply_scale()

    def set_bands_available(self, available: bool):
        """Enable or disable the manual band combos without touching the preset combo.

        A scene may be missing its preferred RGB bands (so manual RGB is degraded)
        yet still support presets that use other bands - the preset combo stays live.
        """
        self._bands_available = available
        self._apply_scale()

    def populate(self, band_names, r=None, g=None, b=None):
        self.combo_preset.blockSignals(True)
        if self.combo_preset.count():
            self.combo_preset.setCurrentIndex(0)
        self.combo_preset.blockSignals(False)
        self._set_mono_mode(False)

        self.chk_dcs.blockSignals(True)
        self.chk_dcs.setChecked(False)
        self.chk_dcs.blockSignals(False)

        def _pick(preferred, fallbacks, idx):
            if preferred and preferred in band_names:
                return preferred
            for c in fallbacks:
                if c in band_names:
                    return c
            return band_names[min(idx, len(band_names) - 1)] if band_names else ''

        self._default_r, self._default_g, self._default_b = (
            _pick(r, ('R0R', 'R2'), 0),
            _pick(g, ('R0G', 'R1'), 1),
            _pick(b, ('R0B', 'R1'), 2),
        )
        for combo, sel in zip((self.combo_r, self.combo_g, self.combo_b),
                              (self._default_r, self._default_g, self._default_b)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(band_names)
            combo.setCurrentText(sel)
            combo.blockSignals(False)

        self._bands_available = True
        self.set_loaded(True)

    def apply_preset(self, r: str, g: str, b: str, dcs: bool):
        # View-menu RGB/DCS actions can call this while Mono is active.  Those
        # actions explicitly replace Mono, so restore the regular controls.
        if self._mono_mode and self.combo_preset.currentText() == _MONO_PRESET:
            self.combo_preset.blockSignals(True)
            self.combo_preset.setCurrentIndex(0)
            self.combo_preset.blockSignals(False)
            self._set_mono_mode(False)

        selections = ((self.combo_r, r), (self.combo_g, g), (self.combo_b, b))
        if any(combo.findText(value) < 0 for combo, value in selections):
            return False

        for combo, val in selections:
            combo.blockSignals(True)
            combo.setCurrentText(val)
            combo.blockSignals(False)
        self.chk_dcs.blockSignals(True)
        self.chk_dcs.setChecked(dcs)
        self.chk_dcs.blockSignals(False)
        self.changed.emit()
        return True

    def get_selection(self):
        if self._mono_mode:
            band = self.combo_r.currentText()
            return band, band, band, False
        return (self.combo_r.currentText(), self.combo_g.currentText(),
                self.combo_b.currentText(), self.chk_dcs.isChecked())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_scale(self):
        self._row.setContentsMargins(scaled(6), 0, scaled(6), 0)
        self._row.setSpacing(scaled(4))
        self._row.setAlignment(Qt.AlignVCenter)

        fs    = scaled_font(9)
        font  = QFont()
        font.setPointSize(fs)
        row_h = _row_h()

        label_color = "white" if self._loaded else Colors.TEXT_OVERLAY_LABEL
        label_style = (
            f"color: {label_color}; font-size: {fs}pt; background: transparent;"
            " margin: 0px; padding: 0px; border: none;"
        )
        for lbl in (*self._band_labels, self._preset_label):
            lbl.setStyleSheet(label_style)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedHeight(row_h)

        for sep in (self._sep_preset, self._sep_dcs):
            sep.setFixedHeight(row_h)

        for combo in (self.combo_r, self.combo_g, self.combo_b):
            combo.setFixedHeight(row_h)

        self.chk_dcs.setFont(font)
        self.chk_dcs.setRowHeight(row_h)

        self._style_preset_combo(fs, row_h)
        self._style_band_controls(
            enabled=self._loaded and self._bands_available
                    and self.combo_preset.currentText() in ("None", _MONO_PRESET)
        )

        self.setFixedHeight(bar_height())
        self.setMaximumWidth(16777215)
        self.adjustSize()
        QTimer.singleShot(0, self._reposition)

    def _style_band_controls(self, enabled: bool):
        self.combo_r.set_active(enabled)
        self.combo_g.set_active(enabled and not self._mono_mode)
        self.combo_b.set_active(enabled and not self._mono_mode)
        self.chk_dcs.setEnabled(enabled and not self._mono_mode)
        self.chk_dcs.update()

    def _set_mono_mode(self, enabled: bool):
        """Collapse or restore the per-channel controls for Mono rendering."""
        self._mono_mode = enabled
        self._band_labels[0].setText("Filter:" if enabled else "R:")
        self._band_labels[0].setVisible(True)
        self.combo_r.setVisible(True)

        for label, combo in zip(self._band_labels[1:],
                                (self.combo_g, self.combo_b)):
            label.setVisible(not enabled)
            combo.setVisible(not enabled)

        self._sep_dcs.setVisible(not enabled)
        self.chk_dcs.setVisible(not enabled)
        if enabled:
            self.chk_dcs.setChecked(False)

        manual = self.combo_preset.currentText() in ("None", _MONO_PRESET)
        self._style_band_controls(
            enabled=self._loaded and self._bands_available and manual
        )
        self.adjustSize()
        QTimer.singleShot(0, self._reposition)

    def _style_preset_combo(self, fs: int, row_h: int):
        loaded = self._loaded
        bg     = Colors.DEFAULT_FEATURE if loaded else Colors.DISABLED_FEATURE
        border = Colors.PANEL_ACCENT    if loaded else Colors.DISABLED_BORDER
        color  = "white"                if loaded else Colors.TEXT_OVERLAY_LABEL
        hover  = (f"QComboBox:hover {{ border: 1px solid {Colors.ACCENT}; "
                  f"background-color: {Colors.SUBTLE_PANEL_ACCENT}; }}"
                  if loaded else "")
        self.combo_preset.setEnabled(loaded)
        self.combo_preset.setStyleSheet(f"""
            QComboBox {{
                background-color: {bg};
                color: {color};
                border: 1px solid {border};
                border-radius: {scaled(3)}px;
                padding: 0px {scaled(3)}px;
                font-size: {fs}pt;
                min-width: {scaled(50)}px;
            }}
            QComboBox:disabled {{ color: {Colors.TEXT_OVERLAY_LABEL}; }}
            {hover}
            QComboBox::drop-down {{ width: 0px; border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: white;
                border: 1px solid {Colors.ACCENT};
                border-radius: 0px;
                padding: 0px;
                outline: none;
                font-size: {fs}pt;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 1px {scaled(8)}px;
                border: none;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {Colors.ACCENT};
                color: white;
            }}
            QToolTip {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.ACCENT};
                padding: {scaled(4)}px;
                font-size: {fs}pt;
            }}
        """)
        self.combo_preset.setFixedHeight(row_h)

    def _on_preset_selected(self, index):
        label = self.combo_preset.itemText(index)
        was_mono = self._mono_mode
        if label == _MONO_PRESET:
            self._set_mono_mode(True)
            self.changed.emit()
            return

        self._set_mono_mode(False)
        if label == "None":
            self._style_band_controls(
                enabled=self._loaded and self._bands_available
            )
            if was_mono:
                self.changed.emit()
            return
        bands = self._named_presets.get(label)
        if bands is None:
            return
        if self.apply_preset(bands['r'], bands['g'], bands['b'], bands['dcs']):
            self._style_band_controls(enabled=False)
            return

        self.combo_preset.blockSignals(True)
        self.combo_preset.setCurrentIndex(0)
        self.combo_preset.blockSignals(False)
        self._style_band_controls(enabled=self._loaded and self._bands_available)
        if was_mono:
            self.changed.emit()

    def _show_preset_popup(self):
        QComboBox.showPopup(self.combo_preset)
        popup = self.combo_preset.findChild(QFrame)
        if popup is not None:
            popup.move(self.combo_preset.mapToGlobal(QPoint(0, -popup.height())))

    def _reposition(self):
        parent = self.parent()
        if parent is None:
            return
        w = self.sizeHint().width()
        self.move((parent.width() - w) // 2,
                  parent.height() - self.height() - scaled(10))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), scaled(3), scaled(3))
        painter.setClipPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(_OVERLAY_BG)
        painter.drawPath(path)

        if self._focused:
            painter.setPen(QPen(QColor(Colors.ACCENT), 1))
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        painter.end()
