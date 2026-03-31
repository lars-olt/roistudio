from PyQt5.QtWidgets import QWidget, QVBoxLayout
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np

from colors import Colors


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

    @staticmethod
    def _sort_spectrum(wavelengths, spectrum, std):
        """Returns wavelengths, spectrum, and std sorted by ascending wavelength."""
        wls = np.array(wavelengths, dtype=float)
        spec = np.array(spectrum, dtype=float)
        s = np.array(std, dtype=float)
        ix = np.argsort(wls)
        return wls[ix], spec[ix], s[ix]

    def _plot_roi(self, ax, roi_data, color_normalized):
        """Plots a single ROI spectrum (non-Bayer line + Bayer dots)."""
        wls, spec, std = self._sort_spectrum(
            roi_data['wavelengths'],
            roi_data['spectrum'],
            roi_data['std'],
        )
        ax.errorbar(wls, spec, yerr=std,
                    color=color_normalized, linewidth=2,
                    marker='o', markersize=4,
                    capsize=3, capthick=1, elinewidth=1)

        # Bayer bands: dots only, no connecting line
        if roi_data.get('bayer_wavelengths'):
            bwls, bspec, bstd = self._sort_spectrum(
                roi_data['bayer_wavelengths'],
                roi_data['bayer_spectrum'],
                roi_data['bayer_std'],
            )
            ax.errorbar(bwls, bspec, yerr=bstd,
                        color=color_normalized, linestyle='',
                        marker='o', markersize=4,
                        capsize=3, capthick=1, elinewidth=1)

    def plot_roi_spectra(self, roi_data_list, color_list):
        """Plots ROI spectra and stores them."""
        self.roi_spectra_data = (roi_data_list, color_list)
        self.ax.clear()
        self.setup_plot_style()

        for i, roi_data in enumerate(roi_data_list):
            color = color_list[i] if i < len(color_list) else (255, 255, 255)
            color_normalized = tuple(c / 255.0 for c in color)
            self._plot_roi(self.ax, roi_data, color_normalized)

        self.canvas.draw()

    def plot_preview_spectrum_separate(self, wavelengths, reflectances, bayer_wls, bayer_reflectances):
        """Plots preview spectrum on top of stored ROI spectra."""
        self.ax.clear()
        self.setup_plot_style()

        if self.roi_spectra_data is not None:
            roi_data_list, color_list = self.roi_spectra_data
            for i, roi_data in enumerate(roi_data_list):
                color = color_list[i] if i < len(color_list) else (255, 255, 255)
                color_normalized = tuple(c / 255.0 for c in color)
                self._plot_roi(self.ax, roi_data, color_normalized)

        # Preview line - already sorted by caller
        wls = np.array(wavelengths, dtype=float)
        spec = np.array(reflectances, dtype=float)
        ix = np.argsort(wls)
        self.ax.plot(wls[ix], spec[ix],
                     color='white', linewidth=1, alpha=0.3,
                     marker='o', markersize=3, zorder=100)

        if len(bayer_wls) > 0:
            bwls = np.array(bayer_wls, dtype=float)
            bspec = np.array(bayer_reflectances, dtype=float)
            self.ax.plot(bwls, bspec,
                         color='white', linestyle='', alpha=0.3,
                         marker='o', markersize=3, zorder=100)

        self.canvas.draw()

    def hide_preview(self):
        """Hides preview spectrum and restores stored ROI spectra."""
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