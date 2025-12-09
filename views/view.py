from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QMenuBar, QMenu, QAction, 
                             QSplitter, QHBoxLayout, QFrame)

from .panels import SpectralViewPanel, ImageSelectionPanel, ImageEditingPanel, StatusPanel, ParameterSelectionPanel
from .widgets import LoadingIndicator
from colors import Colors


class View(QWidget):
    """Main application view."""
    
    load_cube_signal = pyqtSignal()
    set_sam_path_signal = pyqtSignal()
    open_folder_signal = pyqtSignal()
    run_algorithm_signal = pyqtSignal(str, dict) # Updated to pass params
    scene_dropped_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.selected_scene_id = None
        self.scene_thumbnails = {}
        self.pixel_hover_callback = None
        self.init_ui()
    
    def init_ui(self):
        """Creates all visual components."""
        self.setWindowTitle('ROIStudio')
        self.resize(1600, 900)
        
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)
        
        self._create_menu_bar()
        self._create_panels()
        self._setup_splitters()
    
    def _create_menu_bar(self):
        """Creates menu bar with loading indicator."""
        self.menubar = QMenuBar()
        self.menubar.setGeometry(QRect(0, 0, 1600, 25))
        self.menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {Colors.PANEL_ACCENT};
                color: {Colors.TEXT_PRIMARY};
                border-bottom: 1px solid {Colors.PANEL_ACCENT};
                padding: 2px;
            }}
            QMenuBar::item {{
                padding: 4px 12px;
                background: transparent;
            }}
            QMenuBar::item:selected {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
            }}
            QMenu {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.PANEL_ACCENT};
            }}
            QMenu::item:selected {{
                background-color: {Colors.ACCENT};
            }}
        """)
        self.layout.setMenuBar(self.menubar)
        
        self.menu_file = QMenu("File", self.menubar)
        self.menubar.addMenu(self.menu_file)
        
        self.action_set_sam_path = QAction("Set SAM Path", self)
        self.action_set_sam_path.triggered.connect(self.set_sam_path_signal.emit)
        self.menu_file.addAction(self.action_set_sam_path)
        
        self.action_open_folder = QAction("Open Folder", self)
        self.action_open_folder.triggered.connect(self.open_folder_signal.emit)
        self.menu_file.addAction(self.action_open_folder)
        
        self.menu_edit = QMenu("Edit", self.menubar)
        self.menubar.addMenu(self.menu_edit)
        
        self.menu_window = QMenu("Window", self.menubar)
        self.menubar.addMenu(self.menu_window)
        
        corner_widget = QWidget()
        corner_layout = QHBoxLayout()
        corner_layout.setContentsMargins(0, 0, 8, 0)
        corner_layout.setSpacing(0)
        corner_widget.setLayout(corner_layout)
        corner_widget.setStyleSheet("background-color: transparent;")
        
        self.loading_indicator = LoadingIndicator(corner_widget)
        corner_layout.addWidget(self.loading_indicator)
        
        self.menubar.setCornerWidget(corner_widget, Qt.TopRightCorner)
    
    def _create_panels(self):
        """Creates all panel widgets."""
        self.panel_image_selection = ImageSelectionPanel()
        self.panel_image_editing = ImageEditingPanel()
        self.panel_spectral_view = SpectralViewPanel()
        self.panel_status = StatusPanel()
        self.panel_parameter_selection = ParameterSelectionPanel()
        
        # Connect internal signals
        # 1. Image editing run button -> View logic (receives algorithm name)
        self.panel_image_editing.run_algorithm_signal.connect(self._on_run_clicked)
        
        # 2. Parameter view settings -> Spectral view update
        self.panel_parameter_selection.view_settings_changed.connect(
            self.panel_spectral_view.set_y_range
        )
        
        self.panel_image_editing.scene_dropped_signal.connect(self.scene_dropped_signal.emit)
        self.panel_image_editing.canvas_container.pixel_hovered.connect(self._on_pixel_hover)
        self.panel_image_editing.tool_changed_signal.connect(self._on_tool_changed)
    
    def _on_run_clicked(self, algorithm_name):
        """Collects params and emits run signal."""
        # Get params from the parameter panel
        params = self.panel_parameter_selection.get_parameters()
        # Emit complete signal to controller
        self.run_algorithm_signal.emit(algorithm_name, params)

    def _setup_splitters(self):
        """Sets up splitter layout."""
        splitter_style = f"""
            QSplitter::handle {{
                background-color: {Colors.PANEL_ACCENT};
            }}
            QSplitter::handle:hover {{
                background-color: {Colors.ACCENT};
            }}
        """

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(1)
        self.main_splitter.setStyleSheet(splitter_style)
        
        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.setHandleWidth(1)
        self.left_splitter.setStyleSheet(splitter_style)

        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.setHandleWidth(1)
        self.right_splitter.setStyleSheet(splitter_style)
        
        self.left_splitter.addWidget(self.panel_image_selection)
        self.left_splitter.addWidget(self.panel_spectral_view)
        
        self.right_splitter.addWidget(self.panel_image_editing)
        self.right_splitter.addWidget(self.panel_parameter_selection)
        
        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.right_splitter)
        
        total_width = 1600
        self.main_splitter.setSizes([int(total_width * 0.35), int(total_width * 0.65)])
        
        self.layout.addWidget(self.main_splitter)
        self.layout.addWidget(self.panel_status)
    
    def _on_pixel_hover(self, x, y):
        """Forwards pixel hover to callback."""
        if self.pixel_hover_callback:
            self.pixel_hover_callback(x, y)
    
    def _on_tool_changed(self, tool_name):
        """Handles tool change events."""
        if tool_name == "selection":
            self.panel_spectral_view.hide_preview()
            
    def start_loading(self):
        """Shows loading indicator."""
        self.loading_indicator.start_loading()
    
    def stop_loading(self):
        """Hides loading indicator."""
        self.loading_indicator.stop_loading()
    
    def show_status_message(self, message):
        """Displays message in status panel."""
        self.panel_status.show_status_message(message)
    
    def add_scene_thumbnail(self, scene_id, pixmap, filename):
        """Adds thumbnail to selection panel."""
        self.panel_image_selection.add_thumbnail(scene_id, pixmap, filename)
    
    def clear_thumbnails(self):
        """Clears all thumbnails."""
        self.panel_image_selection.clear_thumbnails()
    
    def select_scene(self, scene_id):
        """Selects scene in thumbnail grid."""
        self.panel_image_selection.select_scene(scene_id)