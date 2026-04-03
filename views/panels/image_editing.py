from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton)

from colors import Colors
from utils.paths import _resource_path
from ..canvas import DualCanvasContainer
from ..widgets import ToolbarButton


class ImageEditingPanel(QWidget):
    """Panel for image editing with canvas and toolbar."""

    run_algorithm_signal = pyqtSignal()
    scene_dropped_signal = pyqtSignal(str)
    spectral_preview_signal = pyqtSignal(int, int)
    tool_changed_signal = pyqtSignal(str)

    roi_changed = pyqtSignal(int, tuple, str)
    roi_deleted = pyqtSignal(int)
    roi_created = pyqtSignal(tuple, str)

    split_screen_toggled = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.current_tool = "selection"
        self.init_ui()
        self.canvas_container.installEventFilter(self)

    def init_ui(self):
        """Creates image editing panel layout."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

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
            QPushButton:hover {{
                background-color: {Colors.ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {Colors.ACCENT_PRESSED};
            }}
        """)
        self.run_button.clicked.connect(self.on_run_clicked)
        top_bar_layout.addWidget(self.run_button)
        top_bar_layout.addStretch()
        layout.addWidget(top_bar)

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
        self.update_cursor()

    def select_tool(self, tool_name):
        """Selects tool and updates UI."""
        self.current_tool = tool_name
        self.btn_selection.set_selected(tool_name == "selection")
        self.btn_rectangle.set_selected(tool_name == "rectangle")
        self.canvas_container.set_tool(tool_name)
        self.canvas_container.set_hover_preview_enabled(tool_name == "rectangle")
        self.tool_changed_signal.emit(tool_name)
        self.update_cursor()

    def update_cursor(self):
        """Updates canvas cursor based on tool."""
        if self.current_tool == "selection":
            from PyQt5.QtGui import QCursor, QPixmap
            cursor_pixmap = QPixmap(_resource_path("graphics/selection.png"))
            cursor = QCursor(cursor_pixmap, 0, 0)
            self.canvas_container.set_tool_cursor(cursor)
        elif self.current_tool == "rectangle":
            self.canvas_container.set_tool_cursor(Qt.CrossCursor)

    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    def on_run_clicked(self):
        self.run_algorithm_signal.emit()

    def toggle_split_screen(self):
        is_selected = not self.btn_split_screen.is_selected
        self.btn_split_screen.set_selected(is_selected)
        self.canvas_container.set_split_mode(is_selected)
        self.split_screen_toggled.emit(is_selected)

    def set_image(self, pixmap):
        self.canvas_container.set_image(pixmap)

    def set_rois(self, rois, colors=None):
        self.canvas_container.set_rois(rois, colors)