from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QTextEdit

from colors import Colors
from utils.paths import _resource_path
from utils.scale import Scale, scaled, scaled_font


class StatusPanel(QWidget):
    """Status bar with logo and scrolling message log."""

    def __init__(self):
        super().__init__()
        self._build_ui()
        Scale.changed.connect(self._apply_scale)

    def _build_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.logo_label)

        self.status_bar = QTextEdit()
        self.status_bar.setReadOnly(True)
        self.status_bar.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.status_bar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.status_bar)

        self._apply_scale()

    def _apply_scale(self):
        self.setMaximumHeight(scaled(60))
        self.setStyleSheet(
            f"background-color: {Colors.DEFAULT_FEATURE}; "
            f"border-top: 1px solid {Colors.PANEL_ACCENT};"
        )

        icon_size   = scaled(32)
        logo_pixmap = QPixmap(_resource_path("graphics/logo/logo_500.png")).scaled(
            icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.logo_label.setPixmap(logo_pixmap)
        self.logo_label.setStyleSheet(f"padding: {scaled(8)}px;")

        self.status_bar.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Colors.DEFAULT_FEATURE};
                color: {Colors.TEXT_PRIMARY};
                border: none;
                font-family: Consolas, monospace;
                font-size: {scaled_font(10)}pt;
                padding: {scaled(5)}px;
            }}
        """)

    def show_status_message(self, message):
        self.status_bar.append(f"> {message}")
        self.status_bar.verticalScrollBar().setValue(
            self.status_bar.verticalScrollBar().maximum()
        )