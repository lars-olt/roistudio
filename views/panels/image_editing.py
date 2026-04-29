from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QCheckBox)
from PyQt5.QtGui import QColor, QPainter

from colors import Colors
from utils.paths import _resource_path
from ..canvas import CanvasContainer, DualCanvasContainer
from ..widgets import ToolbarButton, LoadingIndicator, BandComboBox


_LABEL_STYLE = "color: white; font-size: 9pt; background: transparent;"

_CHECKBOX_STYLE = f"""
    QCheckBox {{
        color: white;
        font-size: 9pt;
        background: transparent;
        spacing: 4px;
    }}
    QCheckBox::indicator {{
        width: 12px; height: 12px;
        border: 1px solid {Colors.PANEL_ACCENT};
        border-radius: 0px;
        background: transparent;
    }}
    QCheckBox::indicator:checked {{
        background: {Colors.ACCENT};
        border: 1px solid {Colors.ACCENT};
    }}
    QCheckBox::indicator:hover {{
        border: 1px solid {Colors.ACCENT};
    }}
    QToolTip {{
        background-color: {Colors.PANEL_BACKGROUND};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.ACCENT};
        padding: 4px;
    }}
"""

_OVERLAY_BG = QColor(40, 40, 40, 180)


class BandSelectorOverlay(QWidget):
    """
    Floating R/G/B + DCS selector parented to a CanvasContainer.
    Sits at bottom-centre, same level as the zoom indicator.
    """

    changed = pyqtSignal()

    _PADDING  = 10
    _MARGIN   = 8
    _V_MARGIN = 5

    def __init__(self, parent: CanvasContainer):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)

        row = QHBoxLayout()
        row.setContentsMargins(self._MARGIN, self._V_MARGIN,
                               self._MARGIN, self._V_MARGIN)
        row.setSpacing(6)
        self.setLayout(row)

        self.combo_r = BandComboBox()
        self.combo_g = BandComboBox()
        self.combo_b = BandComboBox()
        for combo in (self.combo_r, self.combo_g, self.combo_b):
            combo.setFixedWidth(52)

        for label, combo in (("R:", self.combo_r),
                              ("G:", self.combo_g),
                              ("B:", self.combo_b)):
            lbl = QLabel(label)
            lbl.setStyleSheet(_LABEL_STYLE)
            row.addWidget(lbl)
            row.addWidget(combo)

        sep = QLabel("|")
        sep.setStyleSheet(
            f"color: {Colors.PANEL_ACCENT}; font-size: 9pt; background: transparent;"
        )
        row.addWidget(sep)

        self.chk_dcs = QCheckBox("DCS")
        self.chk_dcs.setChecked(False)
        self.chk_dcs.setToolTip("Apply decorrelation stretch to selected bands.")
        self.chk_dcs.setStyleSheet(_CHECKBOX_STYLE)
        row.addWidget(self.chk_dcs)

        self.combo_r.currentTextChanged.connect(self.changed.emit)
        self.combo_g.currentTextChanged.connect(self.changed.emit)
        self.combo_b.currentTextChanged.connect(self.changed.emit)
        self.chk_dcs.toggled.connect(self.changed.emit)

        self.adjustSize()

    def populate(self, band_names, r=None, g=None, b=None):
        for combo in (self.combo_r, self.combo_g, self.combo_b):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(band_names)
            combo.blockSignals(False)

        def _pick(preferred, fallbacks, idx):
            if preferred and preferred in band_names:
                return preferred
            for c in fallbacks:
                if c in band_names:
                    return c
            return band_names[min(idx, len(band_names) - 1)] if band_names else ''

        for combo, sel in zip(
            (self.combo_r, self.combo_g, self.combo_b),
            (_pick(r, ('R0R', 'R2'), 0),
             _pick(g, ('R0G', 'R1'), 1),
             _pick(b, ('R0B', 'R1'), 2))
        ):
            combo.blockSignals(True)
            combo.setCurrentText(sel)
            combo.blockSignals(False)

        self.adjustSize()
        self._reposition()

    def get_selection(self):
        """Returns (r_band, g_band, b_band, use_dcs)."""
        return (self.combo_r.currentText(),
                self.combo_g.currentText(),
                self.combo_b.currentText(),
                self.chk_dcs.isChecked())

    def _reposition(self):
        parent = self.parent()
        if parent is None:
            return
        self.adjustSize()
        x = (parent.width()  - self.width())  // 2
        y =  parent.height() - self.height()  - self._PADDING
        self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), _OVERLAY_BG)
        painter.end()


class ImageEditingPanel(QWidget):
    """Image canvas panel with toolbar and per-camera band selector overlays."""

    run_algorithm_signal    = pyqtSignal()
    scene_dropped_signal    = pyqtSignal(str)
    spectral_preview_signal = pyqtSignal(int, int)
    tool_changed_signal     = pyqtSignal(str)
    # (r, g, b, use_dcs, camera: 'left'|'right'|'single')
    rgb_bands_changed       = pyqtSignal(str, str, str, bool, str)

    roi_changed  = pyqtSignal(int, tuple, str)
    roi_deleted  = pyqtSignal(int)
    roi_created  = pyqtSignal(tuple, str)

    split_screen_toggled = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.current_tool = 'selection'
        self._is_split    = False
        self.init_ui()
        self.canvas_container.installEventFilter(self)

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        # top bar - Run button and loading indicator only
        top_bar = QWidget()
        top_bar.setStyleSheet(
            f"background-color: {Colors.PANEL_ACCENT}; "
            f"border-bottom: 1px solid {Colors.DEFAULT_FEATURE};"
        )
        top_bar.setMaximumHeight(35)
        tb_layout = QHBoxLayout()
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(8)
        top_bar.setLayout(tb_layout)

        self.run_button = QPushButton("Run")
        self.run_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.ACCENT};
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 16px;
                font-weight: bold;
            }}
            QPushButton:hover   {{ background-color: {Colors.ACCENT_HOVER}; }}
            QPushButton:pressed {{ background-color: {Colors.ACCENT_PRESSED}; }}
        """)
        self.run_button.clicked.connect(self.run_algorithm_signal.emit)
        tb_layout.addWidget(self.run_button)

        self.loading_indicator = LoadingIndicator()
        tb_layout.addSpacing(5)
        tb_layout.addWidget(self.loading_indicator)
        tb_layout.addStretch()
        layout.addWidget(top_bar)

        # content - side toolbar + canvas
        content = QWidget()
        c_layout = QHBoxLayout()
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)
        content.setLayout(c_layout)

        self.toolbar = QWidget()
        self.toolbar.setStyleSheet(
            f"background-color: {Colors.PANEL_ACCENT}; "
            f"border-right: 1px solid {Colors.DEFAULT_FEATURE};"
        )
        self.toolbar.setMaximumWidth(54)
        t_layout = QVBoxLayout()
        t_layout.setContentsMargins(4, 4, 4, 4)
        t_layout.setSpacing(4)
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
        self.btn_split_screen.clicked.connect(self.toggle_split_screen)
        t_layout.addWidget(self.btn_split_screen)

        c_layout.addWidget(self.toolbar)

        self.canvas_container = DualCanvasContainer()
        self.canvas_container.scene_dropped.connect(self.scene_dropped_signal.emit)
        self.canvas_container.roi_changed.connect(self.roi_changed.emit)
        self.canvas_container.roi_deleted.connect(self.roi_deleted.emit)
        self.canvas_container.roi_created.connect(self.roi_created.emit)
        c_layout.addWidget(self.canvas_container)

        layout.addWidget(content)

        # overlays - one per canvas, parented directly to their canvas widget
        self._overlay_single = BandSelectorOverlay(self.canvas_container.canvas_single)
        self._overlay_right  = BandSelectorOverlay(self.canvas_container.canvas_right)
        self._overlay_left   = BandSelectorOverlay(self.canvas_container.canvas_left)

        for overlay, camera in ((self._overlay_single, 'single'),
                                (self._overlay_right,  'right'),
                                (self._overlay_left,   'left')):
            overlay.changed.connect(lambda c=camera, o=overlay: self._on_overlay_changed(o, c))

        self._sync_overlay_visibility()
        self.update_cursor()
        QTimer.singleShot(0, self._reposition_overlays)

    # ------------------------------------------------------------------
    # Overlay helpers
    # ------------------------------------------------------------------

    def _on_overlay_changed(self, overlay: BandSelectorOverlay, camera: str):
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
        # single mode uses the right-camera bands as the reference view
        self._overlay_single.populate(right_bands, r_right, g_right, b_right)
        self._overlay_right.populate(right_bands,  r_right, g_right, b_right)
        self._overlay_left.populate(left_bands,    r_left,  g_left,  b_left)

    def get_selected_bands(self, camera='single'):
        """Returns (r, g, b, use_dcs) for the given camera."""
        return {
            'single': self._overlay_single,
            'right':  self._overlay_right,
            'left':   self._overlay_left,
        }[camera].get_selection()

    # ------------------------------------------------------------------
    # Tool / cursor
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
            from PyQt5.QtGui import QCursor, QPixmap
            self.canvas_container.set_tool_cursor(
                QCursor(QPixmap(_resource_path("graphics/selection.png")), 0, 0)
            )
        elif self.current_tool == "rectangle":
            self.canvas_container.set_tool_cursor(Qt.CrossCursor)

    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Split screen
    # ------------------------------------------------------------------

    def toggle_split_screen(self):
        self._is_split = not self.btn_split_screen.is_selected
        self.btn_split_screen.set_selected(self._is_split)
        self.canvas_container.set_split_mode(self._is_split)
        self._sync_overlay_visibility()
        self.split_screen_toggled.emit(self._is_split)
        # defer reposition until Qt has finished the layout pass
        QTimer.singleShot(0, self._reposition_overlays)

    # ------------------------------------------------------------------
    # Forwarded methods
    # ------------------------------------------------------------------

    def set_image(self, pixmap):
        self.canvas_container.set_image(pixmap)

    def set_rois(self, rois, colors=None):
        self.canvas_container.set_rois(rois, colors)

    def start_loading(self):
        self.loading_indicator.start_loading()

    def stop_loading(self):
        self.loading_indicator.stop_loading()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlays()