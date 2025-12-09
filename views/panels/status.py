from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QTextEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from colors import Colors


class StatusPanel(QWidget):
    """Panel for status messages and logo."""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """Creates status panel with logo and log."""
        self.setMaximumHeight(60)
        self.setStyleSheet(f"background-color: {Colors.DEFAULT_FEATURE}; border-top: 1px solid {Colors.PANEL_ACCENT};")
        
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        
        logo_label = QLabel()
        logo_pixmap = QPixmap("graphics/mcz_logo.png")
        logo_pixmap = logo_pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("padding: 8px;")
        layout.addWidget(logo_label)
        
        self.status_bar = QTextEdit()
        self.status_bar.setReadOnly(True)
        # ADDED: Hide scroll bars
        self.status_bar.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.status_bar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.status_bar.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Colors.DEFAULT_FEATURE};
                color: {Colors.TEXT_PRIMARY};
                border: none;
                font-family: Consolas, monospace;
                font-size: 10pt;
                padding: 5px;
            }}
        """)
        layout.addWidget(self.status_bar)
    
    def show_status_message(self, message):
        """Displays message in status bar."""
        self.status_bar.append(f"> {message}")
        self.status_bar.verticalScrollBar().setValue(
            self.status_bar.verticalScrollBar().maximum()
        )