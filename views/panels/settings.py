from PyQt5.QtCore import Qt, pyqtSignal, QObject, QEvent
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QScrollArea, QWidget,
                             QFormLayout, QLabel, QDoubleSpinBox, QSpinBox,
                             QCheckBox, QSlider, QAbstractSpinBox)

from colors import Colors
from utils.scale import Scale, scaled, scaled_font
from ..widgets import CollapsibleSection


class _WheelFilter(QObject):
    """Intercepts wheel events on spinboxes so they scroll the panel instead."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            event.ignore()
            return True
        return False


class SettingsPanel(QFrame):
    """Application-wide display and ROI processing settings."""

    view_settings_changed = pyqtSignal(float, float)
    merge_spectra_changed = pyqtSignal(bool)
    line_width_changed    = pyqtSignal(float)
    exposure_changed      = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self._wheel_filter = _WheelFilter(self)
        self._sections = {}
        self._build_ui()
        Scale.changed.connect(self._apply_scale)

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {Colors.PANEL_BACKGROUND};")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)

        content = QWidget()
        self.content_layout = QVBoxLayout()
        content.setLayout(self.content_layout)
        self.scroll_area.setWidget(content)

        # View Settings
        self.spin_y_min        = self._dbl(-0.1, 1.0, 0.0,  0.05)
        self.spin_y_max        = self._dbl(0.0,  5.0, 0.4,  0.05)
        self.chk_merge_spectra = self._chk(True)
        self.slider_line_width = self._slider(50, 300, 75, step=5)
        # symmetric around zero - centered means no exposure change, and it's the
        # value a new scene resets to
        self.slider_exposure   = self._slider(-100, 100, 0, step=5)

        self.spin_y_min.valueChanged.connect(self._emit_view_settings)
        self.spin_y_max.valueChanged.connect(self._emit_view_settings)
        self.chk_merge_spectra.toggled.connect(self.merge_spectra_changed.emit)
        self.slider_line_width.valueChanged.connect(
            lambda v: self.line_width_changed.emit(v / 100.0)
        )
        # map slider position to a multiplicative factor in stops, so equal steps
        # left and right brighten and darken by the same perceptual amount
        self.slider_exposure.valueChanged.connect(
            lambda v: self.exposure_changed.emit(2.0 ** (v / 100.0))
        )

        self._add_section("view_settings", "View Settings", self._form([
            ("Y-Axis Min",           self.spin_y_min,
             "Minimum value for the spectral plot Y-axis (Reflectance)."),
            ("Y-Axis Max",           self.spin_y_max,
             "Maximum value for the spectral plot Y-axis (Reflectance)."),
            ("Merge camera spectra", self.chk_merge_spectra,
             "Average stereo bands into one spectrum, or plot each camera separately."),
            ("Line Width",           self.slider_line_width,
             "Thickness of spectrum lines in the spectral plot."),
            ("Exposure",             self.slider_exposure,
             "Brighten or darken the RGB stretch image."),
        ]))

        # Segmentation
        self.chk_use_dcs     = self._chk(False)
        self.chk_preserve_bg = self._chk(True)
        self.spin_points     = self._int(16, 64,  32)
        self.spin_iou        = self._dbl(0.0, 1.0, 0.88, 0.01)

        self._add_section("segmentation", "Segmentation", self._form([
            ("Use DCS",      self.chk_use_dcs,
             "Apply decorrelation stretch to the input image before segmentation. "
             "Enhances spectral contrast. On by default for Pancam."),
            ("Preserve Bg",  self.chk_preserve_bg,
             "Keep background pixels instead of masking them black."),
            ("Points/Side",  self.spin_points,
             "SAM sampling points per side. Higher = finer detail, slower."),
            ("Pred IOU",     self.spin_iou,
             "IoU threshold - filters out low-confidence masks."),
        ]))

        # ROI Extraction
        self.spin_edge        = self._int(0,   50,    10)
        self.spin_variance    = self._dbl(0.1, 10.0,  1.0, 0.1)
        self.spin_area_thresh = self._int(1,   1000,  50)
        self.spin_albedo      = self._dbl(0.0,  1.0,  0.80, 0.05)
        self.spin_min_cluster = self._int(10,  5000,  500)
        self.spin_min_clean   = self._int(100, 10000, 4000)
        self.spin_morph       = self._int(0,   5000,  1000)
        self.spin_subclusters = self._int(1,   50,    10)

        self._add_section("roi_extraction", "ROI Extraction", self._form([
            ("Edge Offset",  self.spin_edge,
             "Pixels eroded from segment boundaries to avoid edge artifacts."),
            ("Variance",     self.spin_variance,
             "Max allowed spectral variance within a region. Lower = stricter."),
            ("Area Thresh",  self.spin_area_thresh,
             "Minimum pixel area for a superpixel segment."),
            ("Albedo Ratio", self.spin_albedo,
             "Brightness similarity threshold. Low values allow more albedo variation."),
            ("Min Cluster",  self.spin_min_cluster,
             "Minimum total area for a merged segment cluster."),
            ("Min Clean",    self.spin_min_clean,
             "Minimum area for a final ROI after morphological cleaning."),
            ("Morph Open",   self.spin_morph,
             "Morphological opening size to remove small noise regions."),
            ("Subclusters",  self.spin_subclusters,
             "Maximum spectral subclusters per large segment."),
        ]))

        # Spectral Analysis
        self.spin_max_clusters  = self._int(1,   50,  9)

        self._add_section("spectral_analysis", "Spectral Analysis", self._form([
            ("Max Clusters",  self.spin_max_clusters,
             "Maximum number of spectral clusters the GMM may find."),
        ]))

        self.content_layout.addStretch()
        self._apply_scale()

    # ------------------------------------------------------------------
    # Scale
    # ------------------------------------------------------------------

    def _apply_scale(self):
        fs     = scaled_font(9)
        margin = scaled(8)

        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{ border: none; background-color: {Colors.PANEL_BACKGROUND}; }}
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

        spin_style = f"""
            QAbstractSpinBox {{
                background-color: {Colors.DEFAULT_FEATURE};
                color: {Colors.ACCENT};
                border: 1px solid {Colors.PANEL_ACCENT};
                padding: {scaled(2)}px;
                border-radius: {scaled(2)}px;
                font-size: {fs}pt;
            }}
            QAbstractSpinBox:hover {{ border: 1px solid {Colors.ACCENT}; }}
        """
        for spin in (self.spin_y_min, self.spin_y_max, self.spin_points, self.spin_iou,
                     self.spin_edge, self.spin_variance, self.spin_area_thresh,
                     self.spin_albedo, self.spin_min_cluster, self.spin_min_clean,
                     self.spin_morph, self.spin_subclusters,
                     self.spin_max_clusters):
            spin.setStyleSheet(spin_style)

        slider_style = f"""
            QSlider::groove:horizontal {{
                height: {scaled(4)}px;
                background: {Colors.PANEL_ACCENT};
                border-radius: {scaled(2)}px;
            }}
            QSlider::handle:horizontal {{
                background: {Colors.ACCENT};
                width: {scaled(12)}px;
                height: {scaled(12)}px;
                margin: -{scaled(4)}px 0;
                border-radius: {scaled(6)}px;
            }}
            QSlider::sub-page:horizontal {{
                background: {Colors.ACCENT};
                border-radius: {scaled(2)}px;
            }}
        """
        for slider in (self.slider_line_width, self.slider_exposure):
            slider.setStyleSheet(slider_style)

        chk_style = f"""
            QCheckBox {{ color: {Colors.TEXT_PRIMARY}; font-size: {fs}pt; }}
            QCheckBox::indicator {{
                width: {scaled(14)}px; height: {scaled(14)}px;
                border: 1px solid {Colors.PANEL_ACCENT};
                background: {Colors.DEFAULT_FEATURE};
            }}
            QCheckBox::indicator:checked {{
                background: {Colors.ACCENT}; border: 1px solid {Colors.ACCENT};
            }}
        """
        for chk in (self.chk_use_dcs, self.chk_preserve_bg, self.chk_merge_spectra):
            chk.setStyleSheet(chk_style)

        self.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY}; font-size: {fs}pt;
            }}
            QToolTip {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.ACCENT};
                padding: {scaled(4)}px; font-size: {fs}pt;
            }}
        """)

        self.content_layout.setContentsMargins(margin, margin, margin, margin)
        self.content_layout.setSpacing(scaled(2))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _dbl(self, lo, hi, default, step):
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi); sb.setValue(default); sb.setSingleStep(step)
        sb.setFocusPolicy(Qt.StrongFocus)
        sb.setButtonSymbols(QAbstractSpinBox.NoButtons)
        sb.installEventFilter(self._wheel_filter)
        return sb

    def _int(self, lo, hi, default):
        sb = QSpinBox()
        sb.setRange(lo, hi); sb.setValue(default)
        sb.setFocusPolicy(Qt.StrongFocus)
        sb.setButtonSymbols(QAbstractSpinBox.NoButtons)
        sb.installEventFilter(self._wheel_filter)
        return sb

    def _chk(self, checked=False):
        cb = QCheckBox(); cb.setChecked(checked)
        return cb

    def _slider(self, lo, hi, default, step=1):
        sl = QSlider(Qt.Horizontal)
        sl.setRange(lo, hi); sl.setValue(default); sl.setSingleStep(step)
        return sl

    def _form(self, rows):
        """Build a QFormLayout from (label, widget, tooltip) triples."""
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignLeft)
        for label_text, widget, tooltip in rows:
            lbl = QLabel(label_text)
            lbl.setToolTip(tooltip)
            widget.setToolTip(tooltip)
            form.addRow(lbl, widget)
        w = QWidget()
        w.setLayout(form)
        return w

    def _add_section(self, key, title, content_widget):
        section = CollapsibleSection(title)
        section.add_widget(content_widget)
        self.content_layout.addWidget(section)
        self._sections[key] = section

    def _emit_view_settings(self):
        self.view_settings_changed.emit(self.spin_y_min.value(), self.spin_y_max.value())

    def display_preferences(self):
        return {
            'y_min':         self.spin_y_min.value(),
            'y_max':         self.spin_y_max.value(),
            'merge_spectra': self.chk_merge_spectra.isChecked(),
            'line_width':    self.slider_line_width.value() / 100.0,
        }

    def apply_display_preferences(self, *, y_min=None, y_max=None,
                                  merge_spectra=None, line_width=None):
        """Apply saved display values; keyword arguments also suit future CLI overrides."""
        if y_min is not None:
            self.spin_y_min.setValue(float(y_min))
        if y_max is not None:
            self.spin_y_max.setValue(float(y_max))
        if merge_spectra is not None:
            self.chk_merge_spectra.setChecked(bool(merge_spectra))
        if line_width is not None:
            self.slider_line_width.setValue(round(float(line_width) * 100))

    def section_states(self):
        return {key: section.is_expanded()
                for key, section in self._sections.items()}

    def apply_section_states(self, states):
        for key, expanded in states.items():
            section = self._sections.get(key)
            if section is not None:
                section.set_expanded(bool(expanded))

    def set_use_dcs(self, enabled: bool):
        self.chk_use_dcs.setChecked(enabled)

    def reset_exposure(self):
        """Return exposure to neutral - called when a new scene loads."""
        self.slider_exposure.setValue(0)

    def get_parameters(self):
        return {
            'segment': {
                'use_dcs':             self.chk_use_dcs.isChecked(),
                'preserve_background': self.chk_preserve_bg.isChecked(),
                'points_per_side':     self.spin_points.value(),
                'pred_iou_thresh':     self.spin_iou.value(),
            },
            'roi': {
                'edge_offset':             self.spin_edge.value(),
                'allowed_variance':        self.spin_variance.value(),
                'area_threshold':          self.spin_area_thresh.value(),
                'albedo_ratio_threshold':  self.spin_albedo.value(),
                'min_cluster_area':        self.spin_min_cluster.value(),
                'min_clean_area':          self.spin_min_clean.value(),
                'morph_opening_threshold': self.spin_morph.value(),
                'max_subclusters':         self.spin_subclusters.value(),
            },
            'spectral': {
                'max_components': self.spin_max_clusters.value(),
            },
        }
