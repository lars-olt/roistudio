from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPoint, QPointF, QRectF
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QComboBox, QFrame)
from PyQt5.QtGui import QColor, QPainter, QPen, QCursor, QPixmap, QFontMetrics, QFont

from colors import Colors
from utils.paths import _resource_path
from utils.scale import Scale, physical, scaled, scaled_font
from ..canvas import CanvasContainer, DualCanvasContainer
from ..widgets import ToolbarButton, LoadingIndicator, BandComboBox
from .stretch_bar import StretchBar

_OVERLAY_BG      = QColor(40, 40, 40, 180)
_CURSOR_NATIVE_W = 32


class ImageEditingPanel(QWidget):
    """Image canvas panel with toolbar and per-camera band selector overlays."""

    run_algorithm_signal = pyqtSignal()
    scene_dropped_signal = pyqtSignal(str)
    tool_changed_signal  = pyqtSignal(str)
    rgb_bands_changed    = pyqtSignal(str, str, str, bool, str)
    roi_changed          = pyqtSignal(int, tuple, str)
    roi_deleted          = pyqtSignal(int)
    roi_created          = pyqtSignal(tuple, str)
    roi_too_small        = pyqtSignal()
    split_screen_toggled     = pyqtSignal(bool)
    split_screen_exit_requested = pyqtSignal()
    canvas_focus_changed = pyqtSignal(str)   # 'single' | 'left' | 'right'

    def __init__(self):
        super().__init__()
        self.current_tool    = 'selection'
        self._is_split       = False
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
        self.canvas_container.roi_too_small.connect(self.roi_too_small.emit)
        self.canvas_container.tool_shortcut.connect(self.select_tool)
        c_layout.addWidget(self.canvas_container)
        layout.addWidget(content)

        # Band selector overlays — one per camera, parented to their canvas
        self._overlay_single = StretchBar(self.canvas_container.canvas_single)
        self._overlay_right  = StretchBar(self.canvas_container.canvas_right)
        self._overlay_left   = StretchBar(self.canvas_container.canvas_left)

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
        self.toolbar.setFixedWidth(btn_w + scaled(8))
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
        entering_split = not self.btn_split_screen.is_selected
        if not entering_split:
            # Let the controller decide whether to proceed (may show a confirmation dialog).
            self.split_screen_exit_requested.emit()
            return
        self._apply_split_screen(True)

    def confirm_split_screen_exit(self):
        """Called by the controller after the user confirms they want to leave split screen."""
        self._apply_split_screen(False)

    def _apply_split_screen(self, is_split: bool):
        self._is_split = is_split
        self.btn_split_screen.set_selected(is_split)
        self.canvas_container.set_split_mode(is_split)
        self._sync_overlay_visibility()
        self._focused_camera = 'right' if is_split else 'single'
        self._sync_focus()
        if not is_split:
            self.canvas_container.set_sync_enabled(False)
        self.split_screen_toggled.emit(is_split)
        QTimer.singleShot(0, self._reposition_overlays)

    # ------------------------------------------------------------------
    # Sync views
    # ------------------------------------------------------------------

    def set_sync_enabled(self, enabled: bool):
        self.canvas_container.set_sync_enabled(enabled, self.focused_camera)

    # ------------------------------------------------------------------
    # Fit canvas
    # ------------------------------------------------------------------

    def fit_focused_canvas(self):
        canvas = {'single': self.canvas_container.canvas_single,
                  'left':   self.canvas_container.canvas_left,
                  'right':  self.canvas_container.canvas_right}[self.focused_camera]
        canvas.fit_to_panel()

    # ------------------------------------------------------------------
    # Forwarded public API
    # ------------------------------------------------------------------

    def set_overlay_presets(self, presets: dict):
        """Push instrument presets to all three overlays."""
        self._overlay_single.set_presets('right', presets)
        self._overlay_right.set_presets('right', presets)
        self._overlay_left.set_presets('left', presets)

    def set_image(self, pixmap):
        self.canvas_container.set_image(pixmap)

    def set_rois(self, rois, colors=None, names=None):
        self.canvas_container.set_rois(rois, colors, names)

    def start_loading(self):
        self.loading_indicator.start_loading()

    def stop_loading(self):
        self.loading_indicator.stop_loading()

    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlays()

    def set_roi_labels_visible(self, visible: bool):
        self.canvas_container.set_roi_labels_visible(visible)