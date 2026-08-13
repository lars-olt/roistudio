from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QMenuBar, QMenu,
                             QAction, QSplitter, QStackedWidget)

from .panels import (SpectralViewPanel, ImageSelectionPanel, ImageEditingPanel,
                     StatusPanel, SettingsPanel, ROIMetadataPanel)
from colors import Colors
from presets import INSTRUMENT_PRESETS
from utils.scale import Scale, scaled, scaled_font


_DEFAULT_WINDOW_WIDTH  = 1600
_DEFAULT_WINDOW_HEIGHT = 900

_MAIN_RATIO = 0.35



class View(QWidget):
    """Main application view."""

    set_sam_path_signal         = pyqtSignal()
    open_folder_signal          = pyqtSignal()
    load_sel_signal             = pyqtSignal()
    load_fits_signal            = pyqtSignal()
    export_sel_signal           = pyqtSignal()
    export_context_signal       = pyqtSignal()
    export_fits_signal          = pyqtSignal()
    run_algorithm_signal        = pyqtSignal()
    scene_dropped_signal        = pyqtSignal(str)
    scene_double_clicked_signal = pyqtSignal(str)
    apply_stretch_mode_signal   = pyqtSignal(str)
    delete_all_rois_signal      = pyqtSignal()
    mode_changed                = pyqtSignal(str)

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

        self.action_load_fits = QAction("Load FITS", self)
        self.action_load_fits.triggered.connect(self.load_fits_signal.emit)
        self.action_load_fits.setEnabled(False)
        self.menu_file.addAction(self.action_load_fits)

        self.action_export_sel = QAction("Export sel", self)
        self.action_export_sel.triggered.connect(self.export_sel_signal.emit)
        self.action_export_sel.setEnabled(False)
        self.menu_file.addAction(self.action_export_sel)

        self.action_export_context = QAction("Export context", self)
        self.action_export_context.triggered.connect(self.export_context_signal.emit)
        self.action_export_context.setEnabled(False)
        self.menu_file.addAction(self.action_export_context)

        self.action_export_fits = QAction("Export FITS", self)
        self.action_export_fits.triggered.connect(self.export_fits_signal.emit)
        self.action_export_fits.setEnabled(False)
        self.menu_file.addAction(self.action_export_fits)

        self.menu_view = QMenu("View", self.menubar)
        self.menubar.addMenu(self.menu_view)

        self.action_fit_canvas = QAction("Fit Canvas", self)
        self.menu_view.addAction(self.action_fit_canvas)

        self.action_roi_labels = QAction("ROI Labels", self)
        self.action_roi_labels.setCheckable(True)
        self.action_roi_labels.setChecked(False)
        self.action_roi_labels.setShortcut("L")
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
        for mode, label, shortcut in (
            ("RGB", "Set all RGB", "C"),
            ("DCS", "Set all DCS", "D"),
        ):
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.triggered.connect(lambda checked, m=mode: self.apply_stretch_mode_signal.emit(m))
            action.setEnabled(False)
            self.menu_view.addAction(action)
            self._preset_actions.append((action, mode))

        self.menu_window = QMenu("Window", self.menubar)
        self.menubar.addMenu(self.menu_window)

        self.action_mode_scene = QAction("Scene Loading", self)
        self.action_mode_scene.setCheckable(True)
        self.action_mode_scene.setChecked(True)
        self.action_mode_scene.setShortcut("1")
        self.action_mode_scene.triggered.connect(lambda: self.set_mode('scene_loading'))
        self.menu_window.addAction(self.action_mode_scene)

        self.action_mode_settings = QAction("Settings", self)
        self.action_mode_settings.setCheckable(True)
        self.action_mode_settings.setChecked(False)
        self.action_mode_settings.setShortcut("2")
        self.action_mode_settings.triggered.connect(lambda: self.set_mode('settings'))
        self.menu_window.addAction(self.action_mode_settings)

        self.action_mode_metadata = QAction("ROI Metadata", self)
        self.action_mode_metadata.setCheckable(True)
        self.action_mode_metadata.setChecked(False)
        self.action_mode_metadata.setShortcut("3")
        self.action_mode_metadata.triggered.connect(lambda: self.set_mode('roi_metadata'))
        self.menu_window.addAction(self.action_mode_metadata)

        self.menu_window.addSeparator()
        self.action_zoom_context = QAction("Zoom Context", self)
        self.action_zoom_context.setCheckable(True)
        self.action_zoom_context.setChecked(True)
        self.action_zoom_context.setShortcut("Z")
        self.menu_window.addAction(self.action_zoom_context)

    def set_instrument_presets(self, instrument: str):
        """Push instrument presets to the stretch bar overlays."""
        presets = INSTRUMENT_PRESETS.get(instrument, INSTRUMENT_PRESETS['ZCAM'])
        single_side = 'left' if instrument == 'PCAM' else 'right'
        self.panel_image_editing.set_overlay_presets(
            presets, single_side=single_side
        )

    def _create_panels(self):
        self.panel_image_selection     = ImageSelectionPanel()
        self.panel_image_editing       = ImageEditingPanel()
        self.panel_spectral_view       = SpectralViewPanel()
        self.panel_status              = StatusPanel()
        self.panel_settings            = SettingsPanel()
        self.panel_roi_metadata        = ROIMetadataPanel()

        self.panel_image_editing.run_algorithm_signal.connect(self.run_algorithm_signal.emit)
        self.panel_image_selection.scene_double_clicked.connect(self.scene_double_clicked_signal.emit)

        self.panel_settings.view_settings_changed.connect(
            self.panel_spectral_view.set_y_range
        )
        self.panel_settings.merge_spectra_changed.connect(
            self.panel_spectral_view.set_merge_spectra
        )
        self.panel_settings.line_width_changed.connect(
            self.panel_spectral_view.set_line_width
        )

        self.panel_image_editing.scene_dropped_signal.connect(self.scene_dropped_signal.emit)
        self.panel_image_editing.canvas_container.pixel_hovered.connect(self._on_pixel_hover)
        self.panel_image_editing.tool_changed_signal.connect(self._on_tool_changed)
        self.panel_image_editing.split_screen_toggled.connect(self._on_split_screen_toggled)

        self.action_roi_labels.triggered.connect(self.set_roi_labels_visible)
        self.action_zoom_context.triggered.connect(self.set_zoom_context_visible)
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

        # Top slot switches between panels via a stacked widget - indices match _MODES.
        self.top_stack = QStackedWidget()
        self.top_stack.addWidget(self.panel_image_selection)      # scene loading
        self.top_stack.addWidget(self.panel_settings)             # settings
        self.top_stack.addWidget(self.panel_roi_metadata)         # roi metadata

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

    _MODES = {'scene_loading': 0, 'settings': 1, 'roi_metadata': 2}

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str):
        # Migrate UI state saved before ROI Processing became application Settings.
        if mode == 'roi_processing':
            mode = 'settings'
        if mode not in self._MODES:
            return
        if mode == self._mode:
            return
        self._mode = mode
        self.action_mode_scene.setChecked(mode == 'scene_loading')
        self.action_mode_settings.setChecked(mode == 'settings')
        self.action_mode_metadata.setChecked(mode == 'roi_metadata')
        self.top_stack.setCurrentIndex(self._MODES[mode])
        self.mode_changed.emit(mode)

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
        """Enable or disable all export actions together."""
        self.action_export_sel.setEnabled(enabled)
        self.action_export_context.setEnabled(enabled)
        self.action_export_fits.setEnabled(enabled)
        self.action_delete_all_rois.setEnabled(enabled)

    def enable_presets(self, enabled: bool):
        for action, _ in self._preset_actions:
            action.setEnabled(enabled)

    def set_roi_labels_visible(self, visible: bool):
        self.action_roi_labels.setChecked(visible)
        self.panel_image_editing.set_roi_labels_visible(visible)

    def set_zoom_context_visible(self, visible: bool):
        self.action_zoom_context.setChecked(visible)
        self.panel_image_editing.set_zoom_context_visible(visible)

    def set_panel_ratios(self, *, left=None, upper=None):
        """Set relative splitter positions using values between zero and one."""
        if left is not None:
            self.main_splitter.setSizes([
                round(float(left) * 1000),
                round((1.0 - float(left)) * 1000),
            ])
        if upper is not None:
            self.left_splitter.setSizes([
                round(float(upper) * 1000),
                round((1.0 - float(upper)) * 1000),
            ])

    def ensure_visible_on_screen(self):
        """Move a restored window onto the primary screen if its old monitor is gone."""
        if any(screen.availableGeometry().intersects(self.frameGeometry())
               for screen in QApplication.screens()):
            return
        available = QApplication.primaryScreen().availableGeometry()
        self.move(available.center() - self.rect().center())

    def start_loading(self):
        self.panel_image_editing.start_loading()

    def stop_loading(self):
        self.panel_image_editing.stop_loading()

    def show_status_message(self, message):
        self.panel_status.show_status_message(message)

    def set_science_notes(self, notes: str):
        self.panel_status.set_science_notes(notes)

    def add_scene_thumbnail(self, scene_id, pixmap, filename, complete=False, sort_key=None):
        self.panel_image_selection.add_thumbnail(scene_id, pixmap, filename, complete, sort_key)

    def clear_thumbnails(self):
        self.panel_image_selection.clear_thumbnails()

    def select_scene(self, scene_id):
        self.panel_image_selection.select_scene(scene_id)
