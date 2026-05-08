from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np

from colors import Colors
from utils.scale import Scale, scaled_font


def _dpr():
    screen = QApplication.primaryScreen()
    return screen.devicePixelRatio() if screen else 1.0


class SpectralViewPanel(QWidget):
    """Panel for displaying spectral plots."""

    def __init__(self):
        super().__init__()
        self.roi_spectra_data = None
        self.y_min = 0.0
        self.y_max = 0.4
        self.merge_spectra = True
        self.init_ui()
        Scale.changed.connect(self._apply_scale)

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        dpr = _dpr()
        self.figure = Figure(figsize=(8 / dpr, 4 / dpr), dpi=100,
                             facecolor=Colors.PANEL_BACKGROUND)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setStyleSheet(f"background-color: {Colors.PANEL_BACKGROUND};")

        self.ax = self.figure.add_subplot(111)
        self.setup_plot_style()

        layout.addWidget(self.canvas)

        # Defer the first tight_layout until after the widget has its real
        # size from the layout pass — avoids the clipped-on-load issue.
        QTimer.singleShot(0, self._fit_layout)

    def setup_plot_style(self):
        self.ax.set_facecolor(Colors.DEFAULT_FEATURE)
        self.figure.patch.set_facecolor(Colors.PANEL_BACKGROUND)

        self.ax.set_xlabel('Wavelength (nm)', color=Colors.TEXT_PRIMARY,
                           fontsize=scaled_font(10))
        self.ax.set_ylabel('R* = IOF/cos(θ)',  color=Colors.TEXT_PRIMARY,
                           fontsize=scaled_font(10))

        self.ax.set_ylim(self.y_min, self.y_max)
        self.ax.tick_params(colors=Colors.TEXT_PRIMARY, labelsize=scaled_font(9))

        for spine in self.ax.spines.values():
            spine.set_edgecolor(Colors.PANEL_ACCENT)
            spine.set_linewidth(1)

        self.ax.grid(True, alpha=0.2, color=Colors.TEXT_SECONDARY,
                     linestyle='--', linewidth=0.5)

    def _fit_layout(self):
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                self.figure.tight_layout(pad=1.5)
        except Exception:
            pass
        self.canvas.draw_idle()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_layout()

    def _apply_scale(self):
        self.ax.clear()
        self.setup_plot_style()
        if self.roi_spectra_data is not None:
            roi_data_list, color_list = self.roi_spectra_data
            for i, roi_data in enumerate(roi_data_list):
                color = color_list[i] if i < len(color_list) else (255, 255, 255)
                self._plot_roi(self.ax, roi_data, tuple(c / 255.0 for c in color))
        self._fit_layout()

    def set_y_range(self, y_min, y_max):
        self.y_min = y_min
        self.y_max = y_max
        self.ax.set_ylim(self.y_min, self.y_max)
        self.canvas.draw()

    def set_merge_spectra(self, merged):
        self.merge_spectra = merged
        if self.roi_spectra_data is not None:
            roi_data_list, color_list = self.roi_spectra_data
            self.plot_roi_spectra(roi_data_list, color_list)

    @staticmethod
    def _sort_spectrum(wavelengths, spectrum, std):
        wls  = np.array(wavelengths, dtype=float)
        spec = np.array(spectrum,    dtype=float)
        s    = np.array(std,         dtype=float)
        ix   = np.argsort(wls)
        return wls[ix], spec[ix], s[ix]

    def _plot_roi(self, ax, roi_data, color):
        if self.merge_spectra:
            self._plot_merged(ax, roi_data, color)
        else:
            self._plot_split(ax, roi_data, color)

        if roi_data.get('bayer_wavelengths'):
            bwls, bspec, bstd = self._sort_spectrum(
                roi_data['bayer_wavelengths'],
                roi_data['bayer_spectrum'],
                roi_data['bayer_std'],
            )
            ax.errorbar(bwls, bspec, yerr=bstd,
                        color=color, linestyle='',
                        marker='o', markersize=2,
                        capsize=3, capthick=1, elinewidth=1)

    def _plot_merged(self, ax, roi_data, color):
        wls, spec, std = self._sort_spectrum(
            roi_data['wavelengths'],
            roi_data['spectrum'],
            roi_data['std'],
        )
        ax.errorbar(wls, spec, yerr=std,
                    color=color, linewidth=1,
                    capsize=3, capthick=1, elinewidth=1)

    def _plot_split(self, ax, roi_data, color):
        for wl_key, spec_key, std_key in (
            ('left_wavelengths',  'left_spectrum',  'left_std'),
            ('right_wavelengths', 'right_spectrum', 'right_std'),
        ):
            wls  = roi_data.get(wl_key,  [])
            spec = roi_data.get(spec_key, [])
            std  = roi_data.get(std_key,  [])
            if not wls:
                continue
            wls, spec, std = self._sort_spectrum(wls, spec, std)
            ax.errorbar(wls, spec, yerr=std,
                        color=color, linewidth=1,
                        capsize=3, capthick=1, elinewidth=1)

    def plot_roi_spectra(self, roi_data_list, color_list):
        self.roi_spectra_data = (roi_data_list, color_list)
        self.ax.clear()
        self.setup_plot_style()
        for i, roi_data in enumerate(roi_data_list):
            color = color_list[i] if i < len(color_list) else (255, 255, 255)
            self._plot_roi(self.ax, roi_data, tuple(c / 255.0 for c in color))
        self._fit_layout()

    def plot_preview_spectrum_separate(self, wavelengths, reflectances,
                                       bayer_wls, bayer_reflectances):
        self.ax.clear()
        self.setup_plot_style()

        if self.roi_spectra_data is not None:
            roi_data_list, color_list = self.roi_spectra_data
            for i, roi_data in enumerate(roi_data_list):
                color = color_list[i] if i < len(color_list) else (255, 255, 255)
                self._plot_roi(self.ax, roi_data, tuple(c / 255.0 for c in color))

        wls  = np.array(wavelengths, dtype=float)
        spec = np.array(reflectances, dtype=float)
        ix   = np.argsort(wls)
        self.ax.plot(wls[ix], spec[ix],
                     color='white', linewidth=1, alpha=0.3,
                     marker='o', markersize=3, zorder=100)

        if len(bayer_wls) > 0:
            self.ax.plot(np.array(bayer_wls), np.array(bayer_reflectances),
                         color='white', linestyle='', alpha=0.3,
                         marker='o', markersize=3, zorder=100)

        self._fit_layout()

    def hide_preview(self):
        if self.roi_spectra_data is not None:
            roi_data_list, color_list = self.roi_spectra_data
            self.plot_roi_spectra(roi_data_list, color_list)
        else:
            self.clear_plot()

    def clear_roi_spectra(self):
        self.roi_spectra_data = None

    def clear_plot(self):
        self.ax.clear()
        self.setup_plot_style()
        self._fit_layout()