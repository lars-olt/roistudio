from PyQt5.QtCore import QObject, pyqtSignal
import numpy as np
from sparc.core.constants import WAVELENGTHS


class SparcController(QObject):
    """Handles SPARC pipeline execution."""
    
    started = pyqtSignal()
    stopped = pyqtSignal()
    status_update = pyqtSignal(str)
    complete = pyqtSignal(object)
    error = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._sparc_thread = None
    
    def start_sparc(self, sam_path, folder_path, seq_id, obs_ix):
        """Starts SPARC pipeline in background."""
        from workers.sparc_runner import SparcRunThread
        
        self._sparc_thread = SparcRunThread(sam_path, folder_path, seq_id, obs_ix)
        self._sparc_thread.status_update.connect(self.status_update.emit)
        self._sparc_thread.sparc_complete.connect(self.complete.emit)
        self._sparc_thread.sparc_error.connect(self.error.emit)
        self._sparc_thread.start()
        
        self.started.emit()
    
    def extract_roi_data(self, result):
        """Extracts ROI data with spectra from SparcResult."""
        rois = []
        
        bayer_wls = WAVELENGTHS[:3]
        non_bayer_wls = np.array(WAVELENGTHS[3:])
        
        sort_indices = np.argsort(non_bayer_wls)
        non_bayer_wls_sorted = non_bayer_wls[sort_indices]
        
        for i, (roi_rect, spectrum, std) in enumerate(zip(result.final_rois, result.final_spectra, result.final_stds)):
            x, y, w, h = roi_rect
            
            mask = np.zeros(result.segments.shape, dtype=bool)
            mask[y:y+h, x:x+w] = True
            
            bayer_spectrum = spectrum[:3].tolist()
            non_bayer_spectrum = spectrum[3:]
            
            bayer_std = std[:3].tolist()
            non_bayer_std = std[3:]
            
            non_bayer_spectrum_sorted = non_bayer_spectrum[sort_indices].tolist()
            non_bayer_std_sorted = non_bayer_std[sort_indices].tolist()
            
            rois.append({
                'roi': roi_rect,
                'mask': mask,
                'spectrum': non_bayer_spectrum_sorted,
                'std': non_bayer_std_sorted,
                'wavelengths': non_bayer_wls_sorted.tolist(),
                'bayer_spectrum': bayer_spectrum,
                'bayer_std': bayer_std,
                'bayer_wavelengths': bayer_wls,
                'mineral': f'ROI_{i+1}'
            })
        
        return rois