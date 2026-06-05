from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QMenuBar, QMenu, QAction,
                             QSplitter, QStackedWidget)

from .panels import SpectralViewPanel, ImageSelectionPanel, ImageEditingPanel, StatusPanel, ParameterSelectionPanel
from colors import Colors
from utils.scale import Scale, scaled, scaled_font


_DEFAULT_WINDOW_WIDTH  = 1600
_DEFAULT_WINDOW_HEIGHT = 900

_MAIN_RATIO = 0.35

# All named color/band presets, keyed by instrument.
# Each entry: label shown in the menu and stretch bar, camera side, R/G/B band names, DCS flag.
# Edit these to change what any preset does - one place, affects both the View menu and the overlay.
INSTRUMENT_PRESETS = {
    'ZCAM': {
        'right': {
            'RGB': {'r': 'R0R', 'g': 'R0G', 'b': 'R0B', 'dcs': False},
            'DCS': {'r': 'R6',  'g': 'R3',  'b': 'R1',  'dcs': True},
        },
        'left': {
            'RGB': {'r': 'L0R', 'g': 'L0G', 'b': 'L0B', 'dcs': False},
            'DCS': {'r': 'L2',  'g': 'L5',  'b': 'L6',  'dcs': True},
        },
    },
    'PCAM': {
        'right': {
            'RGB': {'r': 'R7', 'g': 'R5', 'b': 'R3', 'dcs': False},
            'DCS': {'r': 'R7', 'g': 'R5', 'b': 'R3', 'dcs': True},
        },
        'left': {
            'RGB': {'r': 'L4', 'g': 'L5', 'b': 'L6', 'dcs': False},
            'DCS': {'r': 'L4', 'g': 'L5', 'b': 'L6', 'dcs': True},
        },
    },
}


class View(QWidget):
    """Main application view."""

    set_sam_path_signal         = pyqtSignal()
    open_folder_signal          = pyqtSignal()
    load_sel_signal             = pyqtSignal()
    export_sel_signal           = pyqtSignal()
    export_context_signal       = pyqtSignal()
    run_algorithm_signal        = pyqtSignal()
    scene_dropped_signal        = pyqtSignal(str)
    scene_double_clicked_signal = pyqtSignal(str)
    apply_stretch_mode_signal   = pyqtSignal(str)
    delete_all_rois_signal      = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.selected_scene_id    = None
        self.scene_thumbnails     = {}
        self.pixel_hover_callback = None
        self._preset_actions      = []
        self._mode                = 'scene_loading'
        self.init_ui()
        Scale.changed.connect(self._apply_scale)

    def init_ui(self):
        self.setWindowTitle('ROIStudio')
        self.resize(_DEFAULT_WINDOW_WIDTH, _DEFAULT_WINDOW_HEIGHT)

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)

        self._create_menu_bar()
        self._create_panels()
        self._setup_splitters()

    def _menu_stylesheet(self):
        fs = scaled_font(9)
        return f"""
            QMenuBar {{
                background-color: {Colors.PANEL_ACCENT};
                color: {Colors.TEXT_PRIMARY};
                border-bottom: 1px solid {Colors.PANEL_ACCENT};
                padding: {scaled(2)}px;
                font-size: {fs}pt;
            }}
            QMenuBar::item {{
                padding: {scaled(4)}px {scaled(12)}px;
                background: transparent;
                font-size: {fs}pt;
            }}
            QMenuBar::item:selected {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
            }}
            QMenu {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.PANEL_ACCENT};
                font-size: {fs}pt;
            }}
            QMenu::item {{
                padding: {scaled(4)}px {scaled(20)}px;
                font-size: {fs}pt;
            }}
            QMenu::item:selected {{
                background-color: {Colors.ACCENT};
            }}
            QMenu::item:disabled {{
                color: {Colors.TEXT_DISABLED};
            }}
            QMenu::indicator {{
                width: 0px;
                height: 0px;
            }}
            QMenu::item:checked {{
                color: {Colors.ACCENT};
            }}
            QMenu::item:checked:selected {{
                color: white;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {Colors.PANEL_ACCENT};
                margin-top: {scaled(4)}px;
            }}
        """

    def _create_menu_bar(self):
        self.menubar = QMenuBar()
        self.menubar.setGeometry(QRect(0, 0, _DEFAULT_WINDOW_WIDTH, scaled(25)))
        self.menubar.setStyleSheet(self._menu_stylesheet())
        self.layout.setMenuBar(self.menubar)

        self.menu_file = QMenu("File", self.menubar)
        self.menubar.addMenu(self.menu_file)

        self.action_set_sam_path = QAction("Set SAM Path", self)
        self.action_set_sam_path.triggered.connect(self.set_sam_path_signal.emit)
        self.menu_file.addAction(self.action_set_sam_path)

        self.action_open_folder = QAction("Open Folder", self)
        self.action_open_folder.triggered.connect(self.open_folder_signal.emit)
        self.menu_file.addAction(self.action_open_folder)

        self.menu_file.addSeparator()
        
        self.action_load_sel = QAction("Load sel", self)
        self.action_load_sel.triggered.connect(self.load_sel_signal.emit)
        self.action_load_sel.setEnabled(False)
        self.menu_file.addAction(self.action_load_sel)

        self.action_export_sel = QAction("Export sel", self)
        self.action_export_sel.triggered.connect(self.export_sel_signal.emit)
        self.action_export_sel.setEnabled(False)
        self.menu_file.addAction(self.action_export_sel)

        self.action_export_context = QAction("Export context", self)
        self.action_export_context.triggered.connect(self.export_context_signal.emit)
        self.action_export_context.setEnabled(False)
        self.menu_file.addAction(self.action_export_context)

        self.menu_view = QMenu("View", self.menubar)
        self.menubar.addMenu(self.menu_view)

        self.action_fit_canvas = QAction("Fit Canvas", self)
        self.menu_view.addAction(self.action_fit_canvas)

        self.action_roi_labels = QAction("ROI Labels", self)
        self.action_roi_labels.setCheckable(True)
        self.action_roi_labels.setChecked(False)
        self.menu_view.addAction(self.action_roi_labels)

        self.action_sync_views = QAction("Sync Views", self)
        self.action_sync_views.setCheckable(True)
        self.action_sync_views.setChecked(False)
        self.action_sync_views.setEnabled(False)
        self.action_sync_views.triggered.connect(self._on_sync_views_toggled)
        self.menu_view.addAction(self.action_sync_views)

        self.menu_view.addSeparator()
        self.action_delete_all_rois = QAction("Delete All ROIs", self)
        self.action_delete_all_rois.triggered.connect(self.delete_all_rois_signal.emit)
        self.action_delete_all_rois.setEnabled(False)
        self.menu_view.addAction(self.action_delete_all_rois)

        self.menu_view.addSeparator()
        for mode, label in (("RGB", "Set all RGB"), ("DCS", "Set all DCS")):
            action = QAction(label, self)
            action.triggered.connect(lambda checked, m=mode: self.apply_stretch_mode_signal.emit(m))
            action.setEnabled(False)
            self.menu_view.addAction(action)
            self._preset_actions.append((action, mode))

        self.menu_window = QMenu("Window", self.menubar)
        self.menubar.addMenu(self.menu_window)

        self.action_mode_scene = QAction("Scene Loading", self)
        self.action_mode_scene.setCheckable(True)
        self.action_mode_scene.setChecked(True)
        self.action_mode_scene.triggered.connect(lambda: self._set_mode('scene_loading'))
        self.menu_window.addAction(self.action_mode_scene)

        self.action_mode_roi = QAction("ROI Processing", self)
        self.action_mode_roi.setCheckable(True)
        self.action_mode_roi.setChecked(False)
        self.action_mode_roi.triggered.connect(lambda: self._set_mode('roi_processing'))
        self.menu_window.addAction(self.action_mode_roi)

    def set_instrument_presets(self, instrument: str):
        """Push instrument presets to the stretch bar overlays."""
        presets = INSTRUMENT_PRESETS.get(instrument, INSTRUMENT_PRESETS['ZCAM'])
        self.panel_image_editing.set_overlay_presets(presets)

    def _create_panels(self):
        self.panel_image_selection     = ImageSelectionPanel()
        self.panel_image_editing       = ImageEditingPanel()
        self.panel_spectral_view       = SpectralViewPanel()
        self.panel_status              = StatusPanel()
        self.panel_parameter_selection = ParameterSelectionPanel()

        self.panel_image_editing.run_algorithm_signal.connect(self.run_algorithm_signal.emit)
        self.panel_image_selection.scene_double_clicked.connect(self.scene_double_clicked_signal.emit)

        self.panel_parameter_selection.view_settings_changed.connect(
            self.panel_spectral_view.set_y_range
        )
        self.panel_parameter_selection.merge_spectra_changed.connect(
            self.panel_spectral_view.set_merge_spectra
        )
        self.panel_parameter_selection.line_width_changed.connect(
            self.panel_spectral_view.set_line_width
        )

        self.panel_image_editing.scene_dropped_signal.connect(self.scene_dropped_signal.emit)
        self.panel_image_editing.canvas_container.pixel_hovered.connect(self._on_pixel_hover)
        self.panel_image_editing.tool_changed_signal.connect(self._on_tool_changed)
        self.panel_image_editing.split_screen_toggled.connect(self._on_split_screen_toggled)

        self.action_roi_labels.triggered.connect(
            lambda checked: self.panel_image_editing.set_roi_labels_visible(checked)
        )
        self.action_fit_canvas.triggered.connect(self.panel_image_editing.fit_focused_canvas)

    def _splitter_stylesheet(self):
        return f"""
            QSplitter::handle {{
                background-color: {Colors.PANEL_ACCENT};
            }}
            QSplitter::handle:hover {{
                background-color: {Colors.ACCENT};
            }}
        """

    def _setup_splitters(self):
        style = self._splitter_stylesheet()

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(1)
        self.main_splitter.setStyleSheet(style)

        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.setHandleWidth(1)
        self.left_splitter.setStyleSheet(style)

        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.setHandleWidth(1)
        self.right_splitter.setStyleSheet(style)

        # Top slot switches between image selection and parameter panels via
        # a stacked widget - no size collapsing tricks needed.
        self.top_stack = QStackedWidget()
        self.top_stack.addWidget(self.panel_image_selection)   # index 0 - scene loading
        self.top_stack.addWidget(self.panel_parameter_selection)  # index 1 - roi processing

        self.left_splitter.addWidget(self.top_stack)
        self.left_splitter.addWidget(self.panel_spectral_view)
        self.left_splitter.setCollapsible(0, False)
        self.left_splitter.setCollapsible(1, False)

        self.right_splitter.addWidget(self.panel_image_editing)
        self.right_splitter.setCollapsible(0, False)

        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.right_splitter)

        h = _DEFAULT_WINDOW_HEIGHT
        w = _DEFAULT_WINDOW_WIDTH
        self.left_splitter.setSizes([int(h * 0.55), int(h * 0.45)])
        self.right_splitter.setSizes([h])
        self.main_splitter.setSizes([int(w * _MAIN_RATIO), int(w * (1 - _MAIN_RATIO))])

        self.layout.addWidget(self.main_splitter)
        self.layout.addWidget(self.panel_status)

    def _set_mode(self, mode: str):
        if mode == self._mode:
            return
        self._mode = mode
        self.action_mode_scene.setChecked(mode == 'scene_loading')
        self.action_mode_roi.setChecked(mode == 'roi_processing')
        self.top_stack.setCurrentIndex(0 if mode == 'scene_loading' else 1)

    def _apply_scale(self):
        self.menubar.setStyleSheet(self._menu_stylesheet())
        self.menubar.setGeometry(QRect(0, 0, self.width(), scaled(25)))

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_pixel_hover(self, x, y):
        if self.pixel_hover_callback:
            self.pixel_hover_callback(x, y)

    def _on_tool_changed(self, tool_name):
        if tool_name == "selection":
            self.panel_spectral_view.hide_preview()

    def _on_split_screen_toggled(self, is_split):
        self.action_sync_views.setChecked(False)
        self.action_sync_views.setEnabled(is_split)

    def _on_sync_views_toggled(self, checked: bool):
        self.panel_image_editing.set_sync_enabled(checked)

    def _scene_loaded(self):
        return any(action.isEnabled() for action, _ in self._preset_actions)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_export_enabled(self, enabled: bool):
        """Enable or disable both export actions together."""
        self.action_export_sel.setEnabled(enabled)
        self.action_export_context.setEnabled(enabled)
        self.action_delete_all_rois.setEnabled(enabled)

    def enable_presets(self, enabled: bool):
        for action, _ in self._preset_actions:
            action.setEnabled(enabled)

    def start_loading(self):
        self.panel_image_editing.start_loading()

    def stop_loading(self):
        self.panel_image_editing.stop_loading()

    def show_status_message(self, message):
        self.panel_status.show_status_message(message)

    def add_scene_thumbnail(self, scene_id, pixmap, filename, complete=False, sort_key=None):
        self.panel_image_selection.add_thumbnail(scene_id, pixmap, filename, complete, sort_key)

    def clear_thumbnails(self):
        self.panel_image_selection.clear_thumbnails()

    def select_scene(self, scene_id):
        self.panel_image_selection.select_scene(scene_id)