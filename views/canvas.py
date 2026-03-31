from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QPoint, QRectF, QRect, QTimer
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QSplitter
from PyQt5.QtGui import QPainter, QColor, QKeyEvent, QMouseEvent, QWheelEvent, QPen, QCursor

from colors import Colors
import numpy as np


class CanvasContainer(QWidget):
    """
    Container for canvas with pan, zoom, and interactive ROI editing.
    """
    
    scene_dropped = pyqtSignal(str)
    pixel_hovered = pyqtSignal(int, int)
    
    # ROI Signals
    roi_changed = pyqtSignal(int, tuple)  # (index, (x, y, w, h))
    roi_selected = pyqtSignal(int)        # (index)
    roi_deleted = pyqtSignal(int)         # (index)
    roi_created = pyqtSignal(tuple)       # ((x, y, w, h))
    
    # Interaction Modes
    MODE_NONE = 0
    MODE_MOVE = 1
    MODE_RESIZE_TL = 2 
    MODE_RESIZE_TR = 3 
    MODE_RESIZE_BL = 4 
    MODE_RESIZE_BR = 5 
    MODE_CREATE = 6 # New mode for drawing
    
    HANDLE_SIZE = 8
    
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {Colors.APP_BACKGROUND};")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        
        # Navigation State
        self.zoom_level = 1.0
        self.pan_offset = QPointF(0, 0)
        self.is_panning = False
        self.last_mouse_pos = QPoint()
        self.space_pressed = False
        
        # Cursor State
        self.tool_cursor = Qt.ArrowCursor
        
        # ROI State
        self.rois = [] # List of tuples (x, y, w, h)
        self.roi_colors = [] # List of RGB tuples
        self.selected_roi_index = -1
        
        # Interaction State
        self.interaction_mode = self.MODE_NONE
        self.interaction_tool = "selection"
        self.creation_start_pos = None
        self.current_creation_rect = None
        
        self.canvas = ImageCanvas()
        self.canvas.setMouseTracking(True)
        self.canvas.scene_dropped.connect(self.scene_dropped.emit)
        
        self.setAcceptDrops(True)
        self.hover_preview_enabled = False
    
    def set_tool_cursor(self, cursor):
        """Sets the cursor for the active tool."""
        self.tool_cursor = cursor
        self.setCursor(cursor)

    def set_hover_preview_enabled(self, enabled):
        """Enables or disables hover preview."""
        self.hover_preview_enabled = enabled

    def set_image(self, pixmap):
        """Sets image on canvas."""
        self.canvas.set_image(pixmap)
        self.update()

    def set_rois(self, rois, colors=None):
        """Sets the list of ROIs to display/edit."""
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
    
    def paintEvent(self, event):
        """Draws background, image, and dynamic ROIs."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # 1. Background
        painter.fillRect(self.rect(), QColor(Colors.APP_BACKGROUND))
        
        painter.save()
        
        # 2. Transform (Pan/Zoom)
        painter.translate(self.pan_offset)
        painter.scale(self.zoom_level, self.zoom_level)
        
        # Center canvas
        canvas_x = (self.width() / self.zoom_level - self.canvas.width()) / 2
        canvas_y = (self.height() / self.zoom_level - self.canvas.height()) / 2
        
        # 3. Draw Image Frame
        painter.fillRect(
            int(canvas_x), int(canvas_y),
            self.canvas.width(), self.canvas.height(),
            QColor(255, 255, 255)
        )
        
        if self.canvas.image is not None:
            painter.drawPixmap(int(canvas_x), int(canvas_y), self.canvas.image)
            
        # 4. Draw ROIs
        painter.translate(canvas_x, canvas_y)
        self._draw_rois(painter)
        
        # 5. Draw Creation Rect
        if self.interaction_mode == self.MODE_CREATE and self.current_creation_rect:
            pen = QPen(QColor(Colors.ACCENT), 2 / self.zoom_level)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.current_creation_rect)
        
        painter.restore()
        
        # 6. Draw Zoom Indicator (in screen space)
        self._draw_zoom_indicator(painter)

    def _draw_rois(self, painter):
        """Draws the ROI rectangles and handles."""
        handle_sz = self.HANDLE_SIZE / self.zoom_level
        
        for i, rect_tuple in enumerate(self.rois):
            x, y, w, h = rect_tuple
            rect = QRectF(x, y, w, h)
            
            # Determine Color
            if i < len(self.roi_colors):
                rgb = self.roi_colors[i]
                base_color = QColor(*rgb)
            else:
                base_color = QColor(Colors.ACCENT)
                
            if i == self.selected_roi_index and self.interaction_tool == "selection":
                # Draw Selected
                pen_selected = QPen(QColor("#FFFFFF"), 2 / self.zoom_level)
                pen_selected.setStyle(Qt.DashLine)
                
                brush_roi = QColor(base_color)
                brush_roi.setAlpha(80)
                
                painter.setPen(pen_selected)
                painter.setBrush(brush_roi)
                painter.drawRect(rect)
                
                # Handles
                painter.setPen(QPen(QColor("black"), 1 / self.zoom_level))
                painter.setBrush(QColor("white"))
                
                handles = [rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()]
                for pt in handles:
                    painter.drawRect(QRectF(
                        pt.x() - handle_sz/2, pt.y() - handle_sz/2,
                        handle_sz, handle_sz
                    ))
            else:
                # Draw Idle
                pen_idle = QPen(base_color, 2 / self.zoom_level)
                brush_roi = QColor(base_color)
                brush_roi.setAlpha(60)
                
                painter.setPen(pen_idle)
                painter.setBrush(brush_roi)
                painter.drawRect(rect)

    def _draw_zoom_indicator(self, painter):
        """Draws zoom level indicator in bottom-right corner."""
        # Format zoom text
        zoom_text = f"{self.zoom_level:.2f}x"
        
        # Set font
        from PyQt5.QtGui import QFont
        font = QFont("Arial", 11)
        painter.setFont(font)
        
        # Measure text size
        from PyQt5.QtGui import QFontMetrics
        metrics = QFontMetrics(font)
        text_width = metrics.horizontalAdvance("10.00x")  # Max width for zoom up to 10x
        text_height = metrics.height()
        
        # Position in bottom-right corner with padding
        padding = 10
        margin = 8  # Internal padding
        box_width = text_width + 2 * margin
        box_height = text_height + 2 * margin
        
        x = self.width() - box_width - padding
        y = self.height() - box_height - padding
        
        # Draw semi-transparent background
        bg_color = QColor(40, 40, 40, 180)  # Dark gray with alpha
        painter.fillRect(x, y, box_width, box_height, bg_color)
        
        # Draw text
        painter.setPen(QColor(255, 255, 255))  # White text
        text_x = x + margin
        text_y = y + margin + metrics.ascent()
        painter.drawText(text_x, text_y, zoom_text)

    def _get_image_coords(self, widget_pos):
        canvas_viewport_x = self.pan_offset.x() + (self.width() / self.zoom_level - self.canvas.width()) / 2 * self.zoom_level
        canvas_viewport_y = self.pan_offset.y() + (self.height() / self.zoom_level - self.canvas.height()) / 2 * self.zoom_level
        
        img_x = (widget_pos.x() - canvas_viewport_x) / self.zoom_level
        img_y = (widget_pos.y() - canvas_viewport_y) / self.zoom_level
        return img_x, img_y

    def _hit_test(self, img_x, img_y):
        if self.interaction_tool != "selection":
            return -1, self.MODE_NONE

        handle_sz = self.HANDLE_SIZE / self.zoom_level
        margin = handle_sz 

        if self.selected_roi_index != -1:
            r = self.rois[self.selected_roi_index]
            rect = QRectF(*r)
            
            if QRectF(rect.left()-margin, rect.top()-margin, handle_sz*2, handle_sz*2).contains(img_x, img_y):
                return self.selected_roi_index, self.MODE_RESIZE_TL
            if QRectF(rect.right()-margin, rect.top()-margin, handle_sz*2, handle_sz*2).contains(img_x, img_y):
                return self.selected_roi_index, self.MODE_RESIZE_TR
            if QRectF(rect.left()-margin, rect.bottom()-margin, handle_sz*2, handle_sz*2).contains(img_x, img_y):
                return self.selected_roi_index, self.MODE_RESIZE_BL
            if QRectF(rect.right()-margin, rect.bottom()-margin, handle_sz*2, handle_sz*2).contains(img_x, img_y):
                return self.selected_roi_index, self.MODE_RESIZE_BR
            
            if rect.contains(img_x, img_y):
                return self.selected_roi_index, self.MODE_MOVE

        for i, r in enumerate(self.rois):
            if QRectF(*r).contains(img_x, img_y):
                return i, self.MODE_MOVE
        
        return -1, self.MODE_NONE

    def mousePressEvent(self, event: QMouseEvent):
        self.last_mouse_pos = event.pos()

        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and self.space_pressed):
            self.is_panning = True
            self.setCursor(Qt.ClosedHandCursor)
            return

        img_x, img_y = self._get_image_coords(event.pos())

        # SELECTION TOOL
        if self.interaction_tool == "selection" and event.button() == Qt.LeftButton:
            idx, mode = self._hit_test(img_x, img_y)
            
            if idx != -1:
                self.selected_roi_index = idx
                self.interaction_mode = mode
                self.roi_selected.emit(idx)
                self.update()
                return
            else:
                if self.selected_roi_index != -1:
                    self.selected_roi_index = -1
                    self.update()
        
        # RECTANGLE TOOL (Creation)
        elif self.interaction_tool == "rectangle" and event.button() == Qt.LeftButton:
            self.interaction_mode = self.MODE_CREATE
            self.creation_start_pos = (img_x, img_y)
            self.current_creation_rect = QRectF(img_x, img_y, 0, 0)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_panning:
            delta = event.pos() - self.last_mouse_pos
            self.pan_offset += delta
            self.last_mouse_pos = event.pos()
            self.update()
            return

        img_x, img_y = self._get_image_coords(event.pos())
        
        # Handle Rectangle Creation
        if self.interaction_mode == self.MODE_CREATE:
            start_x, start_y = self.creation_start_pos
            w = img_x - start_x
            h = img_y - start_y
            
            # Normalize geometry (allow dragging up/left)
            rect_x = start_x if w > 0 else img_x
            rect_y = start_y if h > 0 else img_y
            rect_w = abs(w)
            rect_h = abs(h)
            
            self.current_creation_rect = QRectF(rect_x, rect_y, rect_w, rect_h)
            self.update()
            
            # Emit hover for preview during creation if needed
            if self.hover_preview_enabled:
                if 0 <= img_x < self.canvas.width() and 0 <= img_y < self.canvas.height():
                    self.pixel_hovered.emit(int(img_x), int(img_y))
            return

        # Handle Selection Edit (Move/Resize)
        if self.interaction_mode != self.MODE_NONE and self.selected_roi_index != -1:
            current_rect = list(self.rois[self.selected_roi_index])
            dx = img_x - self._get_image_coords(self.last_mouse_pos)[0]
            dy = img_y - self._get_image_coords(self.last_mouse_pos)[1]
            
            if self.interaction_mode == self.MODE_MOVE:
                current_rect[0] += dx
                current_rect[1] += dy
            elif self.interaction_mode == self.MODE_RESIZE_BR:
                current_rect[2] += dx
                current_rect[3] += dy
            elif self.interaction_mode == self.MODE_RESIZE_TL:
                current_rect[0] += dx
                current_rect[1] += dy
                current_rect[2] -= dx
                current_rect[3] -= dy
            elif self.interaction_mode == self.MODE_RESIZE_TR:
                current_rect[1] += dy
                current_rect[2] += dx
                current_rect[3] -= dy
            elif self.interaction_mode == self.MODE_RESIZE_BL:
                current_rect[0] += dx
                current_rect[2] -= dx
                current_rect[3] += dy

            # Enforce Min Size
            if current_rect[2] < 5: current_rect[2] = 5
            if current_rect[3] < 5: current_rect[3] = 5

            self.rois[self.selected_roi_index] = tuple(current_rect)
            self.last_mouse_pos = event.pos()
            self.update()
            return

        # Hover Cursor Logic
        if self.interaction_tool == "selection":
            idx, mode = self._hit_test(img_x, img_y)
            if mode == self.MODE_MOVE:
                self.setCursor(Qt.SizeAllCursor)
            elif mode in [self.MODE_RESIZE_TL, self.MODE_RESIZE_BR]:
                self.setCursor(Qt.SizeFDiagCursor)
            elif mode in [self.MODE_RESIZE_TR, self.MODE_RESIZE_BL]:
                self.setCursor(Qt.SizeBDiagCursor)
            else:
                self.setCursor(self.tool_cursor)
        
        # Hover Preview
        if self.hover_preview_enabled:
            if 0 <= img_x < self.canvas.width() and 0 <= img_y < self.canvas.height():
                self.pixel_hovered.emit(int(img_x), int(img_y))

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.is_panning:
            self.is_panning = False
            self.setCursor(Qt.OpenHandCursor if self.space_pressed else self.tool_cursor)
        
        # Finalize Creation
        if self.interaction_mode == self.MODE_CREATE:
            if self.current_creation_rect:
                r = self.current_creation_rect
                # Only create if large enough
                if r.width() > 5 and r.height() > 5:
                    self.roi_created.emit((r.x(), r.y(), r.width(), r.height()))
            self.current_creation_rect = None
            self.interaction_mode = self.MODE_NONE
            self.update()
            return

        # Finalize Edit
        if self.interaction_mode != self.MODE_NONE:
            if self.selected_roi_index != -1:
                self.roi_changed.emit(
                    self.selected_roi_index, 
                    tuple(self.rois[self.selected_roi_index])
                )
            self.interaction_mode = self.MODE_NONE

    def keyPressEvent(self, event: QKeyEvent):
        # Pan Mode
        if event.key() == Qt.Key_Space and not self.space_pressed:
            self.space_pressed = True
            if not self.is_panning:
                self.setCursor(Qt.OpenHandCursor)
        
        # Delete ROI
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
    
    def wheelEvent(self, event: QWheelEvent):
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

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        if event.mimeData().hasText():
            scene_id = event.mimeData().text()
            event.acceptProposedAction()
            QTimer.singleShot(0, lambda: self.scene_dropped.emit(scene_id))


class ImageCanvas(QWidget):
    """Canvas that holds the image data (size reference)."""
    scene_dropped = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.image = None
        self.canvas_width = 1648
        self.canvas_height = 1214
        self.setFixedSize(self.canvas_width, self.canvas_height)
        self.setAcceptDrops(True)
    
    def set_image(self, pixmap):
        self.image = pixmap
        if pixmap is not None:
            self.canvas_width = pixmap.width()
            self.canvas_height = pixmap.height()
            self.setFixedSize(self.canvas_width, self.canvas_height)
        if self.parent():
            self.parent().update()
            
    def width(self): return self.canvas_width
    def height(self): return self.canvas_height

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        if event.mimeData().hasText():
            scene_id = event.mimeData().text()
            event.acceptProposedAction()
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.scene_dropped.emit(scene_id))


class DualCanvasContainer(QWidget):
    """
    Container that manages both single and split-screen canvas modes.
    In split mode, left canvas shows left camera, right canvas shows right camera.
    Forwards all signals from active canvas(es) to maintain compatibility.
    """
    
    # Forward all signals from CanvasContainer
    scene_dropped = pyqtSignal(str)
    pixel_hovered = pyqtSignal(int, int)
    roi_changed = pyqtSignal(int, tuple)
    roi_selected = pyqtSignal(int)
    roi_deleted = pyqtSignal(int)
    roi_created = pyqtSignal(tuple)
    
    def __init__(self):
        super().__init__()
        self.is_split_mode = False
        
        # Store homography for ROI transformation
        self.homography_matrix = None
        self.inverse_homography_matrix = None
        
        # Create layout
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)
        
        # Create single canvas
        self.canvas_single = CanvasContainer()
        self._connect_canvas_signals(self.canvas_single)
        
        # Create split canvases (initially hidden)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Colors.PANEL_ACCENT};
            }}
            QSplitter::handle:hover {{
                background-color: {Colors.ACCENT};
            }}
        """)
        
        self.canvas_left = CanvasContainer()
        self.canvas_right = CanvasContainer()
        self._connect_canvas_signals(self.canvas_left)
        self._connect_canvas_signals(self.canvas_right)
        
        self.splitter.addWidget(self.canvas_left)
        self.splitter.addWidget(self.canvas_right)
        self.splitter.setSizes([500, 500])  # Equal split by default
        
        # Start in single mode
        self.layout.addWidget(self.canvas_single)
        self.splitter.hide()
    
    def _connect_canvas_signals(self, canvas):
        """Connect canvas signals to forward them."""
        canvas.scene_dropped.connect(self.scene_dropped.emit)
        canvas.pixel_hovered.connect(self.pixel_hovered.emit)
        canvas.roi_selected.connect(self.roi_selected.emit)
        canvas.roi_deleted.connect(self.roi_deleted.emit)
        
        # For roi_changed and roi_created, we need to know which canvas emitted it
        # so we can transform coordinates appropriately
        canvas.roi_changed.connect(lambda idx, rect, c=canvas: self._on_canvas_roi_changed(c, idx, rect))
        canvas.roi_created.connect(lambda rect, c=canvas: self._on_canvas_roi_created(c, rect))
    
    def set_split_mode(self, split_mode):
        """Toggle between single and split-screen mode."""
        if split_mode == self.is_split_mode:
            return
        
        self.is_split_mode = split_mode
        
        if split_mode:
            # Switch to split mode
            self.layout.removeWidget(self.canvas_single)
            self.canvas_single.hide()
            self.layout.addWidget(self.splitter)
            self.splitter.show()
            
            # Images are set externally via set_camera_images
            # ROIs are set externally via set_rois which handles transformation
        else:
            # Switch to single mode
            self.layout.removeWidget(self.splitter)
            self.splitter.hide()
            self.layout.addWidget(self.canvas_single)
            self.canvas_single.show()
            
            # Sync from right canvas back to single (right is the reference)
            if self.canvas_right.canvas.image is not None:
                self.canvas_single.set_image(self.canvas_right.canvas.image)
            
            if self.canvas_right.rois:
                roi_dicts = [{'roi': r} for r in self.canvas_right.rois]
                self.canvas_single.set_rois(roi_dicts, self.canvas_right.roi_colors)
    
    def _on_canvas_roi_changed(self, source_canvas, roi_index, rect):
        """
        Handle ROI change from a specific canvas.
        Transform coordinates if from left canvas to right camera space.
        """
        if self.is_split_mode and source_canvas == self.canvas_left:
            # ROI changed on left canvas - transform to right camera space
            transformed_rect = self._transform_roi_to_right(rect)
            self.roi_changed.emit(roi_index, transformed_rect)
        else:
            # ROI changed on right canvas or single mode - use as-is
            self.roi_changed.emit(roi_index, rect)
    
    def _on_canvas_roi_created(self, source_canvas, rect):
        """
        Handle ROI creation from a specific canvas.
        Transform coordinates if from left canvas to right camera space.
        """
        if self.is_split_mode and source_canvas == self.canvas_left:
            # ROI created on left canvas - transform to right camera space
            transformed_rect = self._transform_roi_to_right(rect)
            self.roi_created.emit(transformed_rect)
        else:
            # ROI created on right canvas or single mode - use as-is
            self.roi_created.emit(rect)
    
    # Forward all methods to active canvas(es)
    
    def set_homography_matrix(self, homography_matrix):
        """
        Set the homography matrix for ROI transformation.
        This matrix maps left camera to right camera coordinates.
        """
        self.homography_matrix = homography_matrix
        if homography_matrix is not None:
            import cv2
            self.inverse_homography_matrix = cv2.invert(homography_matrix)[1]
    
    def set_camera_images(self, left_pixmap, right_pixmap):
        """
        Set separate images for left and right cameras in split mode.
        Only affects split mode - single mode uses the right image.
        """
        if self.is_split_mode:
            self.canvas_left.set_image(left_pixmap)
            self.canvas_right.set_image(right_pixmap)
        else:
            # Single mode uses right camera
            self.canvas_single.set_image(right_pixmap)
    
    def _transform_roi_to_left(self, roi_tuple):
        """
        Transform ROI from right camera space to left camera space.
        Uses inverse homography matrix.
        """
        if self.inverse_homography_matrix is None:
            return roi_tuple
        
        import cv2
        x, y, w, h = roi_tuple
        
        # Get four corners of the ROI rectangle in right camera space
        corners_right = np.array([
            [x, y],
            [x + w, y],
            [x + w, y + h],
            [x, y + h]
        ], dtype=np.float32).reshape(-1, 1, 2)
        
        # Transform corners to left camera space
        corners_left = cv2.perspectiveTransform(corners_right, self.inverse_homography_matrix)
        corners_left = corners_left.reshape(-1, 2)
        
        # Find bounding box in left camera space
        x_left = corners_left[:, 0].min()
        y_left = corners_left[:, 1].min()
        x_right = corners_left[:, 0].max()
        y_right = corners_left[:, 1].max()
        
        w_left = x_right - x_left
        h_left = y_right - y_left
        
        return (x_left, y_left, w_left, h_left)
    
    def _transform_roi_to_right(self, roi_tuple):
        """
        Transform ROI from left camera space to right camera space.
        Uses forward homography matrix.
        """
        if self.homography_matrix is None:
            return roi_tuple
        
        import cv2
        x, y, w, h = roi_tuple
        
        # Get four corners of the ROI rectangle in left camera space
        corners_left = np.array([
            [x, y],
            [x + w, y],
            [x + w, y + h],
            [x, y + h]
        ], dtype=np.float32).reshape(-1, 1, 2)
        
        # Transform corners to right camera space
        corners_right = cv2.perspectiveTransform(corners_left, self.homography_matrix)
        corners_right = corners_right.reshape(-1, 2)
        
        # Find bounding box in right camera space
        x_left = corners_right[:, 0].min()
        y_left = corners_right[:, 1].min()
        x_right = corners_right[:, 0].max()
        y_right = corners_right[:, 1].max()
        
        w_right = x_right - x_left
        h_right = y_right - y_left
        
        return (x_left, y_left, w_right, h_right)
    
    # Forward all methods to active canvas(es)
    
    def set_tool_cursor(self, cursor):
        """Forward to active canvas(es)."""
        if self.is_split_mode:
            self.canvas_left.set_tool_cursor(cursor)
            self.canvas_right.set_tool_cursor(cursor)
        else:
            self.canvas_single.set_tool_cursor(cursor)
    
    def set_hover_preview_enabled(self, enabled):
        """Forward to active canvas(es)."""
        if self.is_split_mode:
            self.canvas_left.set_hover_preview_enabled(enabled)
            self.canvas_right.set_hover_preview_enabled(enabled)
        else:
            self.canvas_single.set_hover_preview_enabled(enabled)
    
    def set_image(self, pixmap):
        """
        Forward to active canvas(es).
        In split mode, this only updates the right canvas (use set_camera_images for both).
        """
        if self.is_split_mode:
            # In split mode, only update right canvas when set_image is called
            # (set_camera_images should be used for proper split-screen)
            self.canvas_right.set_image(pixmap)
        else:
            self.canvas_single.set_image(pixmap)
    
    def set_rois(self, rois, colors=None):
        """
        Forward to active canvas(es).
        In split mode, ROIs are in right camera space and are transformed for left camera.
        """
        if self.is_split_mode:
            # Right canvas gets ROIs as-is (they're in right camera space)
            self.canvas_right.set_rois(rois, colors)
            
            # Left canvas needs transformed ROIs
            if self.homography_matrix is not None:
                transformed_rois = []
                for roi_data in rois:
                    roi_tuple = tuple(map(float, roi_data['roi']))
                    transformed_roi = self._transform_roi_to_left(roi_tuple)
                    transformed_rois.append({'roi': transformed_roi})
                self.canvas_left.set_rois(transformed_rois, colors)
            else:
                # No homography available, just use same ROIs
                self.canvas_left.set_rois(rois, colors)
        else:
            self.canvas_single.set_rois(rois, colors)
    
    def set_tool(self, tool_name):
        """Forward to active canvas(es)."""
        if self.is_split_mode:
            self.canvas_left.set_tool(tool_name)
            self.canvas_right.set_tool(tool_name)
        else:
            self.canvas_single.set_tool(tool_name)
    
    @property
    def canvas(self):
        """Return the active canvas for compatibility with existing code."""
        if self.is_split_mode:
            return self.canvas_left.canvas
        else:
            return self.canvas_single.canvas