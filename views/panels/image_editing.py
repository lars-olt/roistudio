from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox
from PyQt5.QtGui import QColor, QPainter, QPen, QCursor, QPixmap

from colors import Colors
from utils.paths import _resource_path
from utils.scale import Scale, physical, scaled, scaled_font
from ..canvas import CanvasContainer, DualCanvasContainer
from ..widgets import ToolbarButton, LoadingIndicator, BandComboBox

_OVERLAY_BG      = QColor(40, 40, 40, 180)
_CURSOR_NATIVE_W = 32


def _checkbox_style():
    sz = scaled(12)
    return f"""
        QCheckBox {{
            color: white; font-size: {scaled_font(9)}pt;
            background: transparent; spacing: {scaled(4)}px;
        }}
        QCheckBox::indicator {{
            width: {sz}px; height: {sz}px;
            border: 1px solid {Colors.PANEL_ACCENT};
            border-radius: 0px; background: transparent;
        }}
        QCheckBox::indicator:checked {{
            background: {Colors.ACCENT}; border: 1px solid {Colors.ACCENT};
        }}
        QCheckBox::indicator:hover {{ border: 1px solid {Colors.ACCENT}; }}
        QToolTip {{
            background-color: {Colors.PANEL_BACKGROUND};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.ACCENT};
            padding: {scaled(4)}px;
        }}
    """


class BandSelectorOverlay(QWidget):
    """
    Floating R/G/B + DCS band selector parented to a CanvasContainer.
    Sits centred at the bottom of the canvas. Draws a 1px accent border
    along the bottom edge when this canvas is focused.
    """

    changed = pyqtSignal()

    def __init__(self, parent: CanvasContainer):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self._focused = False

        self._row = QHBoxLayout()
        self.setLayout(self._row)

        self.combo_r = BandComboBox()
        self.combo_g = BandComboBox()
        self.combo_b = BandComboBox()
        self._labels = []

        for text, combo in (("R:", self.combo_r), ("G:", self.combo_g), ("B:", self.combo_b)):
            lbl = QLabel(text)
            self._labels.append(lbl)
            self._row.addWidget(lbl)
            self._row.addWidget(combo)
            combo.currentTextChanged.connect(self.changed.emit)

        self._sep = QLabel("|")
        self._row.addWidget(self._sep)

        self.chk_dcs = QCheckBox("DCS")
        self.chk_dcs.setChecked(False)
        self.chk_dcs.setToolTip("Apply decorrelation stretch to selected bands.")
        self.chk_dcs.toggled.connect(self.changed.emit)
        self._row.addWidget(self.chk_dcs)

        self._apply_scale()
        Scale.changed.connect(self._apply_scale)
        self.adjustSize()

    def set_focused(self, focused: bool):
        if focused != self._focused:
            self._focused = focused
            self.update()

    def _apply_scale(self):
        self._row.setContentsMargins(scaled(6), scaled(3), scaled(6), scaled(3))
        self._row.setSpacing(scaled(4))

        fs = scaled_font(9)
        for lbl in self._labels:
            lbl.setStyleSheet(f"color: white; font-size: {fs}pt; background: transparent;")
        self._sep.setStyleSheet(
            f"color: {Colors.PANEL_ACCENT}; font-size: {fs}pt; background: transparent;"
        )
        self.chk_dcs.setStyleSheet(_checkbox_style())
        self.adjustSize()
        self._reposition()

    def populate(self, band_names, r=None, g=None, b=None):
        def _pick(preferred, fallbacks, idx):
            if preferred and preferred in band_names:
                return preferred
            for c in fallbacks:
                if c in band_names:
                    return c
            return band_names[min(idx, len(band_names) - 1)] if band_names else ''

        defaults = (
            _pick(r, ('R0R', 'R2'), 0),
            _pick(g, ('R0G', 'R1'), 1),
            _pick(b, ('R0B', 'R1'), 2),
        )
        for combo, sel in zip((self.combo_r, self.combo_g, self.combo_b), defaults):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(band_names)
            combo.setCurrentText(sel)
            combo.blockSignals(False)

        self.adjustSize()
        self._reposition()

    def apply_preset(self, r: str, g: str, b: str, dcs: bool):
        """Apply a color scale preset, blocking signals until all three bands are set."""
        for combo, val in ((self.combo_r, r), (self.combo_g, g), (self.combo_b, b)):
            combo.blockSignals(True)
            combo.setCurrentText(val)
            combo.blockSignals(False)
        self.chk_dcs.blockSignals(True)
        self.chk_dcs.setChecked(dcs)
        self.chk_dcs.blockSignals(False)
        self.changed.emit()

    def get_selection(self):
        return (self.combo_r.currentText(), self.combo_g.currentText(),
                self.combo_b.currentText(), self.chk_dcs.isChecked())

    def _reposition(self):
        parent = self.parent()
        if parent is None:
            return
        self.adjustSize()
        self.move((parent.width() - self.width()) // 2,
                  parent.height() - self.height() - scaled(10))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), _OVERLAY_BG)
        if self._focused:
            pen = QPen(QColor(Colors.ACCENT), 1)
            painter.setPen(pen)
            y = self.height() - 1
            painter.drawLine(0, y, self.width(), y)
        painter.end()


class ImageEditingPanel(QWidget):
    """Image canvas panel with toolbar and per-camera band selector overlays."""

    run_algorithm_signal = pyqtSignal()
    scene_dropped_signal = pyqtSignal(str)
    tool_changed_signal  = pyqtSignal(str)
    rgb_bands_changed    = pyqtSignal(str, str, str, bool, str)
    roi_changed          = pyqtSignal(int, tuple, str)
    roi_deleted          = pyqtSignal(int)
    roi_created          = pyqtSignal(tuple, str)
    split_screen_toggled = pyqtSignal(bool)
    canvas_focus_changed = pyqtSignal(str)   # 'single' | 'left' | 'right'

    def __init__(self):
        super().__init__()
        self.current_tool  = 'selection'
        self._is_split     = False
        self._focused_camera = 'single'
        self._build_ui()
        self.canvas_container.installEventFilter(self)
        Scale.changed.connect(self._apply_scale)

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        # Top bar
        self.top_bar = QWidget()
        self.top_bar.setStyleSheet(f"background-color: {Colors.PANEL_ACCENT};")
        tb_layout = QHBoxLayout()
        self.top_bar.setLayout(tb_layout)

        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self.run_algorithm_signal.emit)
        tb_layout.addWidget(self.run_button)

        self.loading_indicator = LoadingIndicator()
        tb_layout.addWidget(self.loading_indicator)
        tb_layout.addStretch()
        layout.addWidget(self.top_bar)

        # Content area — side toolbar + canvas
        content  = QWidget()
        c_layout = QHBoxLayout()
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)
        content.setLayout(c_layout)

        self.toolbar = QWidget()
        self.toolbar.setStyleSheet(
            f"background-color: {Colors.PANEL_ACCENT}; "
            f"border-right: 1px solid {Colors.DEFAULT_FEATURE};"
        )
        t_layout = QVBoxLayout()
        t_layout.setAlignment(Qt.AlignHCenter)
        self.toolbar.setLayout(t_layout)

        self.btn_selection = ToolbarButton(
            _resource_path("graphics/toolbar_selection.png"),
            _resource_path("graphics/toolbar_selection_selected.png")
        )
        self.btn_selection.set_selected(True)
        self.btn_selection.clicked.connect(lambda: self.select_tool("selection"))
        t_layout.addWidget(self.btn_selection)

        self.btn_rectangle = ToolbarButton(
            _resource_path("graphics/toolbar_rectangle.png"),
            _resource_path("graphics/toolbar_rectangle_selected.png")
        )
        self.btn_rectangle.clicked.connect(lambda: self.select_tool("rectangle"))
        t_layout.addWidget(self.btn_rectangle)

        t_layout.addStretch()

        self.btn_split_screen = ToolbarButton(
            _resource_path("graphics/toolbar_single_screen.png"),
            _resource_path("graphics/toolbar_split_screen.png")
        )
        self.btn_split_screen.set_selected(False)
        self.btn_split_screen.clicked.connect(self._toggle_split_screen)
        t_layout.addWidget(self.btn_split_screen)

        c_layout.addWidget(self.toolbar)

        self.canvas_container = DualCanvasContainer()
        self.canvas_container.scene_dropped.connect(self.scene_dropped_signal.emit)
        self.canvas_container.roi_changed.connect(self.roi_changed.emit)
        self.canvas_container.roi_deleted.connect(self.roi_deleted.emit)
        self.canvas_container.roi_created.connect(self.roi_created.emit)
        c_layout.addWidget(self.canvas_container)
        layout.addWidget(content)

        # Band selector overlays — one per camera, parented to their canvas
        self._overlay_single = BandSelectorOverlay(self.canvas_container.canvas_single)
        self._overlay_right  = BandSelectorOverlay(self.canvas_container.canvas_right)
        self._overlay_left   = BandSelectorOverlay(self.canvas_container.canvas_left)

        for overlay, camera in ((self._overlay_single, 'single'),
                                (self._overlay_right,  'right'),
                                (self._overlay_left,   'left')):
            overlay.changed.connect(lambda c=camera, o=overlay: self._on_overlay_changed(o, c))

        # Wire canvas clicks to focus tracking
        self.canvas_container.canvas_single.mousePressEvent = \
            self._make_focus_handler('single', self.canvas_container.canvas_single.mousePressEvent)
        self.canvas_container.canvas_left.mousePressEvent = \
            self._make_focus_handler('left', self.canvas_container.canvas_left.mousePressEvent)
        self.canvas_container.canvas_right.mousePressEvent = \
            self._make_focus_handler('right', self.canvas_container.canvas_right.mousePressEvent)

        self._sync_overlay_visibility()
        self._sync_focus()
        self._apply_scale()
        self.update_cursor()
        QTimer.singleShot(0, self._reposition_overlays)

    def _make_focus_handler(self, camera, original_handler):
        def handler(event):
            self._set_focused_camera(camera)
            original_handler(event)
        return handler

    def _set_focused_camera(self, camera: str):
        if camera == self._focused_camera:
            return
        self._focused_camera = camera
        self._sync_focus()
        self.canvas_focus_changed.emit(camera)

    def _sync_focus(self):
        """Update overlay focus borders to match the active camera."""
        self._overlay_single.set_focused(not self._is_split)
        self._overlay_left.set_focused(self._is_split and self._focused_camera == 'left')
        self._overlay_right.set_focused(self._is_split and self._focused_camera == 'right')

    def _apply_scale(self):
        tb = self.top_bar.layout()
        tb.setContentsMargins(scaled(8), scaled(4), scaled(8), scaled(4))
        tb.setSpacing(scaled(8))

        btn_w = physical(46)
        self.toolbar.setMaximumWidth(btn_w + scaled(8))
        self.toolbar.layout().setContentsMargins(0, scaled(4), 0, scaled(4))
        self.toolbar.layout().setSpacing(scaled(4))

        self.run_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.ACCENT}; color: white;
                border: none; border-radius: {scaled(3)}px;
                padding: {scaled(2)}px {scaled(10)}px;
                font-weight: bold; font-size: {scaled_font(9)}pt;
            }}
            QPushButton:hover   {{ background-color: {Colors.ACCENT_HOVER}; }}
            QPushButton:pressed {{ background-color: {Colors.ACCENT_PRESSED}; }}
        """)
        self.update_cursor()

    # ------------------------------------------------------------------
    # Overlays
    # ------------------------------------------------------------------

    def _on_overlay_changed(self, overlay, camera):
        r, g, b, dcs = overlay.get_selection()
        if r and g and b:
            self.rgb_bands_changed.emit(r, g, b, dcs, camera)

    def _sync_overlay_visibility(self):
        self._overlay_single.setVisible(not self._is_split)
        self._overlay_right.setVisible(self._is_split)
        self._overlay_left.setVisible(self._is_split)

    def _reposition_overlays(self):
        for o in (self._overlay_single, self._overlay_right, self._overlay_left):
            o._reposition()

    def set_band_names(self, right_bands, left_bands,
                       r_right=None, g_right=None, b_right=None,
                       r_left=None,  g_left=None,  b_left=None):
        self._overlay_single.populate(right_bands, r_right, g_right, b_right)
        self._overlay_right.populate(right_bands,  r_right, g_right, b_right)
        self._overlay_left.populate(left_bands,    r_left,  g_left,  b_left)

    def get_selected_bands(self, camera='single'):
        return {'single': self._overlay_single,
                'right':  self._overlay_right,
                'left':   self._overlay_left}[camera].get_selection()

    def apply_preset(self, camera: str, r: str, g: str, b: str, dcs: bool):
        """Apply a color scale preset to the given camera's overlay."""
        overlay = {'single': self._overlay_single,
                   'right':  self._overlay_right,
                   'left':   self._overlay_left}[camera]
        overlay.apply_preset(r, g, b, dcs)

    @property
    def focused_camera(self) -> str:
        return 'single' if not self._is_split else self._focused_camera

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def select_tool(self, tool_name):
        self.current_tool = tool_name
        self.btn_selection.set_selected(tool_name == "selection")
        self.btn_rectangle.set_selected(tool_name == "rectangle")
        self.canvas_container.set_tool(tool_name)
        self.canvas_container.set_hover_preview_enabled(tool_name == "rectangle")
        self.tool_changed_signal.emit(tool_name)
        self.update_cursor()

    def update_cursor(self):
        if self.current_tool == "selection":
            size   = physical(_CURSOR_NATIVE_W)
            pixmap = QPixmap(_resource_path("graphics/selection.png")).scaled(
                size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.canvas_container.set_tool_cursor(QCursor(pixmap, 0, 0))
        elif self.current_tool == "rectangle":
            self.canvas_container.set_tool_cursor(Qt.CrossCursor)

    # ------------------------------------------------------------------
    # Split screen
    # ------------------------------------------------------------------

    def _toggle_split_screen(self):
        self._is_split = not self.btn_split_screen.is_selected
        self.btn_split_screen.set_selected(self._is_split)
        self.canvas_container.set_split_mode(self._is_split)
        self._sync_overlay_visibility()
        self._focused_camera = 'right' if self._is_split else 'single'
        self._sync_focus()
        self.split_screen_toggled.emit(self._is_split)
        QTimer.singleShot(0, self._reposition_overlays)

    # ------------------------------------------------------------------
    # Forwarded public API
    # ------------------------------------------------------------------

    def set_image(self, pixmap):
        self.canvas_container.set_image(pixmap)

    def set_rois(self, rois, colors=None):
        self.canvas_container.set_rois(rois, colors)

    def start_loading(self):
        self.loading_indicator.start_loading()

    def stop_loading(self):
        self.loading_indicator.stop_loading()

    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlays()
    
    def fit_focused_canvas(self):
        self.canvas_container.fit_focused_canvas(self.focused_camera)