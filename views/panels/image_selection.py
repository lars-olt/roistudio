from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QScrollArea, QWidget, 
                             QGridLayout, QLabel)
from PyQt5.QtGui import QPixmap

from colors import Colors
from ..widgets import ClickableLabel


class ImageSelectionPanel(QFrame):
    """Panel for scene thumbnail selection."""
    
    resized = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.scene_thumbnails = {}
        self.thumbnail_pixmaps = {}
        self.thumbnail_filenames = {}
        self.selected_scene_id = None
        self.init_ui()
    
    def init_ui(self):
        """Creates image selection panel."""
        self.setStyleSheet(f"background-color: {Colors.PANEL_BACKGROUND};")
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # RESTORED: Legacy scroll bar styling
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {Colors.PANEL_BACKGROUND};
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {Colors.DEFAULT_FEATURE};
                width: 12px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
                min-height: 20px;
                border-radius: 6px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {Colors.PANEL_ACCENT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background-color: {Colors.DEFAULT_FEATURE};
                height: 12px;
                margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
                min-width: 20px;
                border-radius: 6px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {Colors.PANEL_ACCENT};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """)
        
        scroll_widget = QWidget()
        self.thumbnail_layout = QGridLayout()
        self.thumbnail_layout.setSpacing(10)
        self.thumbnail_layout.setContentsMargins(10, 10, 10, 10)
        scroll_widget.setLayout(self.thumbnail_layout)
        
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)
        
        self.resized.connect(self.update_thumbnail_sizes)
    
    def resizeEvent(self, event):
        """Emits signal when panel resized."""
        super().resizeEvent(event)
        self.resized.emit()
    
    def add_thumbnail(self, scene_id, pixmap, filename):
        """Adds thumbnail to grid."""
        self.thumbnail_pixmaps[scene_id] = pixmap
        self.thumbnail_filenames[scene_id] = filename
        
        thumb_size = self.calculate_thumbnail_size()
        cols = self.calculate_column_count()
        label_height = 45
        
        thumb_widget = QWidget()
        thumb_widget.setProperty("scene_id", scene_id)
        thumb_widget.setFixedSize(thumb_size, thumb_size + label_height + 5)
        thumb_layout = QVBoxLayout()
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(5)
        thumb_widget.setLayout(thumb_layout)
        
        thumb_label = ClickableLabel()
        scaled_pixmap = pixmap.scaled(
            thumb_size, thumb_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        thumb_label.setPixmap(scaled_pixmap)
        thumb_label.setFixedSize(thumb_size, thumb_size)
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setStyleSheet(f"""
            QLabel {{
                background-color: {Colors.DEFAULT_FEATURE};
                border: 2px solid {Colors.PANEL_ACCENT};
            }}
        """)
        thumb_label.clicked.connect(lambda sid=scene_id: self.select_scene(sid))
        thumb_label.set_scene_data(scene_id, scaled_pixmap)
        thumb_layout.addWidget(thumb_label)
        
        name_label = QLabel(filename)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setFixedWidth(thumb_size)
        name_label.setMaximumHeight(label_height)
        name_label.setSizePolicy(name_label.sizePolicy().Fixed,
                                 name_label.sizePolicy().Minimum)
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 8pt;
            }}
        """)
        thumb_layout.addWidget(name_label)
        
        self.scene_thumbnails[scene_id] = thumb_label
        
        num_items = len(self.scene_thumbnails)
        col = (num_items - 1) % cols
        row = (num_items - 1) // cols
        self.thumbnail_layout.addWidget(thumb_widget, row, col, Qt.AlignTop)
    
    def calculate_thumbnail_size(self):
        """Calculates thumbnail size based on width."""
        available_width = self.width() - 40
        cols = self.calculate_column_count()
        spacing = 10 * (cols + 1)
        thumb_size = (available_width - spacing) // cols
        return max(180, min(400, thumb_size))
    
    def calculate_column_count(self):
        """Calculates number of columns."""
        available_width = self.width() - 40
        if available_width < 180:
            return 1
        elif available_width < 400:
            return 1
        else:
            return 2
    
    def update_thumbnail_sizes(self):
        """Updates all thumbnail sizes on resize."""
        if not hasattr(self, 'thumbnail_pixmaps') or not self.thumbnail_pixmaps:
            return
        
        thumb_size = self.calculate_thumbnail_size()
        cols = self.calculate_column_count()
        label_height = 45
        
        selected_scene = self.selected_scene_id
        
        for i in reversed(range(self.thumbnail_layout.count())):
            item = self.thumbnail_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)
        
        self.scene_thumbnails.clear()
        
        for idx, scene_id in enumerate(self.thumbnail_pixmaps.keys()):
            pixmap = self.thumbnail_pixmaps[scene_id]
            filename = self.thumbnail_filenames[scene_id]
            
            thumb_widget = QWidget()
            thumb_widget.setProperty("scene_id", scene_id)
            thumb_widget.setFixedSize(thumb_size, thumb_size + label_height + 5)
            thumb_layout = QVBoxLayout()
            thumb_layout.setContentsMargins(0, 0, 0, 0)
            thumb_layout.setSpacing(5)
            thumb_widget.setLayout(thumb_layout)
            
            thumb_label = ClickableLabel()
            scaled_pixmap = pixmap.scaled(
                thumb_size, thumb_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            thumb_label.setPixmap(scaled_pixmap)
            thumb_label.setFixedSize(thumb_size, thumb_size)
            thumb_label.setAlignment(Qt.AlignCenter)
            thumb_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {Colors.DEFAULT_FEATURE};
                    border: 2px solid {Colors.PANEL_ACCENT};
                }}
            """)
            thumb_label.clicked.connect(lambda sid=scene_id: self.select_scene(sid))
            thumb_label.set_scene_data(scene_id, scaled_pixmap)
            thumb_layout.addWidget(thumb_label)
            
            name_label = QLabel(filename)
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)
            name_label.setFixedWidth(thumb_size)
            name_label.setMaximumHeight(label_height)
            name_label.setSizePolicy(name_label.sizePolicy().Fixed,
                                     name_label.sizePolicy().Minimum)
            name_label.setStyleSheet(f"""
                QLabel {{
                    color: {Colors.TEXT_PRIMARY};
                    font-size: 8pt;
                }}
            """)
            thumb_layout.addWidget(name_label)
            
            self.scene_thumbnails[scene_id] = thumb_label
            
            col = idx % cols
            row = idx // cols
            self.thumbnail_layout.addWidget(thumb_widget, row, col, Qt.AlignTop)
        
        if selected_scene:
            self.select_scene(selected_scene)
    
    def select_scene(self, scene_id):
        """Selects and highlights scene."""
        for sid, label in self.scene_thumbnails.items():
            if sid == scene_id:
                label.setStyleSheet(f"""
                    QLabel {{
                        background-color: {Colors.DEFAULT_FEATURE};
                        border: 2px solid {Colors.ACCENT};
                    }}
                """)
            else:
                label.setStyleSheet(f"""
                    QLabel {{
                        background-color: {Colors.DEFAULT_FEATURE};
                        border: 2px solid {Colors.PANEL_ACCENT};
                    }}
                """)
        
        self.selected_scene_id = scene_id
    
    def get_selected_scene(self):
        """Returns currently selected scene ID."""
        return self.selected_scene_id
    
    def clear_thumbnails(self):
        """Clears all thumbnails."""
        for i in reversed(range(self.thumbnail_layout.count())):
            self.thumbnail_layout.itemAt(i).widget().setParent(None)
        
        self.scene_thumbnails.clear()
        self.thumbnail_pixmaps.clear()
        self.thumbnail_filenames.clear()
        self.selected_scene_id = None