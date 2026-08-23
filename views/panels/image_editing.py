from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PyQt5.QtGui import QColor, QPainter, QPen, QCursor, QPixmap

from colors import Colors
from utils.paths import _resource_path
from utils.scale import Scale, capped_scaled, scaled, scaled_font
from ..canvas import DualCanvasContainer
from ..widgets import (ToolbarButton, LoadingIndicator, ColorSwatchGrid,
                       toolbar_button_size)
from .stretch_bar import StretchBar

_CURSOR_NATIVE_W     = 24
_CURSOR_MAX_W        = 28
_TOOLBAR_PADDING_MAX = 10
_TOOLBAR_GAP_MAX     = 5


class _ActiveColorSwatch(QWidget):
    """Toolbar swatch showing the next ROI color. Click to open the palette."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color   = (150, 150, 150)
        self._hovered = False
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Next ROI color - click to change")
        self.setMouseTracking(True)
        self._apply_scale()
        Scale.changed.connect(self._apply_scale)

    def _apply_scale(self):
        self.setFixedSize(*toolbar_button_size())

    def set_color(self, color):
        self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        from PyQt5.QtSvg import QSvgRenderer
        QSvgRenderer(_resource_path("graphics/toolbar_blank.svg")).render(painter)

        sz       = int(min(self.width(), self.height()) * 0.55)
        margin_x = (self.width()  - sz) // 2
        margin_y = (self.height() - sz) // 2
        radius   = scaled(3)
        outline  = QColor(Colors.ACCENT) if self._hovered else QColor(Colors.TEXT_SECONDARY)
        painter.setPen(QPen(outline, 1))
        painter.setBrush(QColor(*self._color))
        painter.drawRoundedRect(margin_x, margin_y, sz, sz, radius, radius)
        painter.end()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class ImageEditingPanel(QWidget):
    """Image canvas panel with toolbar and per-camera band selector overlays."""

    run_algorithm_signal = pyqtSignal()
    scene_dropped_signal = pyqtSignal(str)
    tool_changed_signal  = pyqtSignal(str)
    rgb_bands_changed    = pyqtSignal(str, str, str, bool, str)
    roi_changed          = pyqtSignal(int, tuple, str)
    roi_deleted          = pyqtSignal(int, str)
    roi_created          = pyqtSignal(tuple, str)
    roi_too_small        = pyqtSignal()
    roi_right_clicked    = pyqtSignal(int, QPoint, str)  # roi_index, global pos, camera
    active_color_palette_requested = pyqtSignal()
    split_screen_toggled        = pyqtSignal(bool)
    split_screen_exit_requested = pyqtSignal()
    split_screen_unavailable    = pyqtSignal()
    canvas_focus_changed        = pyqtSignal(str)   # 'single' | 'left' | 'right'
    crop_changed                = pyqtSignal(tuple)  # (x, y, w, h)

    def __init__(self, algorithm_enabled=True):
        super().__init__()
        self.algorithm_enabled = algorithm_enabled
        self.current_tool    = 'selection'
        self._is_split       = False
        self._focused_camera = 'single'
        self._crop_enabled   = False  # only true when scene loaded and single screen
        self._build_ui()
        self.canvas_container.installEventFilter(self)
        Scale.changed.connect(self._apply_scale)

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        # Content area - side toolbar + canvas
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
            _resource_path("graphics/toolbar_selection.svg"),
            _resource_path("graphics/toolbar_selection_selected.svg")
        )
        self.btn_selection.setToolTip("Selection tool (V)")
        self.btn_selection.set_selected(True)
        self.btn_selection.clicked.connect(lambda: self.select_tool("selection"))
        t_layout.addWidget(self.btn_selection)

        self.btn_rectangle = ToolbarButton(
            _resource_path("graphics/toolbar_rectangle.svg"),
            _resource_path("graphics/toolbar_rectangle_selected.svg")
        )
        self.btn_rectangle.setToolTip("Rectangle ROI tool (R)")
        self.btn_rectangle.clicked.connect(lambda: self.select_tool("rectangle"))
        t_layout.addWidget(self.btn_rectangle)

        self.btn_resize = ToolbarButton(
            _resource_path("graphics/toolbar_resize.svg"),
            _resource_path("graphics/toolbar_resize_selected.svg"),
            hover_icon_path = _resource_path("graphics/toolbar_resize_hover.svg"),
        )
        self.btn_resize.setToolTip("Resize frame (single screen only)")
        self.btn_resize.set_selected(False)
        self.btn_resize.setEnabled(False)
        self.btn_resize.clicked.connect(lambda: self.select_tool("crop"))
        t_layout.addWidget(self.btn_resize)

        self._color_swatch = _ActiveColorSwatch()
        self._color_swatch.clicked.connect(self._on_active_color_clicked)
        t_layout.addWidget(self._color_swatch)

        self.run_button = None
        if self.algorithm_enabled:
            self.run_button = ToolbarButton(
                _resource_path("graphics/toolbar_run.png"),
                hover_icon_path=_resource_path("graphics/toolbar_run_hover.png"),
            )
            self.run_button.setToolTip("Run SPARC")
            self.run_button.clicked.connect(self.run_algorithm_signal.emit)
            t_layout.addWidget(self.run_button)

        t_layout.addSpacing(capped_scaled(3, _TOOLBAR_GAP_MAX))
        self.loading_indicator = LoadingIndicator()
        self.loading_indicator.setAccessibleName("Background activity in progress")
        t_layout.addWidget(self.loading_indicator, 0, Qt.AlignHCenter)

        t_layout.addStretch()

        self.btn_split_screen = ToolbarButton(
            _resource_path("graphics/toolbar_single_screen.svg"),
            _resource_path("graphics/toolbar_split_screen.svg"),
            hover_icon_path          = _resource_path("graphics/toolbar_single_screen_hover.svg"),
            selected_hover_icon_path = _resource_path("graphics/toolbar_split_screen_hover.svg"),
        )
        self.btn_split_screen.setToolTip("Toggle split screen")
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
        self.canvas_container.roi_right_clicked.connect(self.roi_right_clicked.emit)
        self.canvas_container.crop_changed.connect(self.crop_changed.emit)

        self._swatch_grid = ColorSwatchGrid(self)
        c_layout.addWidget(self.canvas_container)
        layout.addWidget(content)

        # Band selector overlays - one per camera, parented to their canvas
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
        btn_w, _ = toolbar_button_size()
        padding = capped_scaled(6, _TOOLBAR_PADDING_MAX)
        gap = capped_scaled(3, _TOOLBAR_GAP_MAX)
        self.toolbar.setFixedWidth(btn_w + padding)
        self.toolbar.layout().setContentsMargins(0, gap, 0, gap)
        self.toolbar.layout().setSpacing(gap)
        self.toolbar.setStyleSheet(f"""
            QWidget {{
                background-color: {Colors.PANEL_ACCENT};
                border-right: 1px solid {Colors.DEFAULT_FEATURE};
            }}
            QToolTip {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.ACCENT};
                padding: {scaled(4)}px;
                font-size: {scaled_font(9)}pt;
            }}
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

    def set_band_names(self, single_bands, right_bands, left_bands,
                        r_single=None, g_single=None, b_single=None,
                        r_right=None,  g_right=None,  b_right=None,
                        r_left=None,   g_left=None,   b_left=None):
        self._overlay_single.populate(single_bands, r_single, g_single, b_single)
        self._overlay_right.populate(right_bands,   r_right,  g_right,  b_right)
        self._overlay_left.populate(left_bands,     r_left,   g_left,   b_left)

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
        # crop tool is only available when enabled
        if tool_name == "crop" and not self._crop_enabled:
            return
        self.current_tool = tool_name
        self.btn_selection.set_selected(tool_name == "selection")
        self.btn_rectangle.set_selected(tool_name == "rectangle")
        self.btn_resize.set_selected(tool_name == "crop")
        self.canvas_container.set_tool(tool_name)
        self.canvas_container.set_hover_preview_enabled(tool_name == "rectangle")
        self.tool_changed_signal.emit(tool_name)
        self.update_cursor()

    def update_cursor(self):
        if self.current_tool == "selection":
            from PyQt5.QtSvg import QSvgRenderer
            size   = capped_scaled(_CURSOR_NATIVE_W, _CURSOR_MAX_W)
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            QSvgRenderer(_resource_path("graphics/selection.svg")).render(painter)
            painter.end()
            self.canvas_container.set_tool_cursor(QCursor(pixmap, 0, 0))
        elif self.current_tool == "rectangle":
            self.canvas_container.set_tool_cursor(Qt.CrossCursor)
        elif self.current_tool == "crop":
            self.canvas_container.set_tool_cursor(Qt.ArrowCursor)

    def set_crop_enabled(self, enabled: bool):
        """Enable or disable the crop tool - controlled by controller based on scene/split state."""
        self._crop_enabled = enabled
        self.btn_resize.setEnabled(enabled)
        if not enabled and self.current_tool == "crop":
            self.select_tool("selection")

    def get_crop_rect(self):
        """Return current crop rect as (x, y, w, h) ints, or None for full frame."""
        r = self.canvas_container.get_crop_rect()
        if r is None:
            return None
        return (int(r.x()), int(r.y()), int(r.width()), int(r.height()))

    # ------------------------------------------------------------------
    # Split screen
    # ------------------------------------------------------------------

    def _toggle_split_screen(self):
        entering_split = not self.btn_split_screen.is_selected
        if not entering_split:
            self.split_screen_exit_requested.emit()
            return
        if not getattr(self, '_split_screen_enabled', True):
            self.btn_split_screen.set_selected(False)
            self.split_screen_unavailable.emit()
            return
        self._apply_split_screen(True)

    def enter_split_screen(self):
        """Programmatically enter split screen if the scene supports it.

        Used after loading a .sel so a stereo scene shows both cameras' loaded
        rects. No-op when split screen is unavailable or already active.
        """
        if self._is_split or not getattr(self, '_split_screen_enabled', True):
            return
        self._apply_split_screen(True)

    def confirm_split_screen_exit(self):
        """Complete the controller-mediated return to single-screen mode."""
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
        # crop tool only works in single screen
        if is_split and self._crop_enabled:
            self.set_crop_enabled(False)
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

    def set_active_color(self, color):
        """Update the active color swatch to reflect the next color."""
        self._color_swatch.set_color(color)

    def _on_active_color_clicked(self):
        self.active_color_palette_requested.emit()
        self._swatch_grid.set_spectrum_action(False)
        self._swatch_grid.show_at(
            self._color_swatch.mapToGlobal(
                self._color_swatch.rect().bottomLeft()
            )
        )

    def set_swatch_palette(self, palette, in_use_names, selected_name=None):
        """Repopulate the ROI color palette."""
        self._swatch_grid.populate(palette, in_use_names, selected_name)

    def set_overlay_presets(self, presets: dict, single_side: str = 'right'):
        """Push instrument presets to all three overlays."""
        self._overlay_single.set_presets(single_side, presets)
        self._overlay_right.set_presets('right', presets)
        self._overlay_left.set_presets('left', presets)

    def set_stretch_enabled(self, camera: str, enabled: bool):
        """Set whether manual band selection is available for a camera."""
        overlay = {'single': self._overlay_single,
                'right':  self._overlay_right,
                'left':   self._overlay_left}[camera]
        overlay.set_bands_available(enabled)

    def set_split_screen_enabled(self, enabled: bool):
        """Mark split screen as available or not for the current scene."""
        self._split_screen_enabled = enabled
        self.btn_split_screen.setToolTip(
            "Toggle split screen" if enabled
            else "Split screen unavailable - scene only has images from one camera"
        )
        if not enabled and self._is_split:
            self._apply_split_screen(False)

    def set_image(self, pixmap):
        self.canvas_container.set_image(pixmap)

    def set_rois(self, rois, colors=None, names=None):
        self.canvas_container.set_rois(rois, colors, names)

    def start_loading(self):
        if self.run_button is not None:
            self.run_button.setEnabled(False)
        self.loading_indicator.start_loading()

    def stop_loading(self):
        self.loading_indicator.stop_loading()
        if self.run_button is not None:
            self.run_button.setEnabled(True)

    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlays()

    def set_roi_labels_visible(self, visible: bool):
        self.canvas_container.set_roi_labels_visible(visible)

    def set_zoom_context_visible(self, visible: bool):
        self.canvas_container.set_zoom_context_visible(visible)
