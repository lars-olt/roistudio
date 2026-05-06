from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QPoint, QRectF, QRect, QTimer
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QSplitter
from PyQt5.QtGui import (QPainter, QColor, QKeyEvent, QMouseEvent, QWheelEvent,
                         QPen, QCursor)

from colors import Colors
import numpy as np

# ------------------------------------------------------------------
# Momentum physics
# ------------------------------------------------------------------

_FRICTION        = 0.88   # velocity multiplier per frame
_MIN_VELOCITY    = 0.5    # px/frame below which momentum stops
_MOMENTUM_HZ     = 60     # timer interval in ms
_VELOCITY_WINDOW = 5      # frames to average for launch velocity


class CanvasContainer(QWidget):
    """
    Container for canvas with pan, zoom, and interactive ROI editing.
    Supports mouse pan/zoom, ctrl+scroll zoom, and trackpad two-finger
    pan (with momentum) and pinch-to-zoom.
    """

    scene_dropped = pyqtSignal(str)
    pixel_hovered = pyqtSignal(int, int)

    roi_changed  = pyqtSignal(int, tuple)
    roi_selected = pyqtSignal(int)
    roi_deleted  = pyqtSignal(int)
    roi_created  = pyqtSignal(tuple)

    MODE_NONE      = 0
    MODE_MOVE      = 1
    MODE_RESIZE_TL = 2
    MODE_RESIZE_TR = 3
    MODE_RESIZE_BL = 4
    MODE_RESIZE_BR = 5
    MODE_CREATE    = 6

    HANDLE_SIZE = 4

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {Colors.APP_BACKGROUND};")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.grabGesture(Qt.PinchGesture)

        # Navigation
        self.zoom_level  = 1.0
        self.pan_offset  = QPointF(0, 0)
        self.is_panning  = False
        self.last_mouse_pos  = QPoint()
        self.space_pressed   = False

        # Momentum
        self._velocity          = QPointF(0, 0)
        self._delta_history     = []          # rolling window of recent deltas
        self._pan_is_mouse      = False
        self._momentum_timer    = QTimer(self)
        self._momentum_timer.setInterval(1000 // _MOMENTUM_HZ)
        self._momentum_timer.timeout.connect(self._momentum_tick)

        # Cursor
        self.tool_cursor = Qt.ArrowCursor

        # ROI state
        self.rois              = []
        self.roi_colors        = []
        self.selected_roi_index = -1

        # Interaction
        self.interaction_mode  = self.MODE_NONE
        self.interaction_tool  = "selection"
        self.creation_start_pos    = None
        self.current_creation_rect = None

        self.canvas = ImageCanvas()
        self.canvas.setMouseTracking(True)
        self.canvas.scene_dropped.connect(self.scene_dropped.emit)

        self.setAcceptDrops(True)
        self.hover_preview_enabled = False

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

    def set_rois(self, rois, colors=None):
        self.rois = [tuple(map(float, r['roi'])) for r in rois]
        self.roi_colors = colors if colors else []
        self.selected_roi_index = -1
        self.update()

    def set_tool(self, tool_name):
        self.interaction_tool = tool_name
        self.selected_roi_index = -1
        self.interaction_mode = self.MODE_NONE
        self.current_creation_rect = None
        self.update()

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

        canvas_x = (self.width()  / self.zoom_level - self.canvas.width())  / 2
        canvas_y = (self.height() / self.zoom_level - self.canvas.height()) / 2

        painter.fillRect(int(canvas_x), int(canvas_y),
                         self.canvas.width(), self.canvas.height(),
                         QColor(255, 255, 255))

        if self.canvas.image is not None:
            painter.drawPixmap(int(canvas_x), int(canvas_y), self.canvas.image)

        painter.translate(canvas_x, canvas_y)
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
            x, y, w, h = rect_tuple
            rect = QRectF(x, y, w, h)

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
    
    def fit_to_panel(self):
        if self.canvas.image is None:
            return
        self.zoom_level = min(self.width() / self.canvas.width(),
                            self.height() / self.canvas.height())
        self.pan_offset = QPointF(0, 0)
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self._zoom_indicator_rect().contains(event.pos()):
            self.fit_to_panel()
    
    def _zoom_indicator_rect(self):
        from utils.scale import scaled, scaled_font
        from PyQt5.QtGui import QFont, QFontMetrics
        font    = QFont("Arial", scaled_font(8))
        metrics = QFontMetrics(font)
        max_w   = metrics.horizontalAdvance("10.00x")
        text_h  = metrics.height()
        margin  = scaled(8)
        padding = scaled(10)
        box_w   = max_w + 2 * margin
        box_h   = text_h + 2 * margin
        return QRect(self.width()  - box_w - padding,
                    self.height() - box_h - padding,
                    box_w, box_h)

    def _draw_zoom_indicator(self, painter):
        from PyQt5.QtGui import QFont, QFontMetrics
        from utils.scale import scaled, scaled_font
        font    = QFont("Arial", scaled_font(8))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        margin  = scaled(8)
        r       = self._zoom_indicator_rect()
        painter.fillRect(r, QColor(40, 40, 40, 180))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(r.x() + margin, r.y() + margin + metrics.ascent(),
                        f"{self.zoom_level:.2f}x")

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _get_image_coords(self, widget_pos):
        cvx = (self.pan_offset.x()
               + (self.width()  / self.zoom_level - self.canvas.width())  / 2 * self.zoom_level)
        cvy = (self.pan_offset.y()
               + (self.height() / self.zoom_level - self.canvas.height()) / 2 * self.zoom_level)
        return ((widget_pos.x() - cvx) / self.zoom_level,
                (widget_pos.y() - cvy) / self.zoom_level)

    def _hit_test(self, img_x, img_y):
        if self.interaction_tool != "selection":
            return -1, self.MODE_NONE

        handle_sz = self.HANDLE_SIZE / self.zoom_level
        margin    = handle_sz

        if self.selected_roi_index != -1:
            r    = self.rois[self.selected_roi_index]
            rect = QRectF(*r)
            corners = [
                (rect.topLeft(),     self.MODE_RESIZE_TL),
                (rect.topRight(),    self.MODE_RESIZE_TR),
                (rect.bottomLeft(),  self.MODE_RESIZE_BL),
                (rect.bottomRight(), self.MODE_RESIZE_BR),
            ]
            for pt, mode in corners:
                if QRectF(pt.x() - margin, pt.y() - margin,
                          handle_sz * 2, handle_sz * 2).contains(img_x, img_y):
                    return self.selected_roi_index, mode
            if rect.contains(img_x, img_y):
                return self.selected_roi_index, self.MODE_MOVE

        for i, r in enumerate(self.rois):
            if QRectF(*r).contains(img_x, img_y):
                return i, self.MODE_MOVE

        return -1, self.MODE_NONE

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
        avg_x = sum(d.x() for d in self._delta_history) / len(self._delta_history)
        avg_y = sum(d.y() for d in self._delta_history) / len(self._delta_history)
        self._velocity = QPointF(avg_x, avg_y)
        self._delta_history.clear()
        self._momentum_timer.start()

    def _momentum_tick(self):
        self._velocity *= _FRICTION
        speed = (self._velocity.x() ** 2 + self._velocity.y() ** 2) ** 0.5
        if speed < _MIN_VELOCITY:
            self._momentum_timer.stop()
            self._velocity = QPointF(0, 0)
            return
        self.pan_offset += self._velocity
        self.update()

    def _stop_momentum(self):
        self._momentum_timer.stop()
        self._velocity = QPointF(0, 0)

    # ------------------------------------------------------------------
    # Zoom helper (shared by wheel and pinch)
    # ------------------------------------------------------------------

    def _apply_zoom(self, factor, viewport_x, viewport_y):
        cvx = (self.pan_offset.x()
               + (self.width()  / self.zoom_level - self.canvas.width())  / 2 * self.zoom_level)
        cvy = (self.pan_offset.y()
               + (self.height() / self.zoom_level - self.canvas.height()) / 2 * self.zoom_level)
        canvas_x = (viewport_x - cvx) / self.zoom_level
        canvas_y = (viewport_y - cvy) / self.zoom_level

        self.zoom_level = max(0.1, min(10.0, self.zoom_level * factor))

        new_cvx = (self.pan_offset.x()
                   + (self.width()  / self.zoom_level - self.canvas.width())  / 2 * self.zoom_level)
        new_cvy = (self.pan_offset.y()
                   + (self.height() / self.zoom_level - self.canvas.height()) / 2 * self.zoom_level)

        self.pan_offset.setX(self.pan_offset.x()
                             + (viewport_x - canvas_x * self.zoom_level) - new_cvx)
        self.pan_offset.setY(self.pan_offset.y()
                             + (viewport_y - canvas_y * self.zoom_level) - new_cvy)
        self.update()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def event(self, ev):
        from PyQt5.QtCore import QEvent
        if ev.type() == QEvent.Gesture:
            return self._handle_gesture(ev)
        return super().event(ev)

    def _handle_gesture(self, ev):
        pinch = ev.gesture(Qt.PinchGesture)
        if pinch:
            center = pinch.centerPoint()
            self._stop_momentum()
            self._apply_zoom(pinch.scaleFactor(),
                             center.x(), center.y())
            ev.accept()
            return True
        return False

    def wheelEvent(self, event: QWheelEvent):
        self._stop_momentum()

        # Trackpad two-finger scroll (synthesized events carry both axes).
        # Qt.MouseEventSynthesizedBySystem covers macOS and Windows precision
        # touchpads; Qt.MouseEventSynthesizedByQt covers some Linux setups.
        is_trackpad = event.source() in (Qt.MouseEventSynthesizedBySystem,
                                         Qt.MouseEventSynthesizedByQt)

        if event.modifiers() & Qt.ControlModifier:
            # Ctrl+scroll zooms regardless of device.
            factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self._apply_zoom(factor, event.pos().x(), event.pos().y())
            return

        if is_trackpad:
            # Two-finger pan: apply both axes directly.
            dx = event.pixelDelta().x() or event.angleDelta().x() / 8
            dy = event.pixelDelta().y() or event.angleDelta().y() / 8
            self.pan_offset += QPointF(dx, dy)
            self._record_delta(dx, dy)
            self.update()
        else:
            # Mouse wheel: vertical scroll only.
            self.pan_offset.setY(self.pan_offset.y()
                                 + event.angleDelta().y() * 0.5)
            self.update()

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
            self.current_creation_rect = None
            self.interaction_mode = self.MODE_NONE
            self.update()
            return

        if self.interaction_mode != self.MODE_NONE:
            if self.selected_roi_index != -1:
                self.roi_changed.emit(self.selected_roi_index,
                                      tuple(self.rois[self.selected_roi_index]))
            self.interaction_mode = self.MODE_NONE

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
            self.pan_offset  += delta
            self._record_delta(delta.x(), delta.y())
            self.last_mouse_pos = event.pos()
            self.update()
            return

        img_x, img_y = self._get_image_coords(event.pos())

        if self.interaction_mode == self.MODE_CREATE:
            sx, sy = self.creation_start_pos
            w, h   = img_x - sx, img_y - sy
            self.current_creation_rect = QRectF(
                sx if w > 0 else img_x, sy if h > 0 else img_y,
                abs(w), abs(h)
            )
            self.update()
            if self.hover_preview_enabled:
                if 0 <= img_x < self.canvas.width() and 0 <= img_y < self.canvas.height():
                    self.pixel_hovered.emit(int(img_x), int(img_y))
            return

        if self.interaction_mode != self.MODE_NONE and self.selected_roi_index != -1:
            r  = list(self.rois[self.selected_roi_index])
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

            r[2] = max(5, r[2]); r[3] = max(5, r[3])
            self.rois[self.selected_roi_index] = tuple(r)
            self.last_mouse_pos = event.pos()
            self.update()
            return

        if self.interaction_tool == "selection":
            _, mode = self._hit_test(img_x, img_y)
            cursors = {
                self.MODE_MOVE:      Qt.SizeAllCursor,
                self.MODE_RESIZE_TL: Qt.SizeFDiagCursor,
                self.MODE_RESIZE_BR: Qt.SizeFDiagCursor,
                self.MODE_RESIZE_TR: Qt.SizeBDiagCursor,
                self.MODE_RESIZE_BL: Qt.SizeBDiagCursor,
            }
            self.setCursor(cursors.get(mode, self.tool_cursor))

        if self.hover_preview_enabled:
            if 0 <= img_x < self.canvas.width() and 0 <= img_y < self.canvas.height():
                self.pixel_hovered.emit(int(img_x), int(img_y))

    def keyPressEvent(self, event: QKeyEvent):
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


# ------------------------------------------------------------------
# ImageCanvas
# ------------------------------------------------------------------

class ImageCanvas(QWidget):
    """Canvas that holds the image data (size reference)."""

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


# ------------------------------------------------------------------
# DualCanvasContainer
# ------------------------------------------------------------------

class DualCanvasContainer(QWidget):
    """
    Manages both single and split-screen canvas modes.
    Forwards all signals from active canvas(es).
    """

    scene_dropped = pyqtSignal(str)
    pixel_hovered = pyqtSignal(int, int)
    roi_changed   = pyqtSignal(int, tuple, str)
    roi_selected  = pyqtSignal(int)
    roi_deleted   = pyqtSignal(int)
    roi_created   = pyqtSignal(tuple, str)

    def __init__(self):
        super().__init__()
        self.is_split_mode = False
        self.homography_matrix         = None
        self.inverse_homography_matrix = None

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)

        self.canvas_single = CanvasContainer()
        self._connect_canvas_signals(self.canvas_single)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet(f"""
            QSplitter::handle       {{ background-color: {Colors.PANEL_ACCENT}; }}
            QSplitter::handle:hover {{ background-color: {Colors.ACCENT}; }}
        """)

        self.canvas_left  = CanvasContainer()
        self.canvas_right = CanvasContainer()
        self._connect_canvas_signals(self.canvas_left)
        self._connect_canvas_signals(self.canvas_right)

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

    def _on_canvas_roi_changed(self, source, roi_index, rect):
        camera = ('left'  if source is self.canvas_left  else
                  'right' if source is self.canvas_right else 'single')
        self.roi_changed.emit(roi_index, rect, camera)

    def _on_canvas_roi_created(self, source, rect):
        camera = ('left'  if source is self.canvas_left  else
                  'right' if source is self.canvas_right else 'single')
        self.roi_created.emit(rect, camera)

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
                roi_dicts = [{'roi': r} for r in self.canvas_right.rois]
                self.canvas_single.set_rois(roi_dicts, self.canvas_right.roi_colors)

    def set_homography_matrix(self, homography_matrix):
        import cv2
        self.homography_matrix = homography_matrix
        if homography_matrix is not None:
            self.inverse_homography_matrix = cv2.invert(homography_matrix)[1]

    def set_camera_images(self, left_pixmap, right_pixmap):
        if self.is_split_mode:
            self.canvas_left.set_image(left_pixmap)
            self.canvas_right.set_image(right_pixmap)
        else:
            self.canvas_single.set_image(right_pixmap)

    def _transform_roi_to_left(self, roi_tuple):
        if self.inverse_homography_matrix is None:
            return roi_tuple
        import cv2
        x, y, w, h = roi_tuple
        corners = np.array([[x, y], [x+w, y], [x+w, y+h], [x, y+h]],
                           dtype=np.float32).reshape(-1, 1, 2)
        tc = cv2.perspectiveTransform(corners, self.inverse_homography_matrix).reshape(-1, 2)
        xl, yl = tc[:, 0].min(), tc[:, 1].min()
        return (xl, yl, tc[:, 0].max() - xl, tc[:, 1].max() - yl)

    def set_rois(self, rois, colors=None):
        if self.is_split_mode:
            self.canvas_right.set_rois(rois, colors)
            left_rois = []
            for roi_data in rois:
                if 'left_rect' in roi_data:
                    left_rois.append({'roi': roi_data['left_rect']})
                elif self.homography_matrix is not None:
                    left_rois.append({'roi': self._transform_roi_to_left(
                        tuple(map(float, roi_data['roi'])))})
                else:
                    left_rois.append({'roi': roi_data['roi']})
            self.canvas_left.set_rois(left_rois, colors)
        else:
            self.canvas_single.set_rois(rois, colors)

    def set_tool_cursor(self, cursor):
        for c in self._active_canvases():
            c.set_tool_cursor(cursor)

    def set_hover_preview_enabled(self, enabled):
        for c in self._active_canvases():
            c.set_hover_preview_enabled(enabled)

    def set_image(self, pixmap):
        if self.is_split_mode:
            self.canvas_right.set_image(pixmap)
        else:
            self.canvas_single.set_image(pixmap)

    def set_tool(self, tool_name):
        for c in self._active_canvases():
            c.set_tool(tool_name)

    def _active_canvases(self):
        if self.is_split_mode:
            return (self.canvas_left, self.canvas_right)
        return (self.canvas_single,)
    
    def fit_focused_canvas(self, focused_camera: str):
        canvas = {'single': self.canvas_single,
                'left':   self.canvas_left,
                'right':  self.canvas_right}[focused_camera]
        canvas.fit_to_panel()

    @property
    def canvas(self):
        if self.is_split_mode:
            return self.canvas_left.canvas
        return self.canvas_single.canvas