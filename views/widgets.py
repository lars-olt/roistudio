from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QSize, QMimeData
from PyQt5.QtWidgets import (QLabel, QPushButton, QComboBox, QWidget,
                             QVBoxLayout, QGridLayout, QFrame, QToolButton,
                             QSizePolicy, QListView)
from PyQt5.QtGui import QIcon, QMovie, QPainter, QPen, QPixmap, QColor, QDrag

from colors import Colors
from utils.paths import _resource_path
from utils.scale import Scale, physical, scaled, scaled_font


class LoadingIndicator(QLabel):
    """Animated square GIF that retains its space when hidden."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.movie = QMovie(_resource_path("graphics/load.gif"))
        self.movie.frameChanged.connect(self._update_frame)
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(False)
        sp = self.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self.setSizePolicy(sp)
        self.setVisible(False)
        self._apply_scale()
        Scale.changed.connect(self._apply_scale)

    def _apply_scale(self):
        sz = physical(22)
        self.setFixedSize(sz, sz)
        self.movie.setScaledSize(QSize(sz, sz))
        self.setStyleSheet(
            "QLabel { background-color: transparent; border: none; padding: 0px; margin: 0px; }"
        )

    def _update_frame(self):
        sz     = self.width()
        pixmap = self.movie.currentPixmap().scaled(
            sz, sz, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(pixmap)

    def start_loading(self):
        self.movie.start()
        self.setVisible(True)

    def stop_loading(self):
        self.movie.stop()
        self.setVisible(False)


class ToolbarButton(QPushButton):
    """Toolbar button with normal, hover, and selected icon states."""

    def __init__(self, normal_icon_path, selected_icon_path, hover_icon_path=None, selected_hover_icon_path=None, parent=None):
        super().__init__(parent)
        if hover_icon_path is None:
            stem, ext       = normal_icon_path.rsplit('.', 1)
            hover_icon_path = f"{stem}_hover.{ext}"
        self._path_normal         = normal_icon_path
        self._path_selected       = selected_icon_path
        self._path_hover          = hover_icon_path
        self._path_selected_hover = selected_hover_icon_path
        self.is_selected = False
        self._hovered    = False
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton { border: none; background-color: transparent; "
            "padding: 0px; margin: 0px; }"
        )
        self._apply_scale()
        Scale.changed.connect(self._apply_scale)

    def _scaled_icon(self, path, w, h):
        """Render an SVG or PNG to a crisp QIcon at exactly (w, h) pixels."""
        pixmap = QPixmap(w, h)
        pixmap.fill(Qt.transparent)
        if path.lower().endswith('.svg'):
            try:
                from PyQt5.QtSvg import QSvgRenderer
                renderer = QSvgRenderer(path)
                painter  = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                renderer.render(painter)
                painter.end()
            except ImportError:
                pixmap = QPixmap(path).scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            pixmap = QPixmap(path).scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon = QIcon(pixmap)
        # prevent Qt from auto-graying the icon when the button is disabled
        icon.addPixmap(pixmap, QIcon.Disabled)
        return icon

    def _apply_scale(self):
        w, h = physical(46), physical(38)
        self.setFixedSize(w, h)
        self.setIconSize(QSize(w, h))
        self.normal_icon         = self._scaled_icon(self._path_normal,   w, h)
        self.selected_icon       = self._scaled_icon(self._path_selected, w, h)
        self.hover_icon          = self._scaled_icon(self._path_hover,    w, h)
        self.selected_hover_icon = (
            self._scaled_icon(self._path_selected_hover, w, h)
            if self._path_selected_hover else None
        )
        self.update_icon()

    def update_icon(self):
        selected = self.is_selected or self.isChecked()
        if self._hovered and selected and self.selected_hover_icon:
            self.setIcon(self.selected_hover_icon)
        elif self._hovered and not selected:
            self.setIcon(self.hover_icon)
        elif selected:
            self.setIcon(self.selected_icon)
        else:
            self.setIcon(self.normal_icon)

    def set_selected(self, selected):
        self.is_selected = selected
        self.setChecked(selected)
        self.update_icon()

    def changeEvent(self, event):
        super().changeEvent(event)
        from PyQt5.QtCore import QEvent
        if event.type() == QEvent.EnabledChange:
            self.setCursor(Qt.PointingHandCursor if self.isEnabled() else Qt.ArrowCursor)

    def enterEvent(self, event):
        self._hovered = True
        self.update_icon()

    def leaveEvent(self, event):
        self._hovered = False
        self.update_icon()


class ClickableLabel(QLabel):
    """Label that emits click signals and supports drag-and-drop."""

    clicked        = pyqtSignal()
    double_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene_id         = None
        self.thumbnail_pixmap = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if not (self.scene_id and self.thumbnail_pixmap):
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.scene_id)
        drag.setMimeData(mime)
        drag.setPixmap(self.thumbnail_pixmap)
        drag.setHotSpot(QPoint(self.thumbnail_pixmap.width() // 2,
                               self.thumbnail_pixmap.height() // 2))
        drag.exec_(Qt.CopyAction)

    def set_scene_data(self, scene_id, pixmap):
        self.scene_id         = scene_id
        self.thumbnail_pixmap = pixmap


class BandComboBox(QComboBox):
    """
    Flat monospace dropdown. Width fits the longest item; height is natural.
    Popup opens upward above the widget.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(16)
        view = QListView()
        view.setUniformItemSizes(True)
        self.setView(view)
        self._apply_scale()
        Scale.changed.connect(self._apply_scale)

    def _apply_scale(self):
        fs = scaled_font(9)
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {Colors.DEFAULT_FEATURE};
                color: white;
                border: 1px solid {Colors.PANEL_ACCENT};
                border-radius: {scaled(3)}px;
                padding: 0px {scaled(3)}px;
                font-size: {fs}pt;
                font-family: Consolas, monospace;
            }}
            QComboBox:hover {{ border: 1px solid {Colors.ACCENT};
                               background-color: {Colors.SUBTLE_PANEL_ACCENT}; }}
            QComboBox:focus {{ border: 1px solid {Colors.ACCENT}; }}
            QComboBox::drop-down {{ width: 0px; border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: white;
                border: 1px solid {Colors.ACCENT};
                border-radius: 0px;
                padding: 0px;
                outline: none;
                font-size: {fs}pt;
                font-family: Consolas, monospace;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 1px {scaled(8)}px;
                border: none;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {Colors.ACCENT};
                color: white;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
            }}
        """)
        self.ensurePolished()
        self.setFixedHeight(self.fontMetrics().height() + scaled(6))
        self._update_width()

    def _update_width(self):
        self.ensurePolished()
        fm    = self.fontMetrics()
        max_w = max((fm.horizontalAdvance(self.itemText(i))
                     for i in range(self.count())), default=0)
        self.setFixedWidth(max(fm.horizontalAdvance("WWW") + scaled(16),
                               max_w + scaled(16)))

    def set_active(self, active: bool):
        """Switch between active and inactive (grayed-out) appearance."""
        self.setEnabled(active)
        fs = scaled_font(9)
        if active:
            bg     = Colors.DEFAULT_FEATURE
            border = Colors.PANEL_ACCENT
            color  = "white"
            hover  = (f"QComboBox:hover {{ border: 1px solid {Colors.ACCENT}; "
                      f"background-color: {Colors.SUBTLE_PANEL_ACCENT}; }}")
            focus  = f"QComboBox:focus {{ border: 1px solid {Colors.ACCENT}; }}"
        else:
            bg     = Colors.DISABLED_FEATURE
            border = Colors.DISABLED_BORDER
            color  = Colors.TEXT_OVERLAY_LABEL
            hover  = ""
            focus  = ""
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {bg};
                color: {color};
                border: 1px solid {border};
                border-radius: {scaled(3)}px;
                padding: 0px {scaled(3)}px;
                font-size: {fs}pt;
                font-family: Consolas, monospace;
            }}
            QComboBox:disabled {{ color: {Colors.TEXT_OVERLAY_LABEL}; }}
            {hover}
            {focus}
            QComboBox::drop-down {{ width: 0px; border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: white;
                border: 1px solid {Colors.ACCENT};
                border-radius: 0px;
                padding: 0px;
                outline: none;
                font-size: {fs}pt;
                font-family: Consolas, monospace;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 1px {scaled(8)}px;
                border: none;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {Colors.ACCENT};
                color: white;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
            }}
        """)

    def addItems(self, texts):
        super().addItems(texts)
        self._update_width()

    def clear(self):
        super().clear()
        self.ensurePolished()
        fm = self.fontMetrics()
        self.setFixedWidth(fm.horizontalAdvance("WWW") + scaled(16))

    def showPopup(self):
        super().showPopup()
        popup = self.findChild(QFrame)
        if popup is None:
            return
        fm    = self.fontMetrics()
        new_w = max(
            self.width(),
            max((fm.boundingRect(self.itemText(i)).width()
                 for i in range(self.count())), default=0) + scaled(30)
        )
        popup.setMinimumWidth(new_w)
        popup.setFixedWidth(new_w)
        view = self.view()
        if view is not None:
            view.setMinimumWidth(new_w)
        popup.move(self.mapToGlobal(QPoint(0, -popup.height())))


class CollapsibleSection(QWidget):
    """Premiere Pro-style collapsible section with arrow toggle."""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.toggle_button = QToolButton(text=title, checkable=True, checked=True)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggle_button.pressed.connect(self._on_toggle)

        self.content_area   = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_area.setLayout(self.content_layout)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content_area)

        self._apply_scale()
        Scale.changed.connect(self._apply_scale)

    def _apply_scale(self):
        self.content_layout.setContentsMargins(scaled(10), scaled(10), 0, scaled(10))
        self.content_layout.setSpacing(scaled(5))
        self.toggle_button.setStyleSheet(f"""
            QToolButton {{
                border: none;
                color: {Colors.TEXT_PRIMARY};
                background-color: {Colors.PANEL_BACKGROUND};
                text-align: left;
                font-weight: bold;
                font-size: {scaled_font(9)}pt;
                padding: {scaled(2)}px;
            }}
            QToolButton:hover {{ background-color: {Colors.SUBTLE_PANEL_ACCENT}; }}
        """)

    def _on_toggle(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(Qt.DownArrow if not checked else Qt.RightArrow)
        self.content_area.setVisible(not checked)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)


class ColorSwatchButton(QWidget):
    """A single rounded-rect color swatch. Unused colors get a white border; hovered get accent blue."""

    clicked = pyqtSignal(tuple, str)  # (color, name)

    _SWATCH_SIZE  = 18
    _RADIUS       = 3
    _BORDER_WIDTH = 1

    def __init__(self, color, name, in_use=False, selected=False, parent=None):
        super().__init__(parent)
        self._color    = color
        self._name     = name
        self._in_use   = in_use
        self._selected = selected
        self._hovered  = False
        sz = scaled(self._SWATCH_SIZE)
        self.setFixedSize(sz, sz)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(name)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        radius = scaled(self._RADIUS)
        rect   = self.rect().adjusted(
            self._BORDER_WIDTH, self._BORDER_WIDTH,
            -self._BORDER_WIDTH, -self._BORDER_WIDTH,
        )

        if self._hovered:
            painter.setPen(QPen(QColor(Colors.ACCENT), self._BORDER_WIDTH))
        elif not self._in_use:
            painter.setPen(QPen(QColor("white"), self._BORDER_WIDTH))
        else:
            painter.setPen(Qt.NoPen)

        painter.setBrush(QColor(*self._color))
        painter.drawRoundedRect(rect, radius, radius)
        painter.end()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._color, self._name)


class ColorSwatchGrid(QFrame):
    """
    Floating palette grid for picking ROI colors.
    Emits color_selected when a swatch is clicked, then hides itself.
    In-use colors are shown dimmed but remain selectable.
    """

    color_selected = pyqtSignal(tuple, str)  # (color, name)

    _COLS = 8

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.PANEL_BACKGROUND};
                border: 1px solid {Colors.PANEL_ACCENT};
                border-radius: {scaled(4)}px;
            }}
        """)
        self._grid = QGridLayout()
        self._grid.setContentsMargins(scaled(6), scaled(6), scaled(6), scaled(6))
        self._grid.setSpacing(scaled(3))
        self.setLayout(self._grid)

    def populate(self, palette, in_use_names, selected_name=None):
        """Rebuild the grid from a (color, name) palette list."""
        for i in reversed(range(self._grid.count())):
            w = self._grid.itemAt(i).widget()
            if w:
                w.setParent(None)

        for idx, (color, name) in enumerate(palette):
            swatch = ColorSwatchButton(
                color, name,
                in_use   = name in in_use_names,
                selected = name == selected_name,
            )
            swatch.clicked.connect(self._on_swatch_clicked)
            self._grid.addWidget(swatch, idx // self._COLS, idx % self._COLS)

        self.adjustSize()

    def _on_swatch_clicked(self, color, name):
        self.color_selected.emit(color, name)
        self.hide()

    def show_at(self, pos):
        self.move(pos)
        self.show()
        self.raise_()