from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QPoint, QTimer
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QKeyEvent, QMouseEvent, QWheelEvent

from colors import Colors


class CanvasContainer(QWidget):
    """Container for canvas with pan and zoom."""
    
    scene_dropped = pyqtSignal(str)
    pixel_hovered = pyqtSignal(int, int)
    
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {Colors.APP_BACKGROUND};")
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.setMouseTracking(True)
        
        self.zoom_level = 1.0
        self.pan_offset = QPointF(0, 0)
        self.is_panning = False
        self.last_pan_pos = QPoint()
        self.space_pressed = False
        
        self.canvas = ImageCanvas()
        self.canvas.setMouseTracking(True)
        
        self.canvas.scene_dropped.connect(self.scene_dropped.emit)
        
        self.setAcceptDrops(True)
        
        self.tool_cursor = Qt.ArrowCursor
        
        self.hover_preview_enabled = False
    
    def set_image(self, pixmap):
        """Sets image on canvas."""
        self.canvas.set_image(pixmap)
        self.update()
    
    def setCursor(self, cursor):
        """Overrides setCursor to store tool cursor."""
        if not self.is_panning and not self.space_pressed:
            self.tool_cursor = cursor
        super().setCursor(cursor)
    
    def paintEvent(self, event):
        """Draws background and canvas."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        painter.fillRect(self.rect(), QColor(Colors.APP_BACKGROUND))
        
        painter.save()
        painter.translate(self.pan_offset)
        painter.scale(self.zoom_level, self.zoom_level)
        
        canvas_x = (self.width() / self.zoom_level - self.canvas.width()) / 2
        canvas_y = (self.height() / self.zoom_level - self.canvas.height()) / 2
        
        painter.fillRect(
            int(canvas_x),
            int(canvas_y),
            self.canvas.width(),
            self.canvas.height(),
            QColor(255, 255, 255)
        )
        
        if self.canvas.image is not None:
            painter.drawPixmap(int(canvas_x), int(canvas_y), self.canvas.image)
        
        painter.restore()
    
    def wheelEvent(self, event: QWheelEvent):
        """Handles zoom and pan."""
        modifiers = event.modifiers()
        
        if modifiers & Qt.ControlModifier:
            delta = event.angleDelta().y()
            zoom_factor = 1.1 if delta > 0 else 0.9
            
            mouse_viewport_x = event.pos().x()
            mouse_viewport_y = event.pos().y()
            
            canvas_viewport_x = self.pan_offset.x() + (self.width() / self.zoom_level - self.canvas.width()) / 2 * self.zoom_level
            canvas_viewport_y = self.pan_offset.y() + (self.height() / self.zoom_level - self.canvas.height()) / 2 * self.zoom_level
            
            mouse_canvas_x = (mouse_viewport_x - canvas_viewport_x) / self.zoom_level
            mouse_canvas_y = (mouse_viewport_y - canvas_viewport_y) / self.zoom_level
            
            self.zoom_level *= zoom_factor
            self.zoom_level = max(0.1, min(10.0, self.zoom_level))
            
            new_canvas_viewport_x = self.pan_offset.x() + (self.width() / self.zoom_level - self.canvas.width()) / 2 * self.zoom_level
            new_canvas_viewport_y = self.pan_offset.y() + (self.height() / self.zoom_level - self.canvas.height()) / 2 * self.zoom_level
            
            desired_canvas_viewport_x = mouse_viewport_x - mouse_canvas_x * self.zoom_level
            desired_canvas_viewport_y = mouse_viewport_y - mouse_canvas_y * self.zoom_level
            
            self.pan_offset.setX(self.pan_offset.x() + (desired_canvas_viewport_x - new_canvas_viewport_x))
            self.pan_offset.setY(self.pan_offset.y() + (desired_canvas_viewport_y - new_canvas_viewport_y))
            
            self.update()
        else:
            delta = event.angleDelta().y()
            self.pan_offset.setY(self.pan_offset.y() + delta * 0.5)
            self.update()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handles mouse move for panning and hover."""
        if self.is_panning:
            delta = event.pos() - self.last_pan_pos
            self.pan_offset += delta
            self.last_pan_pos = event.pos()
            self.update()
        elif self.hover_preview_enabled and self.canvas.image is not None:
            mouse_x = event.pos().x()
            mouse_y = event.pos().y()
            
            canvas_viewport_x = self.pan_offset.x() + (self.width() / self.zoom_level - self.canvas.width()) / 2 * self.zoom_level
            canvas_viewport_y = self.pan_offset.y() + (self.height() / self.zoom_level - self.canvas.height()) / 2 * self.zoom_level
            
            canvas_x = int((mouse_x - canvas_viewport_x) / self.zoom_level)
            canvas_y = int((mouse_y - canvas_viewport_y) / self.zoom_level)
            
            if 0 <= canvas_x < self.canvas.width() and 0 <= canvas_y < self.canvas.height():
                self.pixel_hovered.emit(canvas_x, canvas_y)
    
    def set_hover_preview_enabled(self, enabled):
        """Enables or disables hover preview."""
        self.hover_preview_enabled = enabled
    
    def mousePressEvent(self, event: QMouseEvent):
        """Starts panning."""
        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and self.space_pressed):
            self.is_panning = True
            self.last_pan_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Stops panning."""
        if event.button() == Qt.MiddleButton or event.button() == Qt.LeftButton:
            self.is_panning = False
            if self.space_pressed:
                super().setCursor(Qt.OpenHandCursor)
            else:
                super().setCursor(self.tool_cursor)
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handles space for panning."""
        if event.key() == Qt.Key_Space and not self.space_pressed:
            self.space_pressed = True
            if not self.is_panning:
                self.setCursor(Qt.OpenHandCursor)
    
    def keyReleaseEvent(self, event: QKeyEvent):
        """Releases space panning."""
        if event.key() == Qt.Key_Space:
            self.space_pressed = False
            if not self.is_panning:
                super().setCursor(self.tool_cursor)
    
    def dragEnterEvent(self, event):
        """Accepts drag events."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """Handles drop event."""
        if event.mimeData().hasText():
            scene_id = event.mimeData().text()
            event.acceptProposedAction()
            
            QTimer.singleShot(0, lambda: self.scene_dropped.emit(scene_id))


class ImageCanvas(QWidget):
    """Canvas that holds the image."""
    
    scene_dropped = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        
        self.image = None
        
        self.canvas_width = 1648
        self.canvas_height = 1214
        self.setFixedSize(self.canvas_width, self.canvas_height)
        
        self.setAcceptDrops(True)
    
    def set_image(self, pixmap):
        """Sets image and resizes canvas."""
        self.image = pixmap
        if pixmap is not None:
            self.canvas_width = pixmap.width()
            self.canvas_height = pixmap.height()
            self.setFixedSize(self.canvas_width, self.canvas_height)
        if self.parent():
            self.parent().update()
    
    def width(self):
        """Returns canvas width."""
        return self.canvas_width
    
    def height(self):
        """Returns canvas height."""
        return self.canvas_height
    
    def dragEnterEvent(self, event):
        """Accepts drag events."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """Handles drop event."""
        if event.mimeData().hasText():
            scene_id = event.mimeData().text()
            event.acceptProposedAction()
            
            QTimer.singleShot(0, lambda: self.scene_dropped.emit(scene_id))