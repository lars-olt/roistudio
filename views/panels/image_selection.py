from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QScrollArea, QWidget,
                             QGridLayout, QLabel)

from colors import Colors
from utils.scale import Scale, physical, scaled, scaled_font
from ..widgets import ClickableLabel


_THUMB_BASE = 250   # reference thumbnail size in logical pixels
_SPACING    = 10    # gap between thumbnails in reference pixels


class ImageSelectionPanel(QFrame):
    """Scrollable grid of scene thumbnails."""

    scene_double_clicked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.scene_thumbnails    = {}
        self.thumbnail_pixmaps   = {}
        self.thumbnail_filenames = {}
        self.selected_scene_id   = None
        self._current_cols       = 0
        self._build_ui()
        Scale.changed.connect(self._on_scale_changed)

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {Colors.PANEL_BACKGROUND};")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll_area)

        scroll_widget = QWidget()
        self.thumbnail_layout = QGridLayout()
        self.thumbnail_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        scroll_widget.setLayout(self.thumbnail_layout)
        self.scroll_area.setWidget(scroll_widget)

        self._apply_scroll_style()

    def _apply_scroll_style(self):
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{ background-color: {Colors.PANEL_BACKGROUND}; border: none; }}
            QScrollBar:vertical {{
                background-color: {Colors.DEFAULT_FEATURE};
                width: {scaled(12)}px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
                min-height: {scaled(20)}px;
                border-radius: {scaled(6)}px; margin: {scaled(2)}px;
            }}
            QScrollBar::handle:vertical:hover {{ background-color: {Colors.PANEL_ACCENT}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

    def _on_scale_changed(self):
        self._apply_scroll_style()
        self._current_cols = 0
        self._rebuild_grid()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        params = self._layout_params()
        if params is None:
            return
        cols, _, _ = params
        if cols != self._current_cols:
            self._current_cols = cols
            self._rebuild_grid()

    # ------------------------------------------------------------------
    # Layout geometry
    # ------------------------------------------------------------------

    def _layout_params(self):
        """Return (cols, thumb_px, spacing_px), or None if viewport isn't ready."""
        thumb     = physical(_THUMB_BASE)
        spacing   = scaled(_SPACING)
        sb_w      = self.scroll_area.verticalScrollBar().sizeHint().width()
        available = self.scroll_area.viewport().width() - sb_w
        if available < thumb:
            return None
        cols = max(1, (available + spacing) // (thumb + spacing))
        return cols, thumb, spacing

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _thumb_style(self, selected=False):
        border = Colors.ACCENT if selected else Colors.PANEL_ACCENT
        return f"QLabel {{ background-color: {Colors.DEFAULT_FEATURE}; border: 1px solid {border}; }}"

    def _name_style(self):
        return f"QLabel {{ color: {Colors.TEXT_PRIMARY}; font-size: {scaled_font(9)}pt; }}"

    def _build_thumb_widget(self, scene_id, pixmap, filename, thumb_size):
        label_h = scaled(40)

        container = QWidget()
        container.setFixedSize(thumb_size, thumb_size + label_h + scaled(4))

        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(scaled(4))
        container.setLayout(v)

        thumb_label = ClickableLabel()
        scaled_pix  = pixmap.scaled(thumb_size, thumb_size,
                                    Qt.KeepAspectRatio, Qt.SmoothTransformation)
        thumb_label.setPixmap(scaled_pix)
        thumb_label.setFixedSize(thumb_size, thumb_size)
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setStyleSheet(self._thumb_style(selected=(scene_id == self.selected_scene_id)))
        thumb_label.clicked.connect(lambda sid=scene_id: self.select_scene(sid))
        thumb_label.double_clicked.connect(lambda sid=scene_id: self.scene_double_clicked.emit(sid))
        thumb_label.set_scene_data(scene_id, scaled_pix)
        v.addWidget(thumb_label)

        name_label = QLabel(filename)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setFixedWidth(thumb_size)
        name_label.setMaximumHeight(label_h)
        name_label.setStyleSheet(self._name_style())
        v.addWidget(name_label)

        return container, thumb_label

    # ------------------------------------------------------------------
    # Grid management
    # ------------------------------------------------------------------

    def add_thumbnail(self, scene_id, pixmap, filename):
        self.thumbnail_pixmaps[scene_id]   = pixmap
        self.thumbnail_filenames[scene_id] = filename
        self._rebuild_grid()

    def _rebuild_grid(self):
        if not self.thumbnail_pixmaps:
            return
        params = self._layout_params()
        if params is None:
            return
        cols, thumb_size, spacing = params
        self._current_cols = cols

        for i in reversed(range(self.thumbnail_layout.count())):
            item = self.thumbnail_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

        self.scene_thumbnails.clear()
        self.thumbnail_layout.setSpacing(spacing)
        self.thumbnail_layout.setContentsMargins(scaled(10), scaled(10), scaled(10), scaled(10))

        for idx, scene_id in enumerate(self.thumbnail_pixmaps):
            widget, label = self._build_thumb_widget(
                scene_id,
                self.thumbnail_pixmaps[scene_id],
                self.thumbnail_filenames[scene_id],
                thumb_size,
            )
            self.scene_thumbnails[scene_id] = label
            self.thumbnail_layout.addWidget(widget, idx // cols, idx % cols, Qt.AlignTop)

        if self.selected_scene_id:
            self.select_scene(self.selected_scene_id)

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select_scene(self, scene_id):
        for sid, label in self.scene_thumbnails.items():
            label.setStyleSheet(self._thumb_style(selected=(sid == scene_id)))
        self.selected_scene_id = scene_id

    def get_selected_scene(self):
        return self.selected_scene_id

    def clear_thumbnails(self):
        for i in reversed(range(self.thumbnail_layout.count())):
            item = self.thumbnail_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)
        self.scene_thumbnails.clear()
        self.thumbnail_pixmaps.clear()
        self.thumbnail_filenames.clear()
        self.selected_scene_id = None