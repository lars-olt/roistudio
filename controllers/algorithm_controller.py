"""Full-edition adapter for running SPARC and unpacking its results."""

import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal


class AlgorithmController(QObject):
    """Own the optional SPARC worker; absent from ROIStudio Lite."""

    started       = pyqtSignal()
    stopped       = pyqtSignal()
    status_update = pyqtSignal(str)
    complete      = pyqtSignal(object)
    error         = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._sparc_thread = None

    def start_sparc(self, sam_path, folder_path, seq_id, obs_ix, instrument,
                    params=None, load_result=None, presegmented=None):
        if self._sparc_thread is not None and self._sparc_thread.isRunning():
            self.status_update.emit("SPARC is already running.")
            return False

        thread = self._new_thread(
            sam_path, folder_path, seq_id, obs_ix, instrument,
            params, load_result, presegmented,
        )
        self._sparc_thread = thread
        thread.status_update.connect(self.status_update.emit)
        thread.sparc_complete.connect(self.complete.emit)
        thread.sparc_error.connect(self.error.emit)
        thread.finished.connect(
            lambda current_thread=thread: self._thread_finished(current_thread)
        )
        thread.start()
        self.started.emit()
        return True

    @staticmethod
    def _new_thread(*args):
        # Delay the algorithm import so this controller remains safe to inspect
        # and test in ROIStudio Lite's lightweight environment.
        from workers.sparc_runner import SparcRunThread
        return SparcRunThread(*args)

    def _thread_finished(self, thread):
        if self._sparc_thread is thread:
            self._sparc_thread = None
        thread.deleteLater()
        self.stopped.emit()

    @staticmethod
    def extract_roi_data(result, instrument_config):
        """Build ROIStudio dictionaries from a full-edition SPARC result."""
        from .sparc_controller import SparcController

        rois = []
        for i, (right_rect, left_rect, spectrum, std) in enumerate(
            zip(result.final_rois, result.final_left_rois,
                result.final_spectra, result.final_stds)
        ):
            x, y, w, h = right_rect
            mask = np.zeros(result.segments.shape, dtype=bool)
            mask[y:y+h, x:x+w] = True
            nb_wls, nb_spec, nb_std, bwls, bspec, bstd = \
                SparcController._split_spectrum(
                    spectrum, std, instrument_config
                )
            rois.append({
                'roi':               tuple(right_rect),
                'right_rect':        tuple(right_rect),
                'left_rect':         tuple(left_rect),
                'mask':              mask,
                'spectrum':          nb_spec,
                'std':               nb_std,
                'wavelengths':       nb_wls,
                'bayer_spectrum':    bspec,
                'bayer_std':         bstd,
                'bayer_wavelengths': bwls,
                'left_spectrum':     [],
                'left_std':          [],
                'left_wavelengths':  [],
                'right_spectrum':    [],
                'right_std':         [],
                'right_wavelengths': [],
                'mineral':           f'ROI_{i+1}',
            })
        return rois
