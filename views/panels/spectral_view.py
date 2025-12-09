from PyQt5.QtWidgets import QWidget, QVBoxLayout
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

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
    
    def plot_roi_spectra(self, roi_data_list, color_list):
        """Plots ROI spectra and stores them."""
        self.roi_spectra_data = (roi_data_list, color_list)
        self.ax.clear()
        self.setup_plot_style()
        
        for i, roi_data in enumerate(roi_data_list):
            if i < len(color_list):
                color = color_list[i]
                color_normalized = tuple(c / 255.0 for c in color)
            else:
                color_normalized = (1.0, 1.0, 1.0)
            
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
                if i < len(color_list):
                    color = color_list[i]
                    color_normalized = tuple(c / 255.0 for c in color)
                else:
                    color_normalized = (1.0, 1.0, 1.0)
                
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