from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                             QComboBox, QPushButton, QScrollArea, QGridLayout,
                             QLabel, QTextEdit, QDoubleSpinBox, QSpinBox, 
                             QCheckBox, QFormLayout)
from PyQt5.QtGui import QPixmap
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from colors import Colors
from .canvas import CanvasContainer
from .widgets import ToolbarButton, ClickableLabel, CollapsibleSection


class SpectralViewPanel(QWidget):
    """Panel for displaying spectral plots."""
    
    def __init__(self):
        super().__init__()
        self.roi_spectra_data = None
        self.y_min = 0.0
        self.y_max = 0.4
        self.init_ui()
    
    def init_ui(self):
        """Creates the spectral view panel."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        
        self.figure = Figure(figsize=(8, 4), facecolor=Colors.PANEL_BACKGROUND)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setStyleSheet(f"background-color: {Colors.PANEL_BACKGROUND};")
        
        self.ax = self.figure.add_subplot(111)
        self.setup_plot_style()
        
        layout.addWidget(self.canvas)
    
    def setup_plot_style(self):
        """Configures plot styling."""
        self.ax.set_facecolor(Colors.DEFAULT_FEATURE)
        self.figure.patch.set_facecolor(Colors.PANEL_BACKGROUND)
        
        self.ax.set_xlabel('Wavelength (nm)', color=Colors.TEXT_PRIMARY, fontsize=10)
        self.ax.set_ylabel('R* = IOF/cos(θ)', color=Colors.TEXT_PRIMARY, fontsize=10)
        
        self.ax.set_ylim(self.y_min, self.y_max)
        
        self.ax.tick_params(colors=Colors.TEXT_PRIMARY, labelsize=9)
        for spine in self.ax.spines.values():
            spine.set_edgecolor(Colors.PANEL_ACCENT)
            spine.set_linewidth(1)
        
        self.ax.grid(True, alpha=0.2, color=Colors.TEXT_SECONDARY, linestyle='--', linewidth=0.5)
        
        self.figure.tight_layout()

    def set_y_range(self, y_min, y_max):
        """Updates the Y-axis range and redraws."""
        self.y_min = y_min
        self.y_max = y_max
        self.ax.set_ylim(self.y_min, self.y_max)
        self.canvas.draw()
    
    def plot_roi_spectra(self, roi_data_list, color_list):
        """Plots ROI spectra and stores them."""
        self.roi_spectra_data = (roi_data_list, color_list)
        self.ax.clear()
        self.setup_plot_style()
        
        for i, roi_data in enumerate(roi_data_list):
            color = color_list[i % len(color_list)]
            color_normalized = tuple(c / 255.0 for c in color)
            
            wavelengths = roi_data['wavelengths']
            spectrum = roi_data['spectrum']
            std = roi_data['std']
            
            self.ax.errorbar(wavelengths, spectrum, yerr=std,
                            color=color_normalized, linewidth=2,
                            marker='o', markersize=4,
                            capsize=3, capthick=1, elinewidth=1)
            
            bayer_wls = roi_data['bayer_wavelengths']
            bayer_spec = roi_data['bayer_spectrum']
            bayer_std = roi_data['bayer_std']
            
            self.ax.errorbar(bayer_wls, bayer_spec, yerr=bayer_std,
                            color=color_normalized, linestyle='',
                            marker='o', markersize=4,
                            capsize=3, capthick=1, elinewidth=1)
        
        self.canvas.draw()
    
    def plot_preview_spectrum_separate(self, wavelengths, reflectances, bayer_wls, bayer_reflectances):
        """Plots preview spectrum with separate Bayer handling."""
        if self.roi_spectra_data is not None:
            roi_data_list, color_list = self.roi_spectra_data
            self.ax.clear()
            self.setup_plot_style()
            
            for i, roi_data in enumerate(roi_data_list):
                color = color_list[i % len(color_list)]
                color_normalized = tuple(c / 255.0 for c in color)
                
                wls = roi_data['wavelengths']
                spec = roi_data['spectrum']
                std = roi_data['std']
                
                self.ax.errorbar(wls, spec, yerr=std,
                                color=color_normalized, linewidth=2,
                                marker='o', markersize=4,
                                capsize=3, capthick=1, elinewidth=1)
                
                bayer_wls = roi_data['bayer_wavelengths']
                bayer_spec = roi_data['bayer_spectrum']
                bayer_std = roi_data['bayer_std']
                
                self.ax.errorbar(bayer_wls, bayer_spec, yerr=bayer_std,
                                color=color_normalized, linestyle='',
                                marker='o', markersize=4,
                                capsize=3, capthick=1, elinewidth=1)
        else:
            self.ax.clear()
            self.setup_plot_style()
        
        self.ax.plot(wavelengths, reflectances,
                    color='white', linewidth=1, alpha=0.3,
                    marker='o', markersize=3, zorder=100)
        
        self.ax.plot(bayer_wls, bayer_reflectances,
                    color='white', linestyle='', alpha=0.3,
                    marker='o', markersize=3, zorder=100)
        
        self.canvas.draw()
    
    def hide_preview(self):
        """Hides preview spectrum."""
        if self.roi_spectra_data is not None:
            roi_data_list, color_list = self.roi_spectra_data
            self.plot_roi_spectra(roi_data_list, color_list)
        else:
            self.clear_plot()
    
    def clear_roi_spectra(self):
        """Clears stored ROI spectra."""
        self.roi_spectra_data = None
    
    def clear_plot(self):
        """Clears the plot."""
        self.ax.clear()
        self.setup_plot_style()
        self.canvas.draw()


class ParameterSelectionPanel(QFrame):
    """
    Panel for adjusting algorithm parameters and view settings.
    Mimics Adobe Premiere Pro properties panel style.
    """
    
    view_settings_changed = pyqtSignal(float, float) # y_min, y_max
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        self.setStyleSheet(f"background-color: {Colors.PANEL_BACKGROUND};")
        layout = QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        self.setLayout(layout)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # Use same scroll bar style as Image Selection
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {Colors.PANEL_BACKGROUND};
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
        
        content_widget = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(2)
        content_widget.setLayout(self.content_layout)
        scroll_area.setWidget(content_widget)
        
        layout.addWidget(scroll_area)
        
        # --- View Settings ---
        self.view_section = CollapsibleSection("View Settings")
        
        self.spin_y_min = self._create_double_spin(-0.1, 1.0, 0.0, 0.05)
        self.spin_y_max = self._create_double_spin(0.0, 5.0, 0.4, 0.05)
        
        # Connect signals immediate update
        self.spin_y_min.valueChanged.connect(self._emit_view_settings)
        self.spin_y_max.valueChanged.connect(self._emit_view_settings)

        view_form = QFormLayout()
        self._add_row(view_form, "Y-Axis Min", self.spin_y_min, 
                      "Minimum value for the spectral plot Y-axis (Reflectance).")
        self._add_row(view_form, "Y-Axis Max", self.spin_y_max, 
                      "Maximum value for the spectral plot Y-axis (Reflectance).")
        self.view_section.add_widget(self._wrap_layout(view_form))
        self.content_layout.addWidget(self.view_section)

        # --- Segmentation Settings (SAM) ---
        self.seg_section = CollapsibleSection("Segmentation")
        
        self.chk_preserve_bg = QCheckBox()
        self.chk_preserve_bg.setChecked(True)
        self.spin_points = self._create_int_spin(16, 64, 32)
        self.spin_iou = self._create_double_spin(0.0, 1.0, 0.88, 0.01)
        
        seg_form = QFormLayout()
        self._add_row(seg_form, "Preserve Bg", self.chk_preserve_bg, 
                      "Keep background pixels in visualization instead of masking them black.")
        self._add_row(seg_form, "Points/Side", self.spin_points, 
                      "Sampling points per side for SAM mask generation. Higher = finer detail, slower.")
        self._add_row(seg_form, "Pred IOU", self.spin_iou, 
                      "Intersection Over Union threshold. Filters out low-confidence masks.")
        self.seg_section.add_widget(self._wrap_layout(seg_form))
        self.content_layout.addWidget(self.seg_section)
        
        # --- ROI Extraction Settings ---
        self.roi_section = CollapsibleSection("ROI Extraction")
        
        self.spin_edge = self._create_int_spin(0, 50, 10)
        self.spin_variance = self._create_double_spin(0.1, 10.0, 1.0, 0.1)
        self.spin_area_thresh = self._create_int_spin(1, 1000, 50)
        self.spin_albedo = self._create_double_spin(0.0, 1.0, 0.80, 0.05)
        self.spin_min_cluster = self._create_int_spin(10, 5000, 500)
        self.spin_min_clean = self._create_int_spin(100, 10000, 4000)
        self.spin_morph = self._create_int_spin(0, 5000, 1000)
        self.spin_subclusters = self._create_int_spin(1, 50, 10)
        
        roi_form = QFormLayout()
        self._add_row(roi_form, "Edge Offset", self.spin_edge, 
                      "Pixels to erode from segment boundaries to avoid artifacts.")
        self._add_row(roi_form, "Variance", self.spin_variance, 
                      "Max allowed spectral variance within a region. Lower = stricter uniformity.")
        self._add_row(roi_form, "Area Thresh", self.spin_area_thresh, 
                      "Minimum pixel area for a single superpixel segment.")
        self._add_row(roi_form, "Albedo Ratio", self.spin_albedo, 
                      "Threshold for brightness similarity. Regions with vastly different brightness are split.")
        self._add_row(roi_form, "Min Cluster", self.spin_min_cluster, 
                      "Minimum total area required for a cluster of merged segments.")
        self._add_row(roi_form, "Min Clean", self.spin_min_clean, 
                      "Minimum area required for a final ROI after cleaning.")
        self._add_row(roi_form, "Morph Open", self.spin_morph, 
                      "Size of morphological opening to remove small noise.")
        self._add_row(roi_form, "Subclusters", self.spin_subclusters, 
                      "Max number of spectral units to split a large cluster into.")
        self.roi_section.add_widget(self._wrap_layout(roi_form))
        self.content_layout.addWidget(self.roi_section)
        
        # --- Spectral Analysis Settings ---
        self.spec_section = CollapsibleSection("Spectral Analysis")
        
        self.spin_contamination = self._create_double_spin(0.0, 0.5, 0.1, 0.01)
        self.spin_freq = self._create_double_spin(0.0, 1.0, 0.7, 0.05)
        
        spec_form = QFormLayout()
        self._add_row(spec_form, "Contamination", self.spin_contamination, 
                      "Expected fraction of outliers in the spectral dataset.")
        self._add_row(spec_form, "Freq Thresh", self.spin_freq, 
                      "Threshold for spectral frequency filtering (noise removal).")
        self.spec_section.add_widget(self._wrap_layout(spec_form))
        self.content_layout.addWidget(self.spec_section)
        
        self.content_layout.addStretch()
        
        # Apply dark theme to all child labels and tooltips
        self._apply_styles()

    def _create_double_spin(self, min_val, max_val, default, step):
        sb = QDoubleSpinBox()
        sb.setRange(min_val, max_val)
        sb.setValue(default)
        sb.setSingleStep(step)
        sb.setStyleSheet(self._spin_style())
        return sb
    
    def _create_int_spin(self, min_val, max_val, default):
        sb = QSpinBox()
        sb.setRange(min_val, max_val)
        sb.setValue(default)
        sb.setStyleSheet(self._spin_style())
        return sb
    
    def _add_row(self, layout, label_text, widget, tooltip):
        """Adds a row with tooltips on both label and widget."""
        label = QLabel(label_text)
        label.setToolTip(tooltip)
        widget.setToolTip(tooltip)
        layout.addRow(label, widget)

    def _spin_style(self):
        return f"""
            QAbstractSpinBox {{
                background-color: {Colors.DEFAULT_FEATURE};
                color: {Colors.ACCENT};
                border: 1px solid {Colors.PANEL_ACCENT};
                padding: 2px;
                border-radius: 2px;
            }}
            QAbstractSpinBox:hover {{
                border: 1px solid {Colors.ACCENT};
            }}
        """

    def _wrap_layout(self, layout):
        w = QWidget()
        layout.setContentsMargins(0,0,0,0)
        layout.setLabelAlignment(Qt.AlignLeft)
        w.setLayout(layout)
        return w

    def _apply_styles(self):
        # Styling for labels in form layouts
        self.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 9pt;
            }}
            QCheckBox {{
                color: {Colors.TEXT_PRIMARY};
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {Colors.PANEL_ACCENT};
                background: {Colors.DEFAULT_FEATURE};
            }}
            QCheckBox::indicator:checked {{
                background: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT};
            }}
            QToolTip {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.ACCENT};
                padding: 4px;
            }}
        """)

    def _emit_view_settings(self):
        self.view_settings_changed.emit(self.spin_y_min.value(), self.spin_y_max.value())

    def get_parameters(self):
        """Returns dictionary of all parameters."""
        return {
            'segment': {
                'preserve_background': self.chk_preserve_bg.isChecked(),
                'points_per_side': self.spin_points.value(),
                'pred_iou_thresh': self.spin_iou.value()
            },
            'roi': {
                'edge_offset': self.spin_edge.value(),
                'allowed_variance': self.spin_variance.value(),
                'area_threshold': self.spin_area_thresh.value(),
                'albedo_ratio_threshold': self.spin_albedo.value(),
                'min_cluster_area': self.spin_min_cluster.value(),
                'min_clean_area': self.spin_min_clean.value(),
                'morph_opening_threshold': self.spin_morph.value(),
                'max_subclusters': self.spin_subclusters.value()
            },
            'spectral': {
                'contamination': self.spin_contamination.value(),
                'freq_threshold': self.spin_freq.value()
            }
        }


class ImageSelectionPanel(QFrame):
    """Panel for scene thumbnail selection."""
    
    resized = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.scene_thumbnails = {}
        self.thumbnail_pixmaps = {}
        self.thumbnail_filenames = {}
        self.selected_scene_id = None
        self.init_ui()
    
    def init_ui(self):
        """Creates image selection panel."""
        self.setStyleSheet(f"background-color: {Colors.PANEL_BACKGROUND};")
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # RESTORED: Legacy scroll bar styling
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
        
        scroll_widget = QWidget()
        self.thumbnail_layout = QGridLayout()
        self.thumbnail_layout.setSpacing(10)
        self.thumbnail_layout.setContentsMargins(10, 10, 10, 10)
        scroll_widget.setLayout(self.thumbnail_layout)
        
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)
        
        self.resized.connect(self.update_thumbnail_sizes)
    
    def resizeEvent(self, event):
        """Emits signal when panel resized."""
        super().resizeEvent(event)
        self.resized.emit()
    
    def add_thumbnail(self, scene_id, pixmap, filename):
        """Adds thumbnail to grid."""
        self.thumbnail_pixmaps[scene_id] = pixmap
        self.thumbnail_filenames[scene_id] = filename
        
        thumb_size = self.calculate_thumbnail_size()
        cols = self.calculate_column_count()
        label_height = 45
        
        thumb_widget = QWidget()
        thumb_widget.setProperty("scene_id", scene_id)
        thumb_widget.setFixedSize(thumb_size, thumb_size + label_height + 5)
        thumb_layout = QVBoxLayout()
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(5)
        thumb_widget.setLayout(thumb_layout)
        
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
        
        self.scene_thumbnails[scene_id] = thumb_label
        
        num_items = len(self.scene_thumbnails)
        col = (num_items - 1) % cols
        row = (num_items - 1) // cols
        self.thumbnail_layout.addWidget(thumb_widget, row, col, Qt.AlignTop)
    
    def calculate_thumbnail_size(self):
        """Calculates thumbnail size based on width."""
        available_width = self.width() - 40
        cols = self.calculate_column_count()
        spacing = 10 * (cols + 1)
        thumb_size = (available_width - spacing) // cols
        return max(180, min(400, thumb_size))
    
    def calculate_column_count(self):
        """Calculates number of columns."""
        available_width = self.width() - 40
        if available_width < 180:
            return 1
        elif available_width < 400:
            return 1
        else:
            return 2
    
    def update_thumbnail_sizes(self):
        """Updates all thumbnail sizes on resize."""
        if not hasattr(self, 'thumbnail_pixmaps') or not self.thumbnail_pixmaps:
            return
        
        thumb_size = self.calculate_thumbnail_size()
        cols = self.calculate_column_count()
        label_height = 45
        
        selected_scene = self.selected_scene_id
        
        for i in reversed(range(self.thumbnail_layout.count())):
            item = self.thumbnail_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)
        
        self.scene_thumbnails.clear()
        
        for idx, scene_id in enumerate(self.thumbnail_pixmaps.keys()):
            pixmap = self.thumbnail_pixmaps[scene_id]
            filename = self.thumbnail_filenames[scene_id]
            
            thumb_widget = QWidget()
            thumb_widget.setProperty("scene_id", scene_id)
            thumb_widget.setFixedSize(thumb_size, thumb_size + label_height + 5)
            thumb_layout = QVBoxLayout()
            thumb_layout.setContentsMargins(0, 0, 0, 0)
            thumb_layout.setSpacing(5)
            thumb_widget.setLayout(thumb_layout)
            
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
            
            self.scene_thumbnails[scene_id] = thumb_label
            
            col = idx % cols
            row = idx // cols
            self.thumbnail_layout.addWidget(thumb_widget, row, col, Qt.AlignTop)
        
        if selected_scene:
            self.select_scene(selected_scene)
    
    def select_scene(self, scene_id):
        """Selects and highlights scene."""
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
        """Returns currently selected scene ID."""
        return self.selected_scene_id
    
    def clear_thumbnails(self):
        """Clears all thumbnails."""
        for i in reversed(range(self.thumbnail_layout.count())):
            self.thumbnail_layout.itemAt(i).widget().setParent(None)
        
        self.scene_thumbnails.clear()
        self.thumbnail_pixmaps.clear()
        self.thumbnail_filenames.clear()
        self.selected_scene_id = None


class ImageEditingPanel(QWidget):
    """Panel for image editing with canvas and toolbar."""
    
    # RESTORED: Emit string name of algorithm
    run_algorithm_signal = pyqtSignal(str)
    scene_dropped_signal = pyqtSignal(str)
    spectral_preview_signal = pyqtSignal(int, int)
    tool_changed_signal = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.current_tool = "selection"
        self.init_ui()
        
        self.canvas_container.installEventFilter(self)
    
    def init_ui(self):
        """Creates image editing panel layout."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        
        top_bar = QWidget()
        top_bar.setStyleSheet(f"background-color: {Colors.PANEL_ACCENT}; border-bottom: 1px solid {Colors.DEFAULT_FEATURE};")
        top_bar.setMaximumHeight(35)
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(8, 4, 8, 4)
        top_bar_layout.setSpacing(8)
        top_bar.setLayout(top_bar_layout)
        
        # RESTORED: Algorithm dropdown
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
        
        content_widget = QWidget()
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_widget.setLayout(content_layout)
        
        self.toolbar = QWidget()
        self.toolbar.setStyleSheet(f"background-color: {Colors.PANEL_ACCENT}; border-right: 1px solid {Colors.DEFAULT_FEATURE};")
        self.toolbar.setMaximumWidth(54)
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_layout.setSpacing(4)
        self.toolbar.setLayout(toolbar_layout)
        
        self.btn_selection = ToolbarButton(
            "graphics/toolbar_selection.png",
            "graphics/toolbar_selection_selected.png"
        )
        self.btn_selection.set_selected(True)
        self.btn_selection.clicked.connect(lambda: self.select_tool("selection"))
        toolbar_layout.addWidget(self.btn_selection)
        
        self.btn_rectangle = ToolbarButton(
            "graphics/toolbar_rectangle.png",
            "graphics/toolbar_rectangle_selected.png"
        )
        self.btn_rectangle.clicked.connect(lambda: self.select_tool("rectangle"))
        toolbar_layout.addWidget(self.btn_rectangle)
        
        toolbar_layout.addStretch()
        
        content_layout.addWidget(self.toolbar)
        
        self.canvas_container = CanvasContainer()
        self.canvas_container.scene_dropped.connect(self.scene_dropped_signal.emit)
        content_layout.addWidget(self.canvas_container)
        
        layout.addWidget(content_widget)
        
        self.update_cursor()
    
    def select_tool(self, tool_name):
        """Selects tool and updates UI."""
        self.current_tool = tool_name
        
        self.btn_selection.set_selected(tool_name == "selection")
        self.btn_rectangle.set_selected(tool_name == "rectangle")
        
        self.canvas_container.set_hover_preview_enabled(tool_name == "rectangle")
        
        self.tool_changed_signal.emit(tool_name)
        
        self.update_cursor()
    
    def update_cursor(self):
        """Updates canvas cursor based on tool."""
        if self.current_tool == "selection":
            from PyQt5.QtGui import QCursor, QPixmap
            cursor_pixmap = QPixmap("graphics/selection.png")
            cursor = QCursor(cursor_pixmap, 0, 0)
            self.canvas_container.setCursor(cursor)
        elif self.current_tool == "rectangle":
            self.canvas_container.setCursor(Qt.CrossCursor)
    
    def eventFilter(self, obj, event):
        """Filters events for pixel hover."""
        if obj == self.canvas_container and event.type() == event.MouseMove:
            if self.current_tool == "rectangle" and self.canvas_container.canvas.image is not None:
                mouse_pos = event.pos()
                
                canvas_container = self.canvas_container
                zoom = canvas_container.zoom_level
                pan = canvas_container.pan_offset
                canvas = canvas_container.canvas
                
                canvas_viewport_x = pan.x() + (canvas_container.width() / zoom - canvas.width()) / 2 * zoom
                canvas_viewport_y = pan.y() + (canvas_container.height() / zoom - canvas.height()) / 2 * zoom
                
                canvas_x = int((mouse_pos.x() - canvas_viewport_x) / zoom)
                canvas_y = int((mouse_pos.y() - canvas_viewport_y) / zoom)
                
                if 0 <= canvas_x < canvas.width() and 0 <= canvas_y < canvas.height():
                    canvas_container.pixel_hovered.emit(canvas_x, canvas_y)
            
            return False
        return super().eventFilter(obj, event)
    
    def on_run_clicked(self):
        """Emits signal when run clicked."""
        algorithm = self.algorithm_dropdown.currentText()
        self.run_algorithm_signal.emit(algorithm)
    
    def set_image(self, pixmap):
        """Sets image on canvas."""
        self.canvas_container.set_image(pixmap)


class StatusPanel(QWidget):
    """Panel for status messages and logo."""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """Creates status panel with logo and log."""
        self.setMaximumHeight(60)
        self.setStyleSheet(f"background-color: {Colors.DEFAULT_FEATURE}; border-top: 1px solid {Colors.PANEL_ACCENT};")
        
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        
        logo_label = QLabel()
        logo_pixmap = QPixmap("graphics/mcz_logo.png")
        logo_pixmap = logo_pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("padding: 8px;")
        layout.addWidget(logo_label)
        
        self.status_bar = QTextEdit()
        self.status_bar.setReadOnly(True)
        # ADDED: Hide scroll bars
        self.status_bar.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.status_bar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
        layout.addWidget(self.status_bar)
    
    def show_status_message(self, message):
        """Displays message in status bar."""
        self.status_bar.append(f"> {message}")
        self.status_bar.verticalScrollBar().setValue(
            self.status_bar.verticalScrollBar().maximum()
        )