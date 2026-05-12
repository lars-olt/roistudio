import cv2
import numpy as np

from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QPoint, QRectF, QRect, QTimer, QEvent
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QSplitter
from PyQt5.QtGui import (QPainter, QColor, QKeyEvent, QMouseEvent, QWheelEvent,
                         QPen, QFont, QFontMetrics)

from colors import Colors
from utils.scale import scaled, scaled_font, bar_height


_FRICTION        = 0.88
_MIN_VELOCITY    = 0.5
_MOMENTUM_HZ     = 60
_VELOCITY_WINDOW = 5


class CanvasContainer(QWidget):
    """
    Pan/zoom canvas with interactive ROI editing.
    Supports mouse drag, trackpad two-finger pan with momentum, pinch-to-zoom,
    and ctrl+scroll zoom.
    """

    scene_dropped = pyqtSignal(str)
    pixel_hovered = pyqtSignal(int, int)
    roi_changed   = pyqtSignal(int, tuple)
    roi_selected  = pyqtSignal(int)
    roi_deleted   = pyqtSignal(int)
    roi_created   = pyqtSignal(tuple)
    # Emits (zoom, image_cx, image_cy) — viewport center captured at interaction
    # time so sync handlers always receive a stable snapshot.
    sync_changed  = pyqtSignal(float, float, float)
    roi_too_small = pyqtSignal()
    tool_shortcut = pyqtSignal(str)

    MODE_NONE      = 0
    MODE_MOVE      = 1
    MODE_RESIZE_TL = 2
    MODE_RESIZE_TR = 3
    MODE_RESIZE_BL = 4
    MODE_RESIZE_BR = 5
    MODE_CREATE    = 6
    MODE_RESIZE_T  = 7
    MODE_RESIZE_B  = 8
    MODE_RESIZE_L  = 9
    MODE_RESIZE_R  = 10

    HANDLE_SIZE = 4

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {Colors.APP_BACKGROUND};")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.grabGesture(Qt.PinchGesture)
        self.setAcceptDrops(True)

        self.zoom_level    = 1.0
        self.pan_offset    = QPointF(0, 0)
        self.is_panning    = False
        self._pan_is_mouse = False
        self.last_mouse_pos  = QPoint()
        self.space_pressed   = False
        self.tool_cursor     = Qt.ArrowCursor

        self._velocity      = QPointF(0, 0)
        self._delta_history = []
        self._momentum_timer = QTimer(self)
        self._momentum_timer.setInterval(1000 // _MOMENTUM_HZ)
        self._momentum_timer.timeout.connect(self._momentum_tick)

        self.rois               = []
        self.roi_colors         = []
        self.roi_names          = []
        self.selected_roi_index = -1
        self.hovered_roi_index  = -1
        self.interaction_mode      = self.MODE_NONE
        self.interaction_tool      = "selection"
        self.creation_start_pos    = None
        self.current_creation_rect = None
        self.hover_preview_enabled = False
        self.roi_labels_visible    = False

        self.canvas = ImageCanvas()
        self.canvas.setMouseTracking(True)
        self.canvas.scene_dropped.connect(self.scene_dropped.emit)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tool_cursor(self, cursor):
        self.tool_cursor = cursor
        self.setCursor(cursor)

    def set_hover_preview_enabled(self, enabled):
        self.hover_preview_enabled = enabled

    def set_image(self, pixmap):
        self.canvas.set_image(pixmap)
        self.update()

    def set_rois(self, rois, colors=None, names=None):
        self.rois       = [tuple(map(float, r['roi'])) for r in rois]
        self.roi_colors = colors if colors else []
        self.roi_names  = names  if names  else []
        self.selected_roi_index = -1
        self.hovered_roi_index  = -1
        self.update()

    def set_tool(self, tool_name):
        self.interaction_tool = tool_name
        self.selected_roi_index = -1
        self.hovered_roi_index  = -1
        self.interaction_mode = self.MODE_NONE
        self.current_creation_rect = None
        self.update()

    def fit_to_panel(self):
        self.zoom_level = min(self.width()  / self.canvas.width(),
                              self.height() / self.canvas.height())
        self.pan_offset = QPointF(0, 0)
        self.update()
        self._emit_sync()

    # ------------------------------------------------------------------
    # Coordinate math
    # ------------------------------------------------------------------

    def _canvas_origin(self):
        """Top-left of the image in unscaled widget coordinates."""
        return ((self.width()  / self.zoom_level - self.canvas.width())  / 2,
                (self.height() / self.zoom_level - self.canvas.height()) / 2)

    def _get_image_coords(self, widget_pos):
        ox, oy = self._canvas_origin()
        return ((widget_pos.x() - self.pan_offset.x()) / self.zoom_level - ox,
                (widget_pos.y() - self.pan_offset.y()) / self.zoom_level - oy)

    def _viewport_center_image(self):
        """Image-space coordinate at the center of the viewport."""
        ox, oy = self._canvas_origin()
        return ((self.width()  / 2 - self.pan_offset.x()) / self.zoom_level - ox,
                (self.height() / 2 - self.pan_offset.y()) / self.zoom_level - oy)

    def _pan_to_image_point(self, ix: float, iy: float):
        """Set pan offset so image point (ix, iy) is centered in the viewport."""
        ox, oy = self._canvas_origin()
        self.pan_offset = QPointF(
            self.width()  / 2 - (ox + ix) * self.zoom_level,
            self.height() / 2 - (oy + iy) * self.zoom_level,
        )

    def _emit_sync(self):
        cx, cy = self._viewport_center_image()
        self.sync_changed.emit(self.zoom_level, cx, cy)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        from views.panels.stretch_bar import StretchBar
        for child in self.children():
            if isinstance(child, StretchBar):
                child._reposition()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(Colors.APP_BACKGROUND))

        painter.save()
        painter.translate(self.pan_offset)
        painter.scale(self.zoom_level, self.zoom_level)

        ox, oy = self._canvas_origin()
        painter.fillRect(int(ox), int(oy),
                         self.canvas.width(), self.canvas.height(),
                         QColor(255, 255, 255))
        if self.canvas.image is not None:
            painter.drawPixmap(int(ox), int(oy), self.canvas.image)

        painter.translate(ox, oy)
        self._draw_rois(painter)

        if self.interaction_mode == self.MODE_CREATE and self.current_creation_rect:
            pen = QPen(QColor(Colors.ACCENT), 2 / self.zoom_level)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.current_creation_rect)

        painter.restore()
        self._draw_zoom_indicator(painter)

    def _draw_rois(self, painter):
        handle_sz = self.HANDLE_SIZE / self.zoom_level
        for i, rect_tuple in enumerate(self.rois):
            rect       = QRectF(*rect_tuple)
            base_color = (QColor(*self.roi_colors[i])
                          if i < len(self.roi_colors) else QColor(Colors.ACCENT))
            if i == self.selected_roi_index and self.interaction_tool == "selection":
                pen = QPen(QColor("#FFFFFF"), 1 / self.zoom_level)
                pen.setStyle(Qt.DashLine)
                fill = QColor(base_color); fill.setAlpha(80)
                painter.setPen(pen); painter.setBrush(fill)
                painter.drawRect(rect)
                painter.setPen(QPen(QColor("black"), 1 / self.zoom_level))
                painter.setBrush(QColor("white"))
                for pt in (rect.topLeft(), rect.topRight(),
                           rect.bottomLeft(), rect.bottomRight()):
                    painter.drawRect(QRectF(pt.x() - handle_sz / 2,
                                            pt.y() - handle_sz / 2,
                                            handle_sz, handle_sz))
            else:
                fill = QColor(base_color); fill.setAlpha(60)
                painter.setPen(QPen(base_color, 1 / self.zoom_level))
                painter.setBrush(fill)
                painter.drawRect(rect)

            if i < len(self.roi_names) and self.roi_labels_visible:
                self._draw_roi_label(painter, rect, self.roi_names[i], base_color)

    def _draw_roi_label(self, painter, rect, name, color):
        pt_size = max(1, round(scaled_font(8) / self.zoom_level))
        padding = 2 / self.zoom_level

        font    = QFont("Arial", pt_size)
        metrics = QFontMetrics(font)
        text_w  = metrics.horizontalAdvance(name)
        text_h  = metrics.height()
        bg_w    = text_w + padding * 2
        bg_h    = text_h + padding * 2

        bg = QColor(20, 20, 20, 200)
        painter.fillRect(QRectF(rect.x(), rect.y() - bg_h, bg_w, bg_h), bg)

        painter.setFont(font)
        painter.setPen(QColor(*color.getRgb()[:3]))
        painter.drawText(
            QRectF(rect.x() + padding, rect.y() - bg_h + padding, text_w, text_h),
            Qt.AlignLeft | Qt.AlignVCenter,
            name,
        )

    def _zoom_indicator_rect(self) -> QRect:
        font  = QFont("Arial", scaled_font(9))
        box_h = bar_height()
        box_w = QFontMetrics(font).horizontalAdvance("10.00x") + 2 * scaled(3)
        return QRect(self.width()  - box_w - scaled(10),
                     self.height() - box_h - scaled(10),
                     box_w, box_h)

    def _draw_zoom_indicator(self, painter):
        font = QFont("Arial", scaled_font(9))
        r    = self._zoom_indicator_rect()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(40, 40, 40, 180))
        painter.drawRoundedRect(r, scaled(3), scaled(3))
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRectF(r), Qt.AlignCenter, f"{self.zoom_level:.2f}x")

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def _hit_test(self, img_x, img_y):
        if self.interaction_tool != "selection":
            return -1, self.MODE_NONE

        handle_sz = self.HANDLE_SIZE / self.zoom_level
        edge_sz   = handle_sz * 2

        if self.selected_roi_index != -1:
            rect = QRectF(*self.rois[self.selected_roi_index])

            # Corner handles - take priority over sides.
            for pt, mode in (
                (rect.topLeft(),     self.MODE_RESIZE_TL),
                (rect.topRight(),    self.MODE_RESIZE_TR),
                (rect.bottomLeft(),  self.MODE_RESIZE_BL),
                (rect.bottomRight(), self.MODE_RESIZE_BR),
            ):
                if QRectF(pt.x() - handle_sz, pt.y() - handle_sz,
                        handle_sz * 2, handle_sz * 2).contains(img_x, img_y):
                    return self.selected_roi_index, mode

            # Side edges: proximity is how close the cursor is to the edge,
            # span checks the cursor is between the corners (not in corner territory).
            ix0, ix1 = rect.left() + edge_sz, rect.right()  - edge_sz
            iy0, iy1 = rect.top()  + edge_sz, rect.bottom() - edge_sz
            for edge, proximity, span, span_min, span_max, mode in (
                (rect.top(),    img_y, img_x, ix0, ix1, self.MODE_RESIZE_T),
                (rect.bottom(), img_y, img_x, ix0, ix1, self.MODE_RESIZE_B),
                (rect.left(),   img_x, img_y, iy0, iy1, self.MODE_RESIZE_L),
                (rect.right(),  img_x, img_y, iy0, iy1, self.MODE_RESIZE_R),
            ):
                if abs(proximity - edge) <= edge_sz and span_min < span < span_max:
                    return self.selected_roi_index, mode

            if rect.contains(img_x, img_y):
                return self.selected_roi_index, self.MODE_MOVE

        for i, r in enumerate(self.rois):
            if QRectF(*r).contains(img_x, img_y):
                return i, self.MODE_MOVE

        # no ROI hit
        return -1, self.MODE_NONE

    def _update_hover(self, img_x, img_y):
        """Update hovered_roi_index and repaint if it changed."""
        new_hover = -1
        for i, r in enumerate(self.rois):
            if QRectF(*r).contains(img_x, img_y):
                new_hover = i
                break
        if new_hover != self.hovered_roi_index:
            self.hovered_roi_index = new_hover
            self.update()

    # ------------------------------------------------------------------
    # Momentum
    # ------------------------------------------------------------------

    def _record_delta(self, dx, dy):
        self._delta_history.append(QPointF(dx, dy))
        if len(self._delta_history) > _VELOCITY_WINDOW:
            self._delta_history.pop(0)

    def _launch_momentum(self):
        if not self._delta_history:
            return
        n = len(self._delta_history)
        self._velocity = QPointF(
            sum(d.x() for d in self._delta_history) / n,
            sum(d.y() for d in self._delta_history) / n,
        )
        self._delta_history.clear()
        self._momentum_timer.start()

    def _momentum_tick(self):
        self._velocity *= _FRICTION
        if (self._velocity.x() ** 2 + self._velocity.y() ** 2) ** 0.5 < _MIN_VELOCITY:
            self._momentum_timer.stop()
            self._velocity = QPointF(0, 0)
            return
        self.pan_offset += self._velocity
        self.update()
        self._emit_sync()

    def _stop_momentum(self):
        self._momentum_timer.stop()
        self._velocity = QPointF(0, 0)

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def _apply_zoom(self, factor, vx, vy):
        ox, oy   = self._canvas_origin()
        img_x    = (vx - self.pan_offset.x()) / self.zoom_level - ox
        img_y    = (vy - self.pan_offset.y()) / self.zoom_level - oy
        self.zoom_level = max(0.1, min(10.0, self.zoom_level * factor))
        ox2, oy2 = self._canvas_origin()
        self.pan_offset.setX(vx - (ox2 + img_x) * self.zoom_level)
        self.pan_offset.setY(vy - (oy2 + img_y) * self.zoom_level)
        self.update()
        self._emit_sync()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def event(self, ev):
        if ev.type() == QEvent.Gesture:
            pinch = ev.gesture(Qt.PinchGesture)
            if pinch:
                self._stop_momentum()
                c = pinch.centerPoint()
                self._apply_zoom(pinch.scaleFactor(), c.x(), c.y())
                ev.accept()
                return True
        return super().event(ev)

    def wheelEvent(self, event: QWheelEvent):
        self._stop_momentum()
        is_trackpad = event.source() in (Qt.MouseEventSynthesizedBySystem,
                                         Qt.MouseEventSynthesizedByQt)
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self._apply_zoom(factor, event.pos().x(), event.pos().y())
            return
        if is_trackpad:
            dx = event.pixelDelta().x() or event.angleDelta().x() / 8
            dy = event.pixelDelta().y() or event.angleDelta().y() / 8
            self.pan_offset += QPointF(dx, dy)
            self._record_delta(dx, dy)
        else:
            self.pan_offset.setY(self.pan_offset.y() + event.angleDelta().y() * 0.5)
        self.update()
        self._emit_sync()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self._zoom_indicator_rect().contains(event.pos()):
            self.fit_to_panel()

    def mousePressEvent(self, event: QMouseEvent):
        self._stop_momentum()
        self.last_mouse_pos = event.pos()

        if (event.button() == Qt.MiddleButton
                or (event.button() == Qt.LeftButton and self.space_pressed)):
            self.is_panning    = True
            self._pan_is_mouse = True
            self._delta_history.clear()
            self.setCursor(Qt.ClosedHandCursor)
            return

        img_x, img_y = self._get_image_coords(event.pos())

        if self.interaction_tool == "selection" and event.button() == Qt.LeftButton:
            idx, mode = self._hit_test(img_x, img_y)
            if idx != -1:
                self.selected_roi_index = idx
                self.interaction_mode   = mode
                self.roi_selected.emit(idx)
                self.update()
                return
            if self.selected_roi_index != -1:
                self.selected_roi_index = -1
                self.update()

        elif self.interaction_tool == "rectangle" and event.button() == Qt.LeftButton:
            self.interaction_mode      = self.MODE_CREATE
            self.creation_start_pos    = (img_x, img_y)
            self.current_creation_rect = QRectF(img_x, img_y, 0, 0)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_panning:
            delta = event.pos() - self.last_mouse_pos
            self.pan_offset    += delta
            self._record_delta(delta.x(), delta.y())
            self.last_mouse_pos = event.pos()
            self.update()
            self._emit_sync()
            return

        img_x, img_y = self._get_image_coords(event.pos())

        if self.interaction_mode == self.MODE_CREATE:
            sx, sy = self.creation_start_pos
            w, h   = img_x - sx, img_y - sy
            self.current_creation_rect = QRectF(
                sx if w > 0 else img_x, sy if h > 0 else img_y, abs(w), abs(h)
            )
            self.update()
            if (self.hover_preview_enabled
                    and 0 <= img_x < self.canvas.width()
                    and 0 <= img_y < self.canvas.height()):
                self.pixel_hovered.emit(int(img_x), int(img_y))
            return

        if self.interaction_mode != self.MODE_NONE and self.selected_roi_index != -1:
            r      = list(self.rois[self.selected_roi_index])
            px, py = self._get_image_coords(self.last_mouse_pos)
            dx, dy = img_x - px, img_y - py

            if   self.interaction_mode == self.MODE_MOVE:
                r[0] += dx; r[1] += dy
            elif self.interaction_mode == self.MODE_RESIZE_BR:
                r[2] += dx; r[3] += dy
            elif self.interaction_mode == self.MODE_RESIZE_TL:
                r[0] += dx; r[1] += dy; r[2] -= dx; r[3] -= dy
            elif self.interaction_mode == self.MODE_RESIZE_TR:
                r[1] += dy; r[2] += dx; r[3] -= dy
            elif self.interaction_mode == self.MODE_RESIZE_BL:
                r[0] += dx; r[2] -= dx; r[3] += dy
            elif self.interaction_mode == self.MODE_RESIZE_T:
                r[1] += dy; r[3] -= dy
            elif self.interaction_mode == self.MODE_RESIZE_B:
                r[3] += dy
            elif self.interaction_mode == self.MODE_RESIZE_L:
                r[0] += dx; r[2] -= dx
            elif self.interaction_mode == self.MODE_RESIZE_R:
                r[2] += dx

            r[2] = max(5, r[2]); r[3] = max(5, r[3])
            self.rois[self.selected_roi_index] = tuple(r)
            self.last_mouse_pos = event.pos()
            self.update()
            return

        self._update_hover(img_x, img_y)

        if self.interaction_tool == "selection":
            _, mode = self._hit_test(img_x, img_y)
            self.setCursor({
                self.MODE_MOVE:      Qt.SizeAllCursor,
                self.MODE_RESIZE_TL: Qt.SizeFDiagCursor,
                self.MODE_RESIZE_BR: Qt.SizeFDiagCursor,
                self.MODE_RESIZE_TR: Qt.SizeBDiagCursor,
                self.MODE_RESIZE_BL: Qt.SizeBDiagCursor,
                self.MODE_RESIZE_T:  Qt.SizeVerCursor,
                self.MODE_RESIZE_B:  Qt.SizeVerCursor,
                self.MODE_RESIZE_L:  Qt.SizeHorCursor,
                self.MODE_RESIZE_R:  Qt.SizeHorCursor,
            }.get(mode, self.tool_cursor))

        if (self.hover_preview_enabled
                and 0 <= img_x < self.canvas.width()
                and 0 <= img_y < self.canvas.height()):
            self.pixel_hovered.emit(int(img_x), int(img_y))

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.is_panning:
            self.is_panning = False
            self.setCursor(Qt.OpenHandCursor if self.space_pressed else self.tool_cursor)
            if not self._pan_is_mouse:
                self._launch_momentum()
            self._pan_is_mouse = False
            return

        if self.interaction_mode == self.MODE_CREATE:
            if self.current_creation_rect:
                r = self.current_creation_rect
                if r.width() > 5 and r.height() > 5:
                    self.roi_created.emit((r.x(), r.y(), r.width(), r.height()))
                else:
                    self.roi_too_small.emit()
            self.current_creation_rect = None
            self.interaction_mode = self.MODE_NONE
            self.update()
            return

        if self.interaction_mode != self.MODE_NONE:
            if self.selected_roi_index != -1:
                self.roi_changed.emit(self.selected_roi_index,
                                      tuple(self.rois[self.selected_roi_index]))
            self.interaction_mode = self.MODE_NONE

    def leaveEvent(self, event):
        if self.hovered_roi_index != -1:
            self.hovered_roi_index = -1
            self.update()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_V:
            self.tool_shortcut.emit("selection")
            return
        if event.key() == Qt.Key_R:
            self.tool_shortcut.emit("rectangle")
            return
        if event.key() == Qt.Key_F:
            self.fit_to_panel()
            return
        if event.key() == Qt.Key_Escape:
            if self.selected_roi_index != -1:
                self.selected_roi_index = -1
                self.update()
            return
        if event.key() == Qt.Key_Space and not self.space_pressed:
            self.space_pressed = True
            if not self.is_panning:
                self.setCursor(Qt.OpenHandCursor)
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.selected_roi_index != -1 and self.interaction_tool == "selection":
                self.roi_deleted.emit(self.selected_roi_index)
                self.selected_roi_index = -1
                self.update()

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Space:
            self.space_pressed = False
            if not self.is_panning:
                super().setCursor(self.tool_cursor)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            QTimer.singleShot(0, lambda: self.scene_dropped.emit(event.mimeData().text()))

    def set_roi_labels_visible(self, visible: bool):
        self.roi_labels_visible = visible
        self.update()


class ImageCanvas(QWidget):
    """Holds the image pixmap and defines canvas dimensions."""

    scene_dropped = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.image         = None
        self.canvas_width  = 1648
        self.canvas_height = 1214
        self.setFixedSize(self.canvas_width, self.canvas_height)
        self.setAcceptDrops(True)

    def set_image(self, pixmap):
        self.image = pixmap
        if pixmap is not None:
            self.canvas_width  = pixmap.width()
            self.canvas_height = pixmap.height()
            self.setFixedSize(self.canvas_width, self.canvas_height)
        if self.parent():
            self.parent().update()

    def width(self):  return self.canvas_width
    def height(self): return self.canvas_height

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            QTimer.singleShot(0, lambda: self.scene_dropped.emit(event.mimeData().text()))


class DualCanvasContainer(QWidget):
    """
    Manages single and split-screen canvas modes.
    When sync is enabled, panning or zooming one canvas transforms the
    viewport center through the homography and mirrors it on the other.
    """

    scene_dropped = pyqtSignal(str)
    pixel_hovered = pyqtSignal(int, int)
    roi_changed   = pyqtSignal(int, tuple, str)
    roi_selected  = pyqtSignal(int)
    roi_deleted   = pyqtSignal(int)
    roi_created   = pyqtSignal(tuple, str)
    roi_too_small = pyqtSignal()
    tool_shortcut = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.is_split_mode             = False
        self.homography_matrix         = None
        self.inverse_homography_matrix = None
        self._sync_enabled             = False
        self._syncing                  = False

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)

        self.canvas_single = CanvasContainer()
        self.canvas_left   = CanvasContainer()
        self.canvas_right  = CanvasContainer()
        for canvas in (self.canvas_single, self.canvas_left, self.canvas_right):
            self._connect_canvas_signals(canvas)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet(f"""
            QSplitter::handle       {{ background-color: {Colors.PANEL_ACCENT}; }}
            QSplitter::handle:hover {{ background-color: {Colors.ACCENT}; }}
        """)
        self.splitter.addWidget(self.canvas_left)
        self.splitter.addWidget(self.canvas_right)
        self.splitter.setSizes([500, 500])

        self.layout.addWidget(self.canvas_single)
        self.splitter.hide()

    def _connect_canvas_signals(self, canvas):
        canvas.scene_dropped.connect(self.scene_dropped.emit)
        canvas.pixel_hovered.connect(self.pixel_hovered.emit)
        canvas.roi_selected.connect(self.roi_selected.emit)
        canvas.roi_deleted.connect(self.roi_deleted.emit)
        canvas.roi_changed.connect(
            lambda idx, rect, c=canvas: self._on_canvas_roi_changed(c, idx, rect))
        canvas.roi_created.connect(
            lambda rect, c=canvas: self._on_canvas_roi_created(c, rect))
        canvas.sync_changed.connect(
            lambda zoom, cx, cy, c=canvas: self._on_sync_changed(c, zoom, cx, cy))
        canvas.roi_too_small.connect(self.roi_too_small.emit)
        canvas.tool_shortcut.connect(self.tool_shortcut.emit)

    def _camera_label(self, canvas):
        return ('left'  if canvas is self.canvas_left  else
                'right' if canvas is self.canvas_right else 'single')

    def _on_canvas_roi_changed(self, source, roi_index, rect):
        self.roi_changed.emit(roi_index, rect, self._camera_label(source))

    def _on_canvas_roi_created(self, source, rect):
        self.roi_created.emit(rect, self._camera_label(source))

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def set_sync_enabled(self, enabled: bool, source_camera: str = 'right'):
        self._sync_enabled = enabled
        if not enabled or not self.is_split_mode:
            return
        source = self.canvas_left  if source_camera == 'left' else self.canvas_right
        target = self.canvas_right if source_camera == 'left' else self.canvas_left
        H      = (self.inverse_homography_matrix if source_camera == 'right'
                  else self.homography_matrix)
        cx, cy = source._viewport_center_image()
        self._syncing = True
        try:
            self._apply_synced_view(source, target, source.zoom_level, cx, cy, H)
        finally:
            self._syncing = False

    def _on_sync_changed(self, source: CanvasContainer,
                         zoom: float, cx: float, cy: float):
        if not self._sync_enabled or not self.is_split_mode or self._syncing:
            return
        target = self.canvas_left  if source is self.canvas_right else self.canvas_right
        H      = (self.inverse_homography_matrix if source is self.canvas_right
                  else self.homography_matrix)
        self._syncing = True
        try:
            self._apply_synced_view(source, target, zoom, cx, cy, H)
        finally:
            self._syncing = False

    def _apply_synced_view(self, source: CanvasContainer, target: CanvasContainer,
                           zoom: float, cx: float, cy: float, H):
        """Transform (cx, cy) through H and recenter the target at the same zoom."""
        if H is not None:
            pt     = np.array([[[cx, cy]]], dtype=np.float32)
            tpt    = cv2.perspectiveTransform(pt, H).reshape(2)
            cx, cy = float(tpt[0]), float(tpt[1])
        zoom_ratio        = source.width() / target.width() if target.width() > 0 else 1.0
        target.zoom_level = zoom * zoom_ratio
        target._pan_to_image_point(cx, cy)
        target.update()

    # ------------------------------------------------------------------
    # Split mode
    # ------------------------------------------------------------------

    def set_split_mode(self, split_mode):
        if split_mode == self.is_split_mode:
            return
        self.is_split_mode = split_mode
        if split_mode:
            self.layout.removeWidget(self.canvas_single)
            self.canvas_single.hide()
            self.layout.addWidget(self.splitter)
            self.splitter.show()
        else:
            self.layout.removeWidget(self.splitter)
            self.splitter.hide()
            self.layout.addWidget(self.canvas_single)
            self.canvas_single.show()
            if self.canvas_right.canvas.image is not None:
                self.canvas_single.set_image(self.canvas_right.canvas.image)
            if self.canvas_right.rois:
                self.canvas_single.set_rois(
                    [{'roi': r} for r in self.canvas_right.rois],
                    self.canvas_right.roi_colors,
                    self.canvas_right.roi_names,
                )

    def set_homography_matrix(self, homography_matrix):
        self.homography_matrix = homography_matrix
        self.inverse_homography_matrix = (cv2.invert(homography_matrix)[1]
                                          if homography_matrix is not None else None)

    def set_camera_images(self, left_pixmap, right_pixmap):
        if self.is_split_mode:
            self.canvas_left.set_image(left_pixmap)
            self.canvas_right.set_image(right_pixmap)
        else:
            self.canvas_single.set_image(right_pixmap)

    def set_rois(self, rois, colors=None, names=None):
        if not self.is_split_mode:
            self.canvas_single.set_rois(rois, colors, names)
            return
        self.canvas_right.set_rois(rois, colors, names)
        left_rois = []
        for roi_data in rois:
            if 'left_rect' in roi_data:
                left_rois.append({'roi': roi_data['left_rect']})
            elif self.inverse_homography_matrix is not None:
                x, y, w, h = map(float, roi_data['roi'])
                corners = np.array([[x, y], [x+w, y], [x+w, y+h], [x, y+h]],
                                   dtype=np.float32).reshape(-1, 1, 2)
                tc = cv2.perspectiveTransform(
                    corners, self.inverse_homography_matrix
                ).reshape(-1, 2)
                xl, yl = tc[:, 0].min(), tc[:, 1].min()
                left_rois.append({'roi': (xl, yl,
                                          tc[:, 0].max() - xl,
                                          tc[:, 1].max() - yl)})
            else:
                left_rois.append({'roi': roi_data['roi']})
        self.canvas_left.set_rois(left_rois, colors, names)

    def set_tool_cursor(self, cursor):
        for c in self._active_canvases():
            c.set_tool_cursor(cursor)

    def set_hover_preview_enabled(self, enabled):
        for c in self._active_canvases():
            c.set_hover_preview_enabled(enabled)

    def set_image(self, pixmap):
        (self.canvas_right if self.is_split_mode else self.canvas_single).set_image(pixmap)

    def set_tool(self, tool_name):
        for c in self._active_canvases():
            c.set_tool(tool_name)

    def _active_canvases(self):
        return (self.canvas_left, self.canvas_right) if self.is_split_mode else (self.canvas_single,)

    def set_roi_labels_visible(self, visible: bool):
        for c in (self.canvas_single, self.canvas_left, self.canvas_right):
            c.set_roi_labels_visible(visible)

    @property
    def canvas(self):
        return (self.canvas_left if self.is_split_mode else self.canvas_single).canvas