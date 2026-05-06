from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QMenuBar, QMenu, QAction,
                             QSplitter, QHBoxLayout, QFrame)

from .panels import SpectralViewPanel, ImageSelectionPanel, ImageEditingPanel, StatusPanel, ParameterSelectionPanel
from colors import Colors
from utils.scale import Scale, scaled, scaled_font


_DEFAULT_WINDOW_WIDTH  = 1600
_DEFAULT_WINDOW_HEIGHT = 900

# Each preset targets a specific camera and band combination.
# Add new ZCAM presets here, or define a _PCAM_PRESETS list for Pancam support.
_ZCAM_PRESETS = [
    {'label': 'Right RGB',    'camera': 'right', 'r': 'R0R', 'g': 'R0G', 'b': 'R0B', 'dcs': False},
    {'label': 'Left RGB',     'camera': 'left',  'r': 'L0R', 'g': 'L0G', 'b': 'L0B', 'dcs': False},
    {'label': 'R6 R3 R1 DCS', 'camera': 'right', 'r': 'R6',  'g': 'R3',  'b': 'R1',  'dcs': True},
    {'label': 'L2 L5 L6 DCS', 'camera': 'left',  'r': 'L2',  'g': 'L5',  'b': 'L6',  'dcs': True},
]


class View(QWidget):
    """Main application view."""

    load_cube_signal            = pyqtSignal()
    set_sam_path_signal         = pyqtSignal()
    open_folder_signal          = pyqtSignal()
    export_sel_signal           = pyqtSignal()
    run_algorithm_signal        = pyqtSignal()
    scene_dropped_signal        = pyqtSignal(str)
    scene_double_clicked_signal = pyqtSignal(str)
    apply_preset_signal         = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.selected_scene_id    = None
        self.scene_thumbnails     = {}
        self.pixel_hover_callback = None
        self._preset_actions      = []
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
        """

    def _create_menu_bar(self):
        self.menubar = QMenuBar()
        self.menubar.setGeometry(QRect(0, 0, 1600, scaled(25)))
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

        self.action_export_sel = QAction("Export sel", self)
        self.action_export_sel.triggered.connect(self.export_sel_signal.emit)
        self.action_export_sel.setEnabled(False)
        self.menu_file.addAction(self.action_export_sel)

        self.menu_view   = QMenu("View",   self.menubar)
        self.menu_window = QMenu("Window", self.menubar)
        self.menubar.addMenu(self.menu_view)
        self.menubar.addMenu(self.menu_window)

        self.action_fit_image = QAction("Fit Image", self)
        self.action_fit_image.setEnabled(False)
        self.menu_view.addAction(self.action_fit_image)

        # self.menu_view.addSeparator()
        self.menu_view.addSection("Scale")
        for preset in _ZCAM_PRESETS:
            action = QAction(preset['label'], self)
            action.triggered.connect(lambda checked, p=preset: self.apply_preset_signal.emit(p))
            action.setEnabled(False)
            self.menu_view.addAction(action)
            self._preset_actions.append((action, preset))

    def _create_panels(self):
        self.panel_image_selection    = ImageSelectionPanel()
        self.panel_image_editing      = ImageEditingPanel()
        self.panel_spectral_view      = SpectralViewPanel()
        self.panel_status             = StatusPanel()
        self.panel_parameter_selection = ParameterSelectionPanel()

        self.panel_image_editing.run_algorithm_signal.connect(self.run_algorithm_signal.emit)
        self.panel_image_selection.scene_double_clicked.connect(self.scene_double_clicked_signal.emit)

        self.panel_parameter_selection.view_settings_changed.connect(
            self.panel_spectral_view.set_y_range
        )
        self.panel_parameter_selection.merge_spectra_changed.connect(
            self.panel_spectral_view.set_merge_spectra
        )

        self.panel_image_editing.scene_dropped_signal.connect(self.scene_dropped_signal.emit)
        self.panel_image_editing.canvas_container.pixel_hovered.connect(self._on_pixel_hover)
        self.panel_image_editing.tool_changed_signal.connect(self._on_tool_changed)
        self.panel_image_editing.split_screen_toggled.connect(self._on_split_screen_toggled)
        self.action_fit_image.triggered.connect(self.panel_image_editing.fit_focused_canvas)

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

        self.left_splitter.addWidget(self.panel_image_selection)
        self.left_splitter.addWidget(self.panel_spectral_view)
        self.left_splitter.setSizes([int(_DEFAULT_WINDOW_HEIGHT * 0.55), int(_DEFAULT_WINDOW_HEIGHT * 0.45)])

        self.right_splitter.addWidget(self.panel_image_editing)
        self.right_splitter.addWidget(self.panel_parameter_selection)
        self.right_splitter.setSizes([int(_DEFAULT_WINDOW_HEIGHT * 0.7), int(_DEFAULT_WINDOW_HEIGHT * 0.3)])

        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setSizes([int(_DEFAULT_WINDOW_WIDTH * 0.35), int(_DEFAULT_WINDOW_WIDTH * 0.65)])

        self.layout.addWidget(self.main_splitter)
        self.layout.addWidget(self.panel_status)

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
        """Enable/disable left-camera presets based on split mode."""
        for action, preset in self._preset_actions:
            if preset['camera'] == 'left':
                action.setEnabled(is_split and self._scene_loaded())

    def _scene_loaded(self):
        return any(action.isEnabled() for action, p in self._preset_actions
                   if p['camera'] == 'right')

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def enable_presets(self, enabled: bool):
        self.action_fit_image.setEnabled(enabled)
        is_split = self.panel_image_editing._is_split
        for action, preset in self._preset_actions:
            camera = preset['camera']
            action.setEnabled(enabled and (camera == 'right' or (camera == 'left' and is_split)))

    def start_loading(self):
        self.panel_image_editing.start_loading()

    def stop_loading(self):
        self.panel_image_editing.stop_loading()

    def show_status_message(self, message):
        self.panel_status.show_status_message(message)

    def add_scene_thumbnail(self, scene_id, pixmap, filename):
        self.panel_image_selection.add_thumbnail(scene_id, pixmap, filename)

    def clear_thumbnails(self):
        self.panel_image_selection.clear_thumbnails()

    def select_scene(self, scene_id):
        self.panel_image_selection.select_scene(scene_id)