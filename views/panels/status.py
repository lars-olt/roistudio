from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QLabel, QTextEdit,
                             QFrame, QSizePolicy)

from colors import Colors
from utils.paths import _resource_path
from utils.scale import Scale, scaled, scaled_font


class _ScienceNotes(QLabel):
    """Persistent observation note that elides before crowding status text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def minimumSizeHint(self):
        return QSize(scaled(30), super().minimumSizeHint().height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.width())
        painter.drawText(self.rect(), int(self.alignment()), text)


class StatusPanel(QWidget):
    """Status bar with message history and scene notes."""

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
        layout.addWidget(self.status_bar, 1)

        self.notes_container = QWidget()
        self.notes_layout = QHBoxLayout()
        self.notes_layout.setContentsMargins(0, 0, 0, 0)
        self.notes_container.setLayout(self.notes_layout)

        self.notes_divider = QFrame()
        self.notes_divider.setFrameShape(QFrame.VLine)
        self.notes_divider.setFrameShadow(QFrame.Plain)
        self.notes_layout.addWidget(self.notes_divider)

        self.science_notes = _ScienceNotes()
        self.science_notes.setAccessibleName("Observation notes")
        self.notes_layout.addWidget(self.science_notes, 1)
        self.notes_container.hide()
        layout.addWidget(self.notes_container)

        self._apply_scale()

    def _apply_scale(self):
        self.setMaximumHeight(scaled(60))
        self.setObjectName("statusPanel")
        self.setStyleSheet(f"""
            QWidget#statusPanel {{
                background-color: {Colors.DEFAULT_FEATURE};
                border-top: 1px solid {Colors.PANEL_ACCENT};
            }}
        """)

        icon_size   = scaled(32)
        pixmap      = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.transparent)
        from PyQt5.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(_resource_path("graphics/mcz_logo.svg"))
        painter  = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.end()
        self.logo_label.setPixmap(pixmap)
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

        self.notes_layout.setSpacing(scaled(8))
        self.notes_layout.setContentsMargins(scaled(6), 0, scaled(10), 0)
        self.notes_container.setStyleSheet("background: transparent; border: none;")
        self.notes_divider.setStyleSheet(
            f"QFrame {{ color: {Colors.PANEL_ACCENT}; border: none; "
            f"border-left: 1px solid {Colors.PANEL_ACCENT}; }}"
        )
        self.science_notes.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; border: none; "
            f"font-size: {scaled_font(9)}pt; font-style: italic;"
        )
        self._update_notes_width()

    def _update_notes_width(self):
        target = min(scaled(420), max(scaled(120), round(self.width() * 0.35)))
        self.notes_container.setFixedWidth(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_notes_width()

    def show_status_message(self, message):
        self.status_bar.append(f"> {message}")
        self.status_bar.verticalScrollBar().setValue(
            self.status_bar.verticalScrollBar().maximum()
        )

    def set_science_notes(self, notes: str):
        notes = ' '.join((notes or '').split())
        self.science_notes.setText(notes)
        self.science_notes.setToolTip(notes)
        self.notes_container.setVisible(bool(notes))
        self._update_notes_width()
