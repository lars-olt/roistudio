from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QSize
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QCheckBox, QSizePolicy)
from PyQt5.QtGui import QColor

from colors import Colors
from utils.paths import _resource_path
from ..canvas import CanvasContainer, DualCanvasContainer
from ..widgets import ToolbarButton, LoadingIndicator


# ---------------------------------------------------------------------------
# Shared sub-widget styles
# ---------------------------------------------------------------------------

_LABEL_STYLE = (
    f"color: white; font-size: 9pt; background: transparent;"
)

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


# ---------------------------------------------------------------------------
# BandComboBox  (unchanged from previous version)
# ---------------------------------------------------------------------------

class BandComboBox:
    """Lazy import shim — the real class lives in widgets.py via the import
    below. Defined here so BandSelectorOverlay can reference it cleanly."""


# Import the real BandComboBox
from ..widgets import ToolbarButton, LoadingIndicator
try:
    from ..widgets import BandComboBox  # type: ignore
except ImportError:
    # Fallback: define it inline (mirrors the version in widgets.py).
    from PyQt5.QtWidgets import QComboBox, QListView, QFrame
    from PyQt5.QtCore import QPoint as _QPoint

    class BandComboBox(QComboBox):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setStyleSheet(f"""
                QComboBox {{
                    background-color: {Colors.DEFAULT_FEATURE};
                    color: {Colors.TEXT_PRIMARY};
                    border: 1px solid {Colors.PANEL_ACCENT};
                    border-radius: 0px;
                    padding: 1px 4px;
                    font-size: 9pt;
                    font-family: Consolas, monospace;
                }}
                QComboBox:hover {{ border: 1px solid {Colors.ACCENT};
                                   background-color: {Colors.SUBTLE_PANEL_ACCENT}; }}
                QComboBox:focus {{ border: 1px solid {Colors.ACCENT}; }}
                QComboBox::drop-down {{ width: 0px; border: none; }}
                QComboBox QAbstractItemView {{
                    background-color: {Colors.PANEL_BACKGROUND};
                    color: {Colors.TEXT_PRIMARY};
                    border: 1px solid {Colors.ACCENT};
                    border-radius: 0px; padding: 0px; outline: none;
                    font-size: 9pt; font-family: Consolas, monospace;
                }}
                QComboBox QAbstractItemView::item {{
                    padding: 3px 8px; border: none;
                }}
                QComboBox QAbstractItemView::item:selected {{
                    background-color: {Colors.ACCENT}; color: white;
                }}
                QComboBox QAbstractItemView::item:hover {{
                    background-color: {Colors.SUBTLE_PANEL_ACCENT};
                }}
            """)
            self.setMaxVisibleItems(16)
            view = QListView()
            view.setUniformItemSizes(True)
            self.setView(view)

        def showPopup(self):
            super().showPopup()
            popup = self.findChild(QFrame)
            if popup is None:
                return
            fm    = self.fontMetrics()
            max_w = max(
                (fm.horizontalAdvance(self.itemText(i)) for i in range(self.count())),
                default=0
            ) + 24
            popup.setFixedWidth(max(self.width(), max_w))
            # position above the widget, flush with its top edge
            popup.move(self.mapToGlobal(_QPoint(0, -popup.height())))


# ---------------------------------------------------------------------------
# BandSelectorOverlay
# ---------------------------------------------------------------------------

_OVERLAY_BG = QColor(40, 40, 40, 180)   # same dark-glass as zoom indicator


class BandSelectorOverlay(QWidget):
    """
    Floating overlay widget parented to a CanvasContainer.
    Sits at bottom-centre, same height as the zoom indicator.
    Contains R/G/B dropdowns and a DCS toggle.
    Signals fire whenever the user changes any control.
    """

    changed = pyqtSignal()   # any control changed — parent re-renders

    # Geometry constants matching the zoom indicator
    _PADDING   = 10   # distance from canvas edge
    _MARGIN    = 8    # internal horizontal padding
    _V_MARGIN  = 5    # internal vertical padding

    def __init__(self, camera: str, parent: CanvasContainer):
        """
        camera: 'left' | 'right' | 'single'  (display only, not used in logic)
        parent: the CanvasContainer this floats over
        """
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
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

        for lbl_text, combo in (("R:", self.combo_r),
                                 ("G:", self.combo_g),
                                 ("B:", self.combo_b)):
            lbl = QLabel(lbl_text)
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

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def populate(self, band_names, r_default=None, g_default=None, b_default=None):
        """Fill all three dropdowns and pre-select defaults."""
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
            (
                _pick(r_default, ('R0R', 'R2'), 0),
                _pick(g_default, ('R0G', 'R1'), 1),
                _pick(b_default, ('R0B', 'R1'), 2),
            )
        ):
            combo.blockSignals(True)
            combo.setCurrentText(sel)
            combo.blockSignals(False)

        self.adjustSize()
        self._reposition()

    def get_selection(self):
        """Returns (r_band, g_band, b_band, use_dcs)."""
        return (
            self.combo_r.currentText(),
            self.combo_g.currentText(),
            self.combo_b.currentText(),
            self.chk_dcs.isChecked(),
        )

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _reposition(self):
        """Centre horizontally, align bottom with zoom indicator."""
        parent = self.parent()
        if parent is None:
            return
        self.adjustSize()
        pw, ph = parent.width(), parent.height()
        w, h   = self.width(), self.height()
        x = (pw - w) // 2
        y = ph - h - self._PADDING
        self.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    # ------------------------------------------------------------------
    # Painting — dark-glass pill matching zoom indicator
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), _OVERLAY_BG)
        painter.end()


# ---------------------------------------------------------------------------
# ImageEditingPanel
# ---------------------------------------------------------------------------

class ImageEditingPanel(QWidget):
    """Panel for image editing with canvas and toolbar."""

    run_algorithm_signal    = pyqtSignal()
    scene_dropped_signal    = pyqtSignal(str)
    spectral_preview_signal = pyqtSignal(int, int)
    tool_changed_signal     = pyqtSignal(str)
    rgb_bands_changed       = pyqtSignal(str, str, str, bool, str)
    # ^ (r, g, b, use_dcs, camera: 'left'|'right'|'single')

    roi_changed  = pyqtSignal(int, tuple, str)
    roi_deleted  = pyqtSignal(int)
    roi_created  = pyqtSignal(tuple, str)

    split_screen_toggled = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.current_tool    = 'selection'
        self._is_split       = False
        self._right_bands    = []
        self._left_bands     = []
        self.init_ui()
        self.canvas_container.installEventFilter(self)

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        # --- top bar (Run + loading indicator only) ---
        top_bar = QWidget()
        top_bar.setStyleSheet(
            f"background-color: {Colors.PANEL_ACCENT}; "
            f"border-bottom: 1px solid {Colors.DEFAULT_FEATURE};"
        )
        top_bar.setMaximumHeight(35)
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(8, 4, 8, 4)
        top_bar_layout.setSpacing(8)
        top_bar.setLayout(top_bar_layout)

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
            QPushButton:hover  {{ background-color: {Colors.ACCENT_HOVER}; }}
            QPushButton:pressed {{ background-color: {Colors.ACCENT_PRESSED}; }}
        """)
        self.run_button.clicked.connect(self.on_run_clicked)
        top_bar_layout.addWidget(self.run_button)

        self.loading_indicator = LoadingIndicator()
        top_bar_layout.addSpacing(5)
        top_bar_layout.addWidget(self.loading_indicator)
        top_bar_layout.addStretch()
        layout.addWidget(top_bar)

        # --- content (toolbar + canvas) ---
        content_widget = QWidget()
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_widget.setLayout(content_layout)

        self.toolbar = QWidget()
        self.toolbar.setStyleSheet(
            f"background-color: {Colors.PANEL_ACCENT}; "
            f"border-right: 1px solid {Colors.DEFAULT_FEATURE};"
        )
        self.toolbar.setMaximumWidth(54)
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_layout.setSpacing(4)
        self.toolbar.setLayout(toolbar_layout)

        self.btn_selection = ToolbarButton(
            _resource_path("graphics/toolbar_selection.png"),
            _resource_path("graphics/toolbar_selection_selected.png")
        )
        self.btn_selection.set_selected(True)
        self.btn_selection.clicked.connect(lambda: self.select_tool("selection"))
        toolbar_layout.addWidget(self.btn_selection)

        self.btn_rectangle = ToolbarButton(
            _resource_path("graphics/toolbar_rectangle.png"),
            _resource_path("graphics/toolbar_rectangle_selected.png")
        )
        self.btn_rectangle.clicked.connect(lambda: self.select_tool("rectangle"))
        toolbar_layout.addWidget(self.btn_rectangle)

        toolbar_layout.addStretch()

        self.btn_split_screen = ToolbarButton(
            _resource_path("graphics/toolbar_single_screen.png"),
            _resource_path("graphics/toolbar_split_screen.png")
        )
        self.btn_split_screen.set_selected(False)
        self.btn_split_screen.clicked.connect(self.toggle_split_screen)
        toolbar_layout.addWidget(self.btn_split_screen)

        content_layout.addWidget(self.toolbar)

        self.canvas_container = DualCanvasContainer()
        self.canvas_container.scene_dropped.connect(self.scene_dropped_signal.emit)
        self.canvas_container.roi_changed.connect(self.roi_changed.emit)
        self.canvas_container.roi_deleted.connect(self.roi_deleted.emit)
        self.canvas_container.roi_created.connect(self.roi_created.emit)
        content_layout.addWidget(self.canvas_container)

        layout.addWidget(content_widget)

        # --- overlays (parented to their respective CanvasContainers) ---
        self._overlay_single = BandSelectorOverlay(
            'single', self.canvas_container.canvas_single
        )
        self._overlay_right = BandSelectorOverlay(
            'right', self.canvas_container.canvas_right
        )
        self._overlay_left = BandSelectorOverlay(
            'left', self.canvas_container.canvas_left
        )

        self._overlay_single.changed.connect(
            lambda: self._emit_changed(self._overlay_single, 'single')
        )
        self._overlay_right.changed.connect(
            lambda: self._emit_changed(self._overlay_right, 'right')
        )
        self._overlay_left.changed.connect(
            lambda: self._emit_changed(self._overlay_left, 'left')
        )

        self._update_overlay_visibility()
        self.update_cursor()

    # ------------------------------------------------------------------
    # Overlay management
    # ------------------------------------------------------------------

    def _emit_changed(self, overlay: BandSelectorOverlay, camera: str):
        r, g, b, dcs = overlay.get_selection()
        if r and g and b:
            self.rgb_bands_changed.emit(r, g, b, dcs, camera)

    def _update_overlay_visibility(self):
        self._overlay_single.setVisible(not self._is_split)
        self._overlay_right.setVisible(self._is_split)
        self._overlay_left.setVisible(self._is_split)

    def set_band_names(self, right_bands, left_bands,
                       r_right=None, g_right=None, b_right=None,
                       r_left=None,  g_left=None,  b_left=None):
        """
        Populate overlays.  right_bands / left_bands are separate lists
        so each camera only shows its own filters.
        """
        self._right_bands = right_bands
        self._left_bands  = left_bands

        # Single mode shows right-eye bands (reference camera).
        self._overlay_single.populate(right_bands, r_right, g_right, b_right)
        self._overlay_right.populate(right_bands,  r_right, g_right, b_right)
        self._overlay_left.populate(left_bands,    r_left,  g_left,  b_left)

    def get_selected_bands(self, camera='single'):
        """Returns (r, g, b, use_dcs) for the requested camera overlay."""
        overlay = {
            'single': self._overlay_single,
            'right':  self._overlay_right,
            'left':   self._overlay_left,
        }.get(camera, self._overlay_single)
        return overlay.get_selection()

    # ------------------------------------------------------------------
    # Compatibility shims expected by controller
    # ------------------------------------------------------------------

    @property
    def chk_dcs(self):
        """Return the active overlay's DCS checkbox (single or right)."""
        return (self._overlay_right if self._is_split
                else self._overlay_single).chk_dcs

    # ------------------------------------------------------------------
    # Tool / cursor / split screen
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
            cursor_pixmap = QPixmap(_resource_path("graphics/selection.png"))
            self.canvas_container.set_tool_cursor(QCursor(cursor_pixmap, 0, 0))
        elif self.current_tool == "rectangle":
            self.canvas_container.set_tool_cursor(Qt.CrossCursor)

    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    def on_run_clicked(self):
        self.run_algorithm_signal.emit()

    def toggle_split_screen(self):
        self._is_split = not self.btn_split_screen.is_selected
        self.btn_split_screen.set_selected(self._is_split)
        self.canvas_container.set_split_mode(self._is_split)
        self._update_overlay_visibility()
        self.split_screen_toggled.emit(self._is_split)
        # Defer reposition so Qt has finished the layout pass first.
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._reposition_overlays)

    def _reposition_overlays(self):
        for overlay in (self._overlay_single, self._overlay_right,
                        self._overlay_left):
            overlay._reposition()

    def set_image(self, pixmap):
        self.canvas_container.set_image(pixmap)

    def set_rois(self, rois, colors=None):
        self.canvas_container.set_rois(rois, colors)

    def start_loading(self):
        self.loading_indicator.start_loading()

    def stop_loading(self):
        self.loading_indicator.stop_loading()

    # ------------------------------------------------------------------
    # Overlay repositioning on resize
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlays()