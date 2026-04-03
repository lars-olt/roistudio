from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QSize, QPropertyAnimation, QParallelAnimationGroup
from PyQt5.QtWidgets import (QLabel, QPushButton, QWidget, QVBoxLayout,
                             QHBoxLayout, QFrame, QToolButton, QScrollArea, QSizePolicy)
from PyQt5.QtGui import QIcon, QMovie, QDrag
from PyQt5.QtCore import QMimeData

from colors import Colors
from utils.paths import _resource_path


class LoadingIndicator(QLabel):
    """Animated loading indicator for menu bar."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.movie = QMovie(_resource_path("graphics/load.gif"))
        self.setMovie(self.movie)

        self.setFixedSize(22, 30)
        self.setScaledContents(True)

        size_policy = self.sizePolicy()
        size_policy.setRetainSizeWhenHidden(True)
        self.setSizePolicy(size_policy)

        self.setStyleSheet("""
            QLabel {
                background-color: transparent;
                padding: 4px 0px;
                margin: 0px;
            }
        """)

        self.setVisible(False)

    def start_loading(self):
        """Shows and starts animation."""
        self.movie.start()
        self.setVisible(True)

    def stop_loading(self):
        """Stops and hides animation."""
        self.movie.stop()
        self.setVisible(False)


class ToolbarButton(QPushButton):
    """Custom toolbar button with state icons."""

    def __init__(self, normal_icon_path, selected_icon_path, parent=None):
        super().__init__(parent)
        self.normal_icon = QIcon(normal_icon_path)
        self.selected_icon = QIcon(selected_icon_path)
        self.is_selected = False

        self.setFixedSize(46, 38)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background-color: transparent;
            }}
        """)

        self.update_icon()

    def update_icon(self):
        """Updates icon based on state."""
        if self.is_selected or self.isChecked():
            self.setIcon(self.selected_icon)
        else:
            self.setIcon(self.normal_icon)
        self.setIconSize(QSize(46, 38))

    def set_selected(self, selected):
        """Sets selection state."""
        self.is_selected = selected
        self.setChecked(selected)
        self.update_icon()


class ClickableLabel(QLabel):
    """Label that emits clicked signal and supports drag."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene_id = None
        self.thumbnail_pixmap = None

    def mousePressEvent(self, event):
        """Handles mouse press."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            self.drag_start_pos = event.pos()

    def mouseMoveEvent(self, event):
        """Starts drag operation."""
        if not (event.buttons() & Qt.LeftButton):
            return

        if self.scene_id and self.thumbnail_pixmap:
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(self.scene_id)
            drag.setMimeData(mime_data)

            drag.setPixmap(self.thumbnail_pixmap)
            drag.setHotSpot(QPoint(self.thumbnail_pixmap.width() // 2,
                                   self.thumbnail_pixmap.height() // 2))

            drag.exec_(Qt.CopyAction)

    def set_scene_data(self, scene_id, pixmap):
        """Stores scene data for drag."""
        self.scene_id = scene_id
        self.thumbnail_pixmap = pixmap


class CollapsibleSection(QWidget):
    """Premiere Pro-style collapsible section."""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.toggle_button = QToolButton(text=title, checkable=True, checked=True)
        self.toggle_button.setStyleSheet(f"""
            QToolButton {{
                border: none;
                color: {Colors.TEXT_PRIMARY};
                background-color: {Colors.PANEL_BACKGROUND};
                text-align: left;
                font-weight: bold;
                padding: 5px;
            }}
            QToolButton:hover {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
            }}
        """)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.pressed.connect(self.on_pressed)

        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.content_area = QWidget()
        self.content_area.setVisible(True)
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(10, 0, 0, 10)
        self.content_layout.setSpacing(5)
        self.content_area.setLayout(self.content_layout)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content_area)

    def on_pressed(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(Qt.DownArrow if not checked else Qt.RightArrow)
        self.content_area.setVisible(not checked)

    def set_content_layout(self, layout):
        self.content_area.setLayout(layout)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)