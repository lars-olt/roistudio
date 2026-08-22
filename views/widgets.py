from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QSize, QMimeData, QRectF, QTimer
from PyQt5.QtWidgets import (QLabel, QPushButton, QComboBox, QWidget,
                             QVBoxLayout, QGridLayout, QFrame, QToolButton,
                             QSizePolicy, QListView)
from PyQt5.QtGui import (QIcon, QMovie, QPainter, QPainterPath, QPen,
                         QPixmap, QColor, QDrag)

from colors import Colors
from utils.paths import _resource_path
from utils.scale import Scale, capped_scaled, scaled, scaled_font


_TOOLBAR_BUTTON_MAX_W = 56
_TOOLBAR_BUTTON_MAX_H = 46
_TOOLBAR_ACTIVITY_MAX = 32
_TOOLBAR_BUTTON_W     = 34
_TOOLBAR_BUTTON_H     = 28
_TOOLBAR_ACTIVITY_W   = 20


def toolbar_button_size():
    """Toolbar button size, responsive at small scales and capped at large ones."""
    return (
        capped_scaled(_TOOLBAR_BUTTON_W, _TOOLBAR_BUTTON_MAX_W),
        capped_scaled(_TOOLBAR_BUTTON_H, _TOOLBAR_BUTTON_MAX_H),
    )


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
        sz = capped_scaled(_TOOLBAR_ACTIVITY_W, _TOOLBAR_ACTIVITY_MAX)
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
    """Toolbar button with hover and optional selected icon states."""

    def __init__(self, normal_icon_path, selected_icon_path=None, hover_icon_path=None, selected_hover_icon_path=None, parent=None):
        super().__init__(parent)
        if hover_icon_path is None:
            stem, ext       = normal_icon_path.rsplit('.', 1)
            hover_icon_path = f"{stem}_hover.{ext}"
        self._path_normal         = normal_icon_path
        self._path_selected       = selected_icon_path or normal_icon_path
        self._path_hover          = hover_icon_path
        self._path_selected_hover = selected_hover_icon_path
        self.is_selected = False
        self._hovered    = False
        self.setCheckable(selected_icon_path is not None)
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
        w, h = toolbar_button_size()
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
        selected = self.isCheckable() and (self.is_selected or self.isChecked())
        if self._hovered and selected and self.selected_hover_icon:
            self.setIcon(self.selected_hover_icon)
        elif self._hovered and not selected:
            self.setIcon(self.hover_icon)
        elif selected:
            self.setIcon(self.selected_icon)
        else:
            self.setIcon(self.normal_icon)

    def set_selected(self, selected):
        self.is_selected = selected if self.isCheckable() else False
        self.setChecked(self.is_selected)
        self.update_icon()

    def changeEvent(self, event):
        super().changeEvent(event)
        from PyQt5.QtCore import QEvent
        if event.type() == QEvent.EnabledChange:
            self.setCursor(Qt.PointingHandCursor)

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
    """Premiere Pro-style collapsible section with an arrow toggle."""

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

    def is_expanded(self) -> bool:
        return self.toggle_button.isChecked()

    def set_expanded(self, expanded: bool):
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.content_area.setVisible(expanded)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)


class ColorSwatchButton(QWidget):
    """A rounded color swatch with white unused and blue hovered borders."""

    clicked = pyqtSignal(tuple, str)  # (color, name)

    _SWATCH_SIZE = 18
    _RADIUS      = 3
    # Use a heavier white ring for available colors and the accent ring for hover.
    _BORDER_WIDTH = 1
    _UNUSED_WIDTH = 2

    def __init__(self, color, name, in_use=False, selected=False, parent=None):
        super().__init__(parent)
        self._color    = color
        self._name     = name
        self._in_use   = in_use
        self._selected = selected
        self._hovered  = False
        self._pressed  = False
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(
            f"{name} - add to this selection" if in_use else name
        )
        self._apply_scale()
        Scale.changed.connect(self._apply_scale)

    def _apply_scale(self):
        sz = scaled(self._SWATCH_SIZE)
        self.setFixedSize(sz, sz)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        radius = scaled(self._RADIUS)
        if self._hovered:
            border = scaled(self._BORDER_WIDTH)
            pen    = QPen(QColor(Colors.ACCENT), border)
        elif not self._in_use:
            border = scaled(self._UNUSED_WIDTH)
            pen    = QPen(QColor("white"), border)
        else:
            border = 0
            pen    = QPen(Qt.NoPen)

        inset = border / 2
        rect  = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        painter.setPen(pen)
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
            self._pressed = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            clicked = self.rect().contains(event.pos())
            event.accept()
            if clicked:
                self.clicked.emit(self._color, self._name)
            return
        self._pressed = False
        super().mouseReleaseEvent(event)


class ColorSwatchGrid(QFrame):
    """
    Floating palette for picking ROI colors and acting on a specific ROI.
    Emits color_selected when a swatch is clicked, then hides itself.
    In-use colors are shown dimmed but remain selectable.
    """

    color_selected = pyqtSignal(tuple, str)  # (color, name)
    spectrum_action_requested = pyqtSignal()

    _COLS = 8

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName("roiContextPopup")
        self._layout = QVBoxLayout()
        self.setLayout(self._layout)

        self._grid = QGridLayout()
        self._layout.addLayout(self._grid)

        self._spectrum_action = QPushButton("Hide spectrum")
        self._spectrum_action.setCursor(Qt.PointingHandCursor)
        self._spectrum_action.setAccessibleName("Change spectrum visibility")
        self._spectrum_action.clicked.connect(self._on_spectrum_action_clicked)
        self._spectrum_action.hide()
        self._layout.addWidget(self._spectrum_action)

        self._palette       = []
        self._in_use_names  = []
        self._selected_name = None
        self._apply_scale()
        Scale.changed.connect(self._apply_scale)

    def _apply_scale(self):
        self.setStyleSheet(f"""
            QFrame#roiContextPopup {{
                background: transparent;
                border: none;
            }}
        """)
        m = scaled(6)
        self._layout.setContentsMargins(m, m, m, m)
        self._layout.setSpacing(scaled(5))
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(scaled(3))
        action_style = f"""
            QPushButton {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.PANEL_ACCENT};
                border-radius: {scaled(3)}px;
                padding: {scaled(4)}px {scaled(8)}px;
                font-size: {scaled_font(9)}pt;
            }}
            QPushButton:hover {{
                background-color: {Colors.PANEL_ACCENT};
                border-color: {Colors.ACCENT};
            }}
            QPushButton:checked {{
                background-color: {Colors.DEFAULT_FEATURE};
                border-color: {Colors.ACCENT};
                color: white;
            }}
            QPushButton:pressed {{ background-color: {Colors.DEFAULT_FEATURE}; }}
        """
        self._spectrum_action.setStyleSheet(action_style)
        # Swatches resize from Scale.changed; update the containing frame here.
        self.adjustSize()

    def paintEvent(self, event):
        """Paint the same antialiased rounded edge used by the preset bar."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, scaled(3), scaled(3))
        painter.setClipPath(path)
        painter.fillPath(path, QColor(Colors.PANEL_BACKGROUND))
        painter.setClipping(False)
        painter.setPen(QPen(QColor(Colors.PANEL_ACCENT), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.end()

    def populate(self, palette, in_use_names, selected_name=None):
        """Rebuild the grid from a (color, name) palette list."""
        self._palette       = palette
        self._in_use_names  = in_use_names
        self._selected_name = selected_name

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
        # Keep the popup alive until the swatch's release event has completely
        # finished. Hiding it during mouse-down/release can expose a toolbar
        # button beneath the popup to the tail end of the same click.
        QTimer.singleShot(
            0, lambda c=color, n=name: self._commit_swatch_selection(c, n)
        )

    def _commit_swatch_selection(self, color, name):
        self.color_selected.emit(color, name)
        self.hide()

    def set_spectrum_action(self, visible, spectrum_hidden=False):
        """Configure the per-ROI spectrum action shown below the swatches."""
        text = "Show spectrum" if spectrum_hidden else "Hide spectrum"
        self._spectrum_action.setText(text)
        self._spectrum_action.setToolTip(text)
        self._spectrum_action.setVisible(bool(visible))
        self.adjustSize()

    def _on_spectrum_action_clicked(self):
        self.spectrum_action_requested.emit()
        self.hide()

    def show_at(self, pos):
        self.move(pos)
        self.show()
        self.raise_()
