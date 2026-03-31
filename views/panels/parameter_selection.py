from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QScrollArea, QWidget,
                             QFormLayout, QLabel, QDoubleSpinBox, QSpinBox,
                             QCheckBox)

from colors import Colors
from ..widgets import CollapsibleSection


class ParameterSelectionPanel(QFrame):
    """
    Panel for adjusting algorithm parameters and view settings.
    Mimics Adobe Premiere Pro properties panel style.
    """

    view_settings_changed = pyqtSignal(float, float)  # y_min, y_max

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(f"background-color: {Colors.PANEL_BACKGROUND};")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
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
        self.spin_max_clusters = self._create_int_spin(1, 50, 9)

        spec_form = QFormLayout()
        self._add_row(spec_form, "Contamination", self.spin_contamination,
                      "Expected fraction of outliers in the spectral dataset.")
        self._add_row(spec_form, "Freq Thresh", self.spin_freq,
                      "Threshold for spectral frequency filtering (noise removal).")
        self._add_row(spec_form, "Max Clusters", self.spin_max_clusters,
                      "Maximum number of spectral clusters the GMM can find.")
        self.spec_section.add_widget(self._wrap_layout(spec_form))
        self.content_layout.addWidget(self.spec_section)

        self.content_layout.addStretch()

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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setLabelAlignment(Qt.AlignLeft)
        w.setLayout(layout)
        return w

    def _apply_styles(self):
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
                'points_per_side':     self.spin_points.value(),
                'pred_iou_thresh':     self.spin_iou.value(),
            },
            'roi': {
                'edge_offset':            self.spin_edge.value(),
                'allowed_variance':       self.spin_variance.value(),
                'area_threshold':         self.spin_area_thresh.value(),
                'albedo_ratio_threshold': self.spin_albedo.value(),
                'min_cluster_area':       self.spin_min_cluster.value(),
                'min_clean_area':         self.spin_min_clean.value(),
                'morph_opening_threshold': self.spin_morph.value(),
                'max_subclusters':        self.spin_subclusters.value(),
            },
            'spectral': {
                'contamination':  self.spin_contamination.value(),
                'freq_threshold': self.spin_freq.value(),
                'max_components': self.spin_max_clusters.value(),
            },
        }