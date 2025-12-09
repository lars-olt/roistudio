from PyQt5.QtCore import QRect, Qt, pyqtSignal, QSize, QPoint, QPointF, QMimeData, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QColor, QWheelEvent, QKeyEvent, QMouseEvent, QDrag, QCursor, QIcon, QMovie
from PyQt5.QtWidgets import (QAction, QFrame, QHBoxLayout, QLabel, QMenu,
                             QMenuBar, QPushButton, QScrollArea, QSplitter,
                             QVBoxLayout, QWidget, QGridLayout, QTextEdit, QComboBox)

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np

from colors import Colors


class SpectralViewPanel(QWidget):
    """
    panel for displaying spectral plots with matplotlib.
    minimal and elegant design matching spec_anal_suite style.
    """
    def __init__(self):
        super().__init__()
        self.roi_spectra_data = None  # stores ROI spectra to persist
        self.init_ui()
    
    def init_ui(self):
        """
        creates the spectral view panel with matplotlib canvas.
        """
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        
        # create matplotlib figure and canvas
        self.figure = Figure(figsize=(8, 4), facecolor=Colors.PANEL_BACKGROUND)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setStyleSheet(f"background-color: {Colors.PANEL_BACKGROUND};")
        
        # create axis
        self.ax = self.figure.add_subplot(111)
        self.setup_plot_style()
        
        layout.addWidget(self.canvas)
    
    def setup_plot_style(self):
        """
        configures the plot styling to match app theme.
        """
        # backgrounds
        self.ax.set_facecolor(Colors.DEFAULT_FEATURE)
        self.figure.patch.set_facecolor(Colors.PANEL_BACKGROUND)
        
        # axis labels
        self.ax.set_xlabel('Wavelength (nm)', color=Colors.TEXT_PRIMARY, fontsize=10)
        self.ax.set_ylabel('R* = IOF/cos(θ)', color=Colors.TEXT_PRIMARY, fontsize=10)
        
        # fixed y-axis range
        self.ax.set_ylim(0, 0.4)
        
        # styling
        self.ax.tick_params(colors=Colors.TEXT_PRIMARY, labelsize=9)
        for spine in self.ax.spines.values():
            spine.set_edgecolor(Colors.PANEL_ACCENT)
            spine.set_linewidth(1)
        
        # subtle grid
        self.ax.grid(True, alpha=0.2, color=Colors.TEXT_SECONDARY, linestyle='--', linewidth=0.5)
        
        self.figure.tight_layout()
    
    def plot_roi_spectra(self, roi_data_list, color_list):
        """
        plots ROI spectra and stores them for persistence.
        
        parameters:
            roi_data_list : list of dicts with spectrum data
            color_list : list of RGB tuples
        """
        self.roi_spectra_data = (roi_data_list, color_list)
        self.ax.clear()
        self.setup_plot_style()
        
        for i, roi_data in enumerate(roi_data_list):
            color = color_list[i % len(color_list)]
            color_normalized = tuple(c / 255.0 for c in color)
            
            # non-bayer: solid line with markers and error bars
            wavelengths = roi_data['wavelengths']
            spectrum = roi_data['spectrum']
            std = roi_data['std']
            
            self.ax.errorbar(wavelengths, spectrum, yerr=std,
                            color=color_normalized, linewidth=2, 
                            marker='o', markersize=4,
                            capsize=3, capthick=1, elinewidth=1)
            
            # bayer: dots only with error bars
            bayer_wls = roi_data['bayer_wavelengths']
            bayer_spec = roi_data['bayer_spectrum']
            bayer_std = roi_data['bayer_std']
            
            self.ax.errorbar(bayer_wls, bayer_spec, yerr=bayer_std,
                            color=color_normalized, linestyle='', 
                            marker='o', markersize=4,
                            capsize=3, capthick=1, elinewidth=1)
        
        self.canvas.draw()
    
    def plot_preview_spectrum(self, wavelengths, reflectances):
        """
        plots a faint preview spectrum for hover, overlaid on ROI spectra.
        """
        # redraw ROI spectra first if they exist
        if self.roi_spectra_data is not None:
            roi_data_list, color_list = self.roi_spectra_data
            self.ax.clear()
            self.setup_plot_style()
            
            # plot ROI spectra
            for i, roi_data in enumerate(roi_data_list):
                color = color_list[i % len(color_list)]
                color_normalized = tuple(c / 255.0 for c in color)
                
                # non-bayer
                wls = roi_data['wavelengths']
                spec = roi_data['spectrum']
                std = roi_data['std']
                
                self.ax.errorbar(wls, spec, yerr=std,
                                color=color_normalized, linewidth=2, 
                                marker='o', markersize=4,
                                capsize=3, capthick=1, elinewidth=1)
                
                # bayer
                bayer_wls = roi_data['bayer_wavelengths']
                bayer_spec = roi_data['bayer_spectrum']
                bayer_std = roi_data['bayer_std']
                
                self.ax.errorbar(bayer_wls, bayer_spec, yerr=bayer_std,
                                color=color_normalized, linestyle='', 
                                marker='o', markersize=4,
                                capsize=3, capthick=1, elinewidth=1)
        else:
            # no ROI spectra, just clear
            self.ax.clear()
            self.setup_plot_style()
        
        # overlay preview spectrum
        self.ax.plot(wavelengths, reflectances, 
                    color='white', linewidth=1, alpha=0.3,
                    marker='o', markersize=3, zorder=100)
        
        self.canvas.draw()
        
    def plot_preview_spectrum_separate(self, wavelengths, reflectances, bayer_wls, bayer_reflectances):
        """
        plots a faint preview spectrum with separate handling for Bayer bands.
        """
        # redraw ROI spectra first if they exist
        if self.roi_spectra_data is not None:
            roi_data_list, color_list = self.roi_spectra_data
            self.ax.clear()
            self.setup_plot_style()
            
            # plot ROI spectra
            for i, roi_data in enumerate(roi_data_list):
                color = color_list[i % len(color_list)]
                color_normalized = tuple(c / 255.0 for c in color)
                
                # non-bayer with line
                wls = roi_data['wavelengths']
                spec = roi_data['spectrum']
                std = roi_data['std']
                
                self.ax.errorbar(wls, spec, yerr=std,
                                color=color_normalized, linewidth=2, 
                                marker='o', markersize=4,
                                capsize=3, capthick=1, elinewidth=1)
                
                # bayer as dots only
                bayer_wls = roi_data['bayer_wavelengths']
                bayer_spec = roi_data['bayer_spectrum']
                bayer_std = roi_data['bayer_std']
                
                self.ax.errorbar(bayer_wls, bayer_spec, yerr=bayer_std,
                                color=color_normalized, linestyle='', 
                                marker='o', markersize=4,
                                capsize=3, capthick=1, elinewidth=1)
        else:
            # no ROI spectra, just clear
            self.ax.clear()
            self.setup_plot_style()
        
        # overlay preview spectrum - non-Bayer with line
        self.ax.plot(wavelengths, reflectances, 
                    color='white', linewidth=1, alpha=0.3,
                    marker='o', markersize=3, zorder=100)
        
        # overlay preview spectrum - Bayer as dots only
        self.ax.plot(bayer_wls, bayer_reflectances,
                    color='white', linestyle='', alpha=0.3,
                    marker='o', markersize=3, zorder=100)
        
        self.canvas.draw()
    
    def hide_preview(self):
        """
        hides preview spectrum, showing only ROI spectra.
        """
        if self.roi_spectra_data is not None:
            roi_data_list, color_list = self.roi_spectra_data
            self.plot_roi_spectra(roi_data_list, color_list)
        else:
            self.clear_plot()
    
    def clear_roi_spectra(self):
        """clears stored ROI spectra."""
        self.roi_spectra_data = None
    
    def clear_plot(self):
        """clears the plot."""
        self.ax.clear()
        self.setup_plot_style()
        self.canvas.draw()


class ImageSelectionPanel(QFrame):
    """
    custom panel for image selection that handles resize events.
    """
    resized = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def resizeEvent(self, event):
        """
        emits signal when panel is resized.
        """
        super().resizeEvent(event)
        self.resized.emit()


class LoadingIndicator(QLabel):
    """
    animated loading indicator that displays in menu bar.
    small and non-intrusive.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # load animated GIF
        self.movie = QMovie("graphics/load.gif")
        self.setMovie(self.movie)
        
        # set small size for menu bar (30x30)
        self.setFixedSize(30, 30)
        self.setScaledContents(True)
        
        # maintain size policy even when hidden
        size_policy = self.sizePolicy()
        size_policy.setRetainSizeWhenHidden(True)
        self.setSizePolicy(size_policy)
        
        # style for menu bar
        self.setStyleSheet("""
            QLabel {
                background-color: transparent;
                padding: 0px;
                margin: 0px;
            }
        """)
        
        # hide by default but keep space reserved
        self.setVisible(False)
    
    def start_loading(self):
        """
        shows indicator and starts animation.
        """
        self.movie.start()
        self.setVisible(True)
    
    def stop_loading(self):
        """
        stops animation and hides indicator.
        """
        self.movie.stop()
        self.setVisible(False)


class ToolbarButton(QPushButton):
    """
    custom button for toolbar with normal and selected state icons.
    """
    def __init__(self, normal_icon_path, selected_icon_path, parent=None):
        super().__init__(parent)
        self.normal_icon = QIcon(normal_icon_path)
        self.selected_icon = QIcon(selected_icon_path)
        self.is_selected = False
        
        # set button properties
        self.setFixedSize(46, 38)
        self.setCheckable(True)
        self.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background-color: transparent;
            }}
        """)
        
        # set initial icon
        self.update_icon()
    
    def update_icon(self):
        """
        updates the button icon based on selection state.
        """
        if self.is_selected or self.isChecked():
            self.setIcon(self.selected_icon)
        else:
            self.setIcon(self.normal_icon)
        self.setIconSize(QSize(46, 38))
    
    def set_selected(self, selected):
        """
        sets the selection state and updates icon.
        """
        self.is_selected = selected
        self.setChecked(selected)
        self.update_icon()


class CanvasContainer(QWidget):
    """
    container for canvas with pan and zoom navigation for the whole viewport.
    similar to photoshop's canvas view.
    """
    scene_dropped = pyqtSignal(str)  # emits scene_id when dropped
    pixel_hovered = pyqtSignal(int, int)  # emits (x, y) canvas coordinates on hover
    
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {Colors.APP_BACKGROUND};")
        self.setFocusPolicy(Qt.StrongFocus)
        
        # enable mouse tracking for hover events
        self.setMouseTracking(True)
        
        # navigation state
        self.zoom_level = 1.0
        self.pan_offset = QPointF(0, 0)
        self.is_panning = False
        self.last_pan_pos = QPoint()
        self.space_pressed = False
        
        # canvas (white frame with fixed Mastcam-Z size)
        self.canvas = ImageCanvas()
        self.canvas.setMouseTracking(True)  # enable tracking on child too
        
        # forward canvas drop events
        self.canvas.scene_dropped.connect(self.scene_dropped.emit)
        
        # enable drop on container too
        self.setAcceptDrops(True)
        
        # store tool cursor for restoration after pan
        self.tool_cursor = Qt.ArrowCursor
        
        # track if hover preview is enabled
        self.hover_preview_enabled = False
        
    def set_image(self, pixmap):
        """
        sets image on canvas.
        """
        self.canvas.set_image(pixmap)
        self.update()
    
    def setCursor(self, cursor):
        """
        overrides setCursor to store tool cursor for restoration.
        """
        if not self.is_panning and not self.space_pressed:
            self.tool_cursor = cursor
        super().setCursor(cursor)
    
    def paintEvent(self, event):
        """
        draws the dark background and transformed canvas.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # fill background dark
        painter.fillRect(self.rect(), QColor(Colors.APP_BACKGROUND))
        
        # apply transformations
        painter.save()
        painter.translate(self.pan_offset)
        painter.scale(self.zoom_level, self.zoom_level)
        
        # center canvas in viewport
        canvas_x = (self.width() / self.zoom_level - self.canvas.width()) / 2
        canvas_y = (self.height() / self.zoom_level - self.canvas.height()) / 2
        
        # draw the white canvas frame
        painter.fillRect(
            int(canvas_x), 
            int(canvas_y), 
            self.canvas.width(), 
            self.canvas.height(),
            QColor(255, 255, 255)
        )
        
        # draw the image if it exists (no centering since canvas matches image size)
        if self.canvas.image is not None:
            painter.drawPixmap(int(canvas_x), int(canvas_y), self.canvas.image)
        
        painter.restore()
    
    def wheelEvent(self, event: QWheelEvent):
        """
        handles zoom (ctrl+scroll) and pan (scroll).
        """
        modifiers = event.modifiers()
        
        if modifiers & Qt.ControlModifier:
            # ctrl + scroll = zoom
            delta = event.angleDelta().y()
            zoom_factor = 1.1 if delta > 0 else 0.9
            
            # get mouse position in viewport
            mouse_viewport_x = event.pos().x()
            mouse_viewport_y = event.pos().y()
            
            # calculate where canvas is currently positioned in viewport (before zoom)
            canvas_viewport_x = self.pan_offset.x() + (self.width() / self.zoom_level - self.canvas.width()) / 2 * self.zoom_level
            canvas_viewport_y = self.pan_offset.y() + (self.height() / self.zoom_level - self.canvas.height()) / 2 * self.zoom_level
            
            # convert mouse position to canvas-relative coordinates (before zoom)
            mouse_canvas_x = (mouse_viewport_x - canvas_viewport_x) / self.zoom_level
            mouse_canvas_y = (mouse_viewport_y - canvas_viewport_y) / self.zoom_level
            
            # apply zoom
            self.zoom_level *= zoom_factor
            self.zoom_level = max(0.1, min(10.0, self.zoom_level))
            
            # calculate new canvas position in viewport (after zoom)
            new_canvas_viewport_x = self.pan_offset.x() + (self.width() / self.zoom_level - self.canvas.width()) / 2 * self.zoom_level
            new_canvas_viewport_y = self.pan_offset.y() + (self.height() / self.zoom_level - self.canvas.height()) / 2 * self.zoom_level
            
            # calculate where the same canvas point should be in viewport to stay under mouse
            desired_canvas_viewport_x = mouse_viewport_x - mouse_canvas_x * self.zoom_level
            desired_canvas_viewport_y = mouse_viewport_y - mouse_canvas_y * self.zoom_level
            
            # adjust pan offset by the difference
            self.pan_offset.setX(self.pan_offset.x() + (desired_canvas_viewport_x - new_canvas_viewport_x))
            self.pan_offset.setY(self.pan_offset.y() + (desired_canvas_viewport_y - new_canvas_viewport_y))
            
            self.update()
        else:
            # regular scroll = vertical pan
            delta = event.angleDelta().y()
            self.pan_offset.setY(self.pan_offset.y() + delta * 0.5)
            self.update()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """
        handles mouse move for panning and hover preview.
        """
        if self.is_panning:
            # handle panning
            delta = event.pos() - self.last_pan_pos
            self.pan_offset += delta
            self.last_pan_pos = event.pos()
            self.update()
        elif self.hover_preview_enabled and self.canvas.image is not None:
            # convert mouse position to canvas coordinates
            mouse_x = event.pos().x()
            mouse_y = event.pos().y()
            
            # calculate canvas position in viewport
            canvas_viewport_x = self.pan_offset.x() + (self.width() / self.zoom_level - self.canvas.width()) / 2 * self.zoom_level
            canvas_viewport_y = self.pan_offset.y() + (self.height() / self.zoom_level - self.canvas.height()) / 2 * self.zoom_level
            
            # convert to canvas coordinates
            canvas_x = int((mouse_x - canvas_viewport_x) / self.zoom_level)
            canvas_y = int((mouse_y - canvas_viewport_y) / self.zoom_level)
            
            # check if within canvas bounds
            if 0 <= canvas_x < self.canvas.width() and 0 <= canvas_y < self.canvas.height():
                self.pixel_hovered.emit(canvas_x, canvas_y)

    def set_hover_preview_enabled(self, enabled):
        """
        enables or disables hover spectral preview.
        """
        self.hover_preview_enabled = enabled
    
    def mousePressEvent(self, event: QMouseEvent):
        """
        starts panning on middle mouse or space+left mouse.
        """
        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and self.space_pressed):
            self.is_panning = True
            self.last_pan_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """
        handles panning drag.
        """
        if self.is_panning:
            delta = event.pos() - self.last_pan_pos
            self.pan_offset += delta
            self.last_pan_pos = event.pos()
            self.update()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """
        stops panning and restores tool cursor.
        """
        if event.button() == Qt.MiddleButton or event.button() == Qt.LeftButton:
            self.is_panning = False
            if self.space_pressed:
                super().setCursor(Qt.OpenHandCursor)
            else:
                super().setCursor(self.tool_cursor)
    
    def keyPressEvent(self, event: QKeyEvent):
        """
        handles space bar for panning mode.
        """
        if event.key() == Qt.Key_Space and not self.space_pressed:
            self.space_pressed = True
            if not self.is_panning:
                self.setCursor(Qt.OpenHandCursor)
    
    def keyReleaseEvent(self, event: QKeyEvent):
        """
        releases space bar panning mode and restores tool cursor.
        """
        if event.key() == Qt.Key_Space:
            self.space_pressed = False
            if not self.is_panning:
                super().setCursor(self.tool_cursor)
    
    def dragEnterEvent(self, event):
        """
        accepts drag events with text mime data (scene_id).
        """
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """
        handles drop event on container (dark background area).
        """
        if event.mimeData().hasText():
            scene_id = event.mimeData().text()
            event.acceptProposedAction()
            
            # emit signal after event completes to prevent cursor blocking
            QTimer.singleShot(0, lambda: self.scene_dropped.emit(scene_id))


class ImageCanvas(QWidget):
    """
    white canvas frame that holds the image.
    resizes to match loaded image.
    accepts drag-and-drop of scenes.
    """
    scene_dropped = pyqtSignal(str)  # emits scene_id when dropped
    
    def __init__(self):
        super().__init__()
        
        # image data
        self.image = None
        
        # default Mastcam-Z image size (1648x1214)
        self.canvas_width = 1648
        self.canvas_height = 1214
        self.setFixedSize(self.canvas_width, self.canvas_height)
        
        # enable drop events
        self.setAcceptDrops(True)
    
    def set_image(self, pixmap):
        """
        sets the image to display and resizes canvas to match.
        """
        self.image = pixmap
        if pixmap is not None:
            # resize canvas to match image
            self.canvas_width = pixmap.width()
            self.canvas_height = pixmap.height()
            self.setFixedSize(self.canvas_width, self.canvas_height)
        # trigger repaint of parent container
        if self.parent():
            self.parent().update()
    
    def width(self):
        """returns canvas width."""
        return self.canvas_width
    
    def height(self):
        """returns canvas height."""
        return self.canvas_height
    
    def dragEnterEvent(self, event):
        """
        accepts drag events with text mime data (scene_id).
        """
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """
        handles drop event and emits scene_id asynchronously.
        """
        if event.mimeData().hasText():
            scene_id = event.mimeData().text()
            event.acceptProposedAction()
            
            # emit signal after event completes to prevent cursor blocking
            QTimer.singleShot(0, lambda: self.scene_dropped.emit(scene_id))


class ImageEditingPanel(QWidget):
    """
    panel for image editing with algorithm dropdown and canvas.
    """
    run_algorithm_signal = pyqtSignal(str)  # emits algorithm name
    scene_dropped_signal = pyqtSignal(str)  # emits scene_id when dropped
    spectral_preview_signal = pyqtSignal(int, int)  # emits (x, y) for pixel hover
    tool_changed_signal = pyqtSignal(str)  # emits tool name when changed
    
    def __init__(self):
        super().__init__()
        self.current_tool = "selection"  # default tool
        self.init_ui()
        
        # install event filter to catch mouse move events on canvas
        self.canvas_container.installEventFilter(self)
    
    def init_ui(self):
        """
        creates the image editing panel layout.
        """
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        
        # top bar with dropdown and run button
        top_bar = QWidget()
        top_bar.setStyleSheet(f"background-color: {Colors.PANEL_ACCENT}; border-bottom: 1px solid {Colors.DEFAULT_FEATURE};")
        top_bar.setMaximumHeight(35)
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(8, 4, 8, 4)
        top_bar_layout.setSpacing(8)
        top_bar.setLayout(top_bar_layout)
        
        # algorithm dropdown
        self.algorithm_dropdown = QComboBox()
        self.algorithm_dropdown.addItems([
            "full algorithm",
            "masked",
            "sam",
            "decorrelation",
            "composite"
        ])
        self.algorithm_dropdown.setStyleSheet(f"""
            QComboBox {{
                background-color: {Colors.PANEL_ACCENT};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.PANEL_ACCENT};
                border-radius: 3px;
                padding: 4px 8px;
                min-width: 120px;
            }}
            QComboBox:hover {{
                border: 1px solid {Colors.ACCENT};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid {Colors.TEXT_PRIMARY};
                margin-right: 4px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT};
                border: 1px solid {Colors.PANEL_ACCENT};
            }}
        """)
        top_bar_layout.addWidget(self.algorithm_dropdown)
        
        # run button
        self.run_button = QPushButton("Run")
        self.run_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.ACCENT};
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Colors.ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {Colors.ACCENT_PRESSED};
            }}
        """)
        self.run_button.clicked.connect(self.on_run_clicked)
        top_bar_layout.addWidget(self.run_button)
        
        top_bar_layout.addStretch()
        
        layout.addWidget(top_bar)
        
        # main content area with toolbar and canvas
        content_widget = QWidget()
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_widget.setLayout(content_layout)
        
        # left toolbar with tool buttons
        self.toolbar = QWidget()
        self.toolbar.setStyleSheet(f"background-color: {Colors.PANEL_ACCENT}; border-right: 1px solid {Colors.DEFAULT_FEATURE};")
        self.toolbar.setMaximumWidth(54)
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_layout.setSpacing(4)
        self.toolbar.setLayout(toolbar_layout)
        
        # selection tool button
        self.btn_selection = ToolbarButton(
            "graphics/toolbar_selection.png",
            "graphics/toolbar_selection_selected.png"
        )
        self.btn_selection.set_selected(True)  # default selected
        self.btn_selection.clicked.connect(lambda: self.select_tool("selection"))
        toolbar_layout.addWidget(self.btn_selection)
        
        # rectangle tool button
        self.btn_rectangle = ToolbarButton(
            "graphics/toolbar_rectangle.png",
            "graphics/toolbar_rectangle_selected.png"
        )
        self.btn_rectangle.clicked.connect(lambda: self.select_tool("rectangle"))
        toolbar_layout.addWidget(self.btn_rectangle)
        
        toolbar_layout.addStretch()
        
        content_layout.addWidget(self.toolbar)
        
        # canvas container (handles pan/zoom for entire viewport)
        self.canvas_container = CanvasContainer()
        self.canvas_container.scene_dropped.connect(self.scene_dropped_signal.emit)
        content_layout.addWidget(self.canvas_container)
        
        layout.addWidget(content_widget)
        
        # set initial cursor for selection tool
        self.update_cursor()
    
    def select_tool(self, tool_name):
        """
        selects a tool and updates toolbar button states and cursor.
        
        parameters:
            tool_name : str
                name of tool ("selection" or "rectangle")
        """
        self.current_tool = tool_name
        
        # update button states
        self.btn_selection.set_selected(tool_name == "selection")
        self.btn_rectangle.set_selected(tool_name == "rectangle")
        
        # enable hover preview only for rectangle tool
        self.canvas_container.set_hover_preview_enabled(tool_name == "rectangle")
        
        # emit signal for tool change
        self.tool_changed_signal.emit(tool_name)
        
        # update cursor
        self.update_cursor()
    
    def update_cursor(self):
        """
        updates the canvas container cursor based on current tool.
        """
        if self.current_tool == "selection":
            # load custom selection cursor
            cursor_pixmap = QPixmap("graphics/selection.png")
            cursor = QCursor(cursor_pixmap, 0, 0)  # hotspot at top-left
            self.canvas_container.setCursor(cursor)
        elif self.current_tool == "rectangle":
            # use crosshair cursor
            self.canvas_container.setCursor(Qt.CrossCursor)
    
    def eventFilter(self, obj, event):
        """
        filters events on canvas_container to detect mouse moves.
        """
        if obj == self.canvas_container and event.type() == event.MouseMove:
            # the event is already a QMouseEvent when type is MouseMove
            # directly process it here instead of calling mouseMoveEvent
            if self.current_tool == "rectangle" and self.canvas_container.canvas.image is not None:
                # get mouse position relative to canvas_container
                mouse_pos = event.pos()
                
                # convert to canvas coordinates using canvas_container's transform
                canvas_container = self.canvas_container
                zoom = canvas_container.zoom_level
                pan = canvas_container.pan_offset
                canvas = canvas_container.canvas
                
                # calculate canvas position in viewport
                canvas_viewport_x = pan.x() + (canvas_container.width() / zoom - canvas.width()) / 2 * zoom
                canvas_viewport_y = pan.y() + (canvas_container.height() / zoom - canvas.height()) / 2 * zoom
                
                # convert to canvas coordinates
                canvas_x = int((mouse_pos.x() - canvas_viewport_x) / zoom)
                canvas_y = int((mouse_pos.y() - canvas_viewport_y) / zoom)
                
                # check if within canvas bounds
                if 0 <= canvas_x < canvas.width() and 0 <= canvas_y < canvas.height():
                    canvas_container.pixel_hovered.emit(canvas_x, canvas_y)
            
            return False  # let event propagate
        return super().eventFilter(obj, event)
    
    def on_run_clicked(self):
        """
        emits signal when run button is clicked.
        """
        algorithm = self.algorithm_dropdown.currentText()
        self.run_algorithm_signal.emit(algorithm)
    
    def set_image(self, pixmap):
        """
        sets image on canvas.
        """
        self.canvas_container.set_image(pixmap)


class View(QWidget):
    """
    sets up the UI of ROIStudio.
    """
    # signals for functionality
    load_cube_signal = pyqtSignal()
    set_sam_path_signal = pyqtSignal()
    open_folder_signal = pyqtSignal()
    run_algorithm_signal = pyqtSignal(str)  # emits algorithm name
    scene_dropped_signal = pyqtSignal(str)  # emits scene_id when dropped on canvas

    def __init__(self):
        super().__init__()
        self.selected_scene_id = None
        self.scene_thumbnails = {}  # maps scene_id to thumbnail widget
        self.init_ui()

    def init_ui(self):
        """
        creates all visual components of GUI.
        """
        self.setWindowTitle('ROIStudio')
        self.resize(1600, 900)

        # main layout
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)

        # menu bar
        self.menubar = QMenuBar()
        self.menubar.setGeometry(QRect(0, 0, 1600, 25))
        self.menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {Colors.PANEL_ACCENT};
                color: {Colors.TEXT_PRIMARY};
                border-bottom: 1px solid {Colors.PANEL_ACCENT};
                padding: 2px;
            }}
            QMenuBar::item {{
                padding: 4px 12px;
                background: transparent;
            }}
            QMenuBar::item:selected {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
            }}
            QMenu {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.PANEL_ACCENT};
            }}
            QMenu::item:selected {{
                background-color: {Colors.ACCENT};
            }}
        """)
        self.layout.setMenuBar(self.menubar)

        # create menu items
        self.menu_file = QMenu("File", self.menubar)
        self.menubar.addMenu(self.menu_file)

        # add Set SAM Path action
        self.action_set_sam_path = QAction("Set SAM Path", self)
        self.action_set_sam_path.triggered.connect(self.set_sam_path_signal.emit)
        self.menu_file.addAction(self.action_set_sam_path)
        
        # add Open Folder action
        self.action_open_folder = QAction("Open Folder", self)
        self.action_open_folder.triggered.connect(self.open_folder_signal.emit)
        self.menu_file.addAction(self.action_open_folder)

        self.menu_edit = QMenu("Edit", self.menubar)
        self.menubar.addMenu(self.menu_edit)

        self.menu_window = QMenu("Window", self.menubar)
        self.menubar.addMenu(self.menu_window)
        
        # add loading indicator to right side of menu bar
        # use a container to control sizing and prevent menu bar expansion
        corner_widget = QWidget()
        corner_layout = QHBoxLayout()
        corner_layout.setContentsMargins(0, 0, 8, 0)  # 8px from right edge
        corner_layout.setSpacing(0)
        corner_widget.setLayout(corner_layout)
        corner_widget.setStyleSheet("background-color: transparent;")
        
        self.loading_indicator = LoadingIndicator(corner_widget)
        corner_layout.addWidget(self.loading_indicator)
        
        self.menubar.setCornerWidget(corner_widget, Qt.TopRightCorner)

        # create 2x2 panel grid with splitters
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(1)
        self.main_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Colors.PANEL_ACCENT};
            }}
            QSplitter::handle:hover {{
                background-color: {Colors.ACCENT};
            }}
        """)

        # left column splitter (top/bottom)
        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.setHandleWidth(1)
        self.left_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Colors.PANEL_ACCENT};
            }}
            QSplitter::handle:hover {{
                background-color: {Colors.ACCENT};
            }}
        """)

        # right column splitter (top/bottom)
        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.setHandleWidth(1)
        self.right_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {Colors.PANEL_ACCENT};
            }}
            QSplitter::handle:hover {{
                background-color: {Colors.ACCENT};
            }}
        """)

        # create four panels
        self.panel_image_selection = self.create_image_selection_panel()
        self.panel_parameter_selection = self.create_panel()
        self.panel_image_editing = ImageEditingPanel()
        self.panel_spectral_view = SpectralViewPanel()

        # add panels to splitters
        self.left_splitter.addWidget(self.panel_image_selection)
        self.left_splitter.addWidget(self.panel_spectral_view)

        self.right_splitter.addWidget(self.panel_image_editing)
        self.right_splitter.addWidget(self.panel_parameter_selection)

        # add column splitters to main splitter
        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.right_splitter)

        # set initial sizes: left 35%, right 65%
        total_width = 1600
        self.main_splitter.setSizes([int(total_width * 0.35), 
                                     int(total_width * 0.65)])

        # add main splitter to layout
        self.layout.addWidget(self.main_splitter)

        # status bar at bottom with logo
        status_container = QWidget()
        status_container.setMaximumHeight(60)
        status_container.setStyleSheet(f"background-color: {Colors.DEFAULT_FEATURE}; border-top: 1px solid {Colors.PANEL_ACCENT};")
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)
        status_container.setLayout(status_layout)
        
        # mastcam-z logo on left
        logo_label = QLabel()
        logo_pixmap = QPixmap("graphics/mcz_logo.png")
        # scale down to be subtle (32x32)
        logo_pixmap = logo_pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("padding: 8px;")
        status_layout.addWidget(logo_label)
        
        # status text area
        self.status_bar = QTextEdit()
        self.status_bar.setReadOnly(True)
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
        status_layout.addWidget(self.status_bar)
        
        self.layout.addWidget(status_container)
        
        # connect image editing panel signals
        self.panel_image_editing.run_algorithm_signal.connect(self.run_algorithm_signal.emit)
        self.panel_image_editing.scene_dropped_signal.connect(self.scene_dropped_signal.emit)
        self.panel_image_editing.canvas_container.pixel_hovered.connect(self.on_pixel_hovered)
        self.panel_image_editing.tool_changed_signal.connect(self.on_tool_changed)
    
    def start_loading(self):
        """
        shows loading indicator.
        """
        self.loading_indicator.start_loading()
    
    def stop_loading(self):
        """
        hides loading indicator.
        """
        self.loading_indicator.stop_loading()
    
    def on_pixel_hovered(self, x, y):
        """
        handles pixel hover event and requests spectral data from controller.
        emits signal that controller can connect to.
        
        parameters:
            x, y : int
                pixel coordinates on canvas
        """
        # forward to any connected handlers (controller will handle)
        if hasattr(self, 'pixel_hover_callback'):
            self.pixel_hover_callback(x, y)
    
    def on_tool_changed(self, tool_name):
        """
        handles tool change event from image editing panel.
        hides preview spectrum when selection tool is active.
        
        parameters:
            tool_name : str
                name of the selected tool
        """
        if tool_name == "selection":
            self.panel_spectral_view.hide_preview()

    def create_image_selection_panel(self):
        """
        creates image selection panel with open folder, thumbnail grid, and load scene buttons.

        returns:
            panel : ImageSelectionPanel
                styled panel widget with image selection functionality
        """
        panel = ImageSelectionPanel()
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.PANEL_BACKGROUND};
                border: 1px solid {Colors.PANEL_ACCENT};
            }}
        """)
        
        # connect resize signal to update thumbnails
        panel.resized.connect(self.update_thumbnail_sizes)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        panel.setLayout(layout)

        # scrollable thumbnail grid
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {Colors.PANEL_BACKGROUND};
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {Colors.DEFAULT_FEATURE};
                width: 12px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
                min-height: 20px;
                border-radius: 6px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {Colors.PANEL_ACCENT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background-color: {Colors.DEFAULT_FEATURE};
                height: 12px;
                margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
                min-width: 20px;
                border-radius: 6px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {Colors.PANEL_ACCENT};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """)

        # container for thumbnails
        self.thumbnail_container = QWidget()
        self.thumbnail_layout = QGridLayout()
        self.thumbnail_layout.setSpacing(10)
        self.thumbnail_layout.setContentsMargins(10, 10, 10, 10)
        self.thumbnail_layout.setAlignment(Qt.AlignTop)  # stack rows from top
        self.thumbnail_container.setLayout(self.thumbnail_layout)
        
        # store original pixmaps and filenames for rescaling
        self.thumbnail_pixmaps = {}  # scene_id -> original pixmap
        self.thumbnail_filenames = {}  # scene_id -> filename text
        
        scroll_area.setWidget(self.thumbnail_container)
        layout.addWidget(scroll_area)

        return panel

    def create_panel(self):
        """
        creates a blank panel frame.

        returns:
            panel : QFrame
                styled panel widget
        """
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.PANEL_BACKGROUND};
                border: 1px solid {Colors.PANEL_ACCENT};
            }}
        """)
        
        # empty layout for future content
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        panel.setLayout(layout)
        
        return panel

    def add_scene_thumbnail(self, scene_id, pixmap, filename):
        """
        adds a thumbnail to the grid.

        parameters:
            scene_id : str
                unique identifier for the scene
            pixmap : QPixmap
                thumbnail image
            filename : str
                filename to display below thumbnail
        """
        # store original pixmap for rescaling
        self.thumbnail_pixmaps[scene_id] = pixmap
        self.thumbnail_filenames[scene_id] = filename
        
        # calculate thumbnail size based on current width
        thumb_size = self.calculate_thumbnail_size()
        
        # create thumbnail widget
        thumb_widget = QWidget()
        thumb_widget.setProperty("scene_id", scene_id)  # store for later updates
        label_height = 45
        thumb_widget.setFixedSize(thumb_size, thumb_size + label_height + 5)
        thumb_layout = QVBoxLayout()
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(5)
        thumb_widget.setLayout(thumb_layout)

        # clickable label for image
        thumb_label = ClickableLabel()
        scaled_pixmap = pixmap.scaled(
            thumb_size, thumb_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        thumb_label.setPixmap(scaled_pixmap)
        thumb_label.setFixedSize(thumb_size, thumb_size)
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setStyleSheet(f"""
            QLabel {{
                background-color: {Colors.DEFAULT_FEATURE};
                border: 2px solid {Colors.PANEL_ACCENT};
            }}
        """)
        thumb_label.clicked.connect(lambda: self.select_scene(scene_id))
        
        # set scene data for drag-and-drop
        thumb_label.set_scene_data(scene_id, scaled_pixmap)
        
        thumb_layout.addWidget(thumb_label)

        # filename label - smaller text, constrained width to image width
        name_label = QLabel(filename)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setFixedWidth(thumb_size)
        name_label.setMaximumHeight(label_height)
        name_label.setSizePolicy(name_label.sizePolicy().Fixed, 
                                 name_label.sizePolicy().Minimum)
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 8pt;
            }}
        """)
        thumb_layout.addWidget(name_label)

        # store references
        self.scene_thumbnails[scene_id] = thumb_label

        # calculate column layout
        cols = self.calculate_column_count()
        num_items = len(self.scene_thumbnails)
        col = (num_items - 1) % cols
        row = (num_items - 1) // cols
        self.thumbnail_layout.addWidget(thumb_widget, row, col, Qt.AlignTop)
    
    def calculate_thumbnail_size(self):
        """
        calculates thumbnail size based on available width.
        
        returns:
            int : thumbnail size in pixels
        """
        available_width = self.panel_image_selection.width() - 40  # account for margins/scrollbar
        cols = self.calculate_column_count()
        spacing = 10 * (cols + 1)  # spacing between columns
        thumb_size = (available_width - spacing) // cols
        
        # clamp between 180 and 400 pixels
        return max(180, min(400, thumb_size))
    
    def calculate_column_count(self):
        """
        calculates number of columns based on available width.
        
        returns:
            int : number of columns (1 or 2)
        """
        available_width = self.panel_image_selection.width() - 40
        if available_width < 180:
            return 1
        elif available_width < 400:
            return 1  # single column if can't fit 2 at min size
        else:
            return 2  # two columns
    
    def update_thumbnail_sizes(self):
        """
        updates all thumbnail sizes when window is resized.
        """
        if not hasattr(self, 'thumbnail_pixmaps') or not self.thumbnail_pixmaps:
            return
        
        # calculate new size
        thumb_size = self.calculate_thumbnail_size()
        cols = self.calculate_column_count()
        label_height = 45
        
        # store currently selected scene to restore later
        selected_scene = self.selected_scene_id
        
        # clear layout
        for i in reversed(range(self.thumbnail_layout.count())):
            item = self.thumbnail_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)
        
        # clear thumbnail references
        self.scene_thumbnails.clear()
        
        # re-add all thumbnails with new sizes
        for idx, scene_id in enumerate(self.thumbnail_pixmaps.keys()):
            pixmap = self.thumbnail_pixmaps[scene_id]
            filename = self.thumbnail_filenames[scene_id]
            
            # create new widget with updated size
            thumb_widget = QWidget()
            thumb_widget.setProperty("scene_id", scene_id)
            thumb_widget.setFixedSize(thumb_size, thumb_size + label_height + 5)
            thumb_layout = QVBoxLayout()
            thumb_layout.setContentsMargins(0, 0, 0, 0)
            thumb_layout.setSpacing(5)
            thumb_widget.setLayout(thumb_layout)
            
            # create new thumbnail label
            thumb_label = ClickableLabel()
            scaled_pixmap = pixmap.scaled(
                thumb_size, thumb_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            thumb_label.setPixmap(scaled_pixmap)
            thumb_label.setFixedSize(thumb_size, thumb_size)
            thumb_label.setAlignment(Qt.AlignCenter)
            thumb_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {Colors.DEFAULT_FEATURE};
                    border: 2px solid {Colors.PANEL_ACCENT};
                }}
            """)
            thumb_label.clicked.connect(lambda sid=scene_id: self.select_scene(sid))
            thumb_label.set_scene_data(scene_id, scaled_pixmap)
            thumb_layout.addWidget(thumb_label)
            
            # create filename label
            name_label = QLabel(filename)
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)
            name_label.setFixedWidth(thumb_size)
            name_label.setMaximumHeight(label_height)
            name_label.setSizePolicy(name_label.sizePolicy().Fixed, 
                                     name_label.sizePolicy().Minimum)
            name_label.setStyleSheet(f"""
                QLabel {{
                    color: {Colors.TEXT_PRIMARY};
                    font-size: 8pt;
                }}
            """)
            thumb_layout.addWidget(name_label)
            
            # store reference
            self.scene_thumbnails[scene_id] = thumb_label
            
            # add to grid
            col = idx % cols
            row = idx // cols
            self.thumbnail_layout.addWidget(thumb_widget, row, col, Qt.AlignTop)
        
        # restore selection
        if selected_scene:
            self.select_scene(selected_scene)

    def select_scene(self, scene_id):
        """
        selects a scene and highlights it.

        parameters:
            scene_id : str
                unique identifier for the scene
        """
        # deselect all
        for sid, label in self.scene_thumbnails.items():
            if sid == scene_id:
                label.setStyleSheet(f"""
                    QLabel {{
                        background-color: {Colors.DEFAULT_FEATURE};
                        border: 2px solid {Colors.ACCENT};
                    }}
                """)
            else:
                label.setStyleSheet(f"""
                    QLabel {{
                        background-color: {Colors.DEFAULT_FEATURE};
                        border: 2px solid {Colors.PANEL_ACCENT};
                    }}
                """)

        self.selected_scene_id = scene_id

    def get_selected_scene(self):
        """
        returns the currently selected scene ID.

        returns:
            scene_id : str or None
        """
        return self.selected_scene_id

    def clear_thumbnails(self):
        """
        clears all thumbnails from the grid.
        """
        # remove all widgets from layout
        for i in reversed(range(self.thumbnail_layout.count())):
            self.thumbnail_layout.itemAt(i).widget().setParent(None)
        
        self.scene_thumbnails.clear()
        self.selected_scene_id = None

    def show_status_message(self, message):
        """
        displays a message in the status bar.

        parameters:
            message : str
                message to display
        """
        self.status_bar.append(f"> {message}")
        # auto-scroll to bottom
        self.status_bar.verticalScrollBar().setValue(
            self.status_bar.verticalScrollBar().maximum()
        )


class ClickableLabel(QLabel):
    """
    label that emits clicked signal when clicked and supports drag-and-drop.
    """
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene_id = None
        self.thumbnail_pixmap = None

    def mousePressEvent(self, event):
        """
        handles mouse press for click and drag start.
        """
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            self.drag_start_pos = event.pos()

    def mouseMoveEvent(self, event):
        """
        starts drag operation when mouse moves while pressed.
        """
        if not (event.buttons() & Qt.LeftButton):
            return
        
        if self.scene_id and self.thumbnail_pixmap:
            # start drag operation
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(self.scene_id)
            drag.setMimeData(mime_data)
            
            # set thumbnail as drag preview
            drag.setPixmap(self.thumbnail_pixmap)
            drag.setHotSpot(QPoint(self.thumbnail_pixmap.width() // 2, 
                                  self.thumbnail_pixmap.height() // 2))
            
            drag.exec_(Qt.CopyAction)

    def set_scene_data(self, scene_id, pixmap):
        """
        stores scene data for drag operation.
        """
        self.scene_id = scene_id
        self.thumbnail_pixmap = pixmap