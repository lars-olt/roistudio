from PyQt5.QtCore import QObject, pyqtSignal
import numpy as np


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

    def start_sparc(self, sam_path, folder_path, seq_id, obs_ix, instrument, max_components=9):
        """Starts SPARC pipeline in background."""
        from workers.sparc_runner import SparcRunThread

        self._sparc_thread = SparcRunThread(
            sam_path, folder_path, seq_id, obs_ix, instrument, max_components
        )
        self._sparc_thread.status_update.connect(self.status_update.emit)
        self._sparc_thread.sparc_complete.connect(self.complete.emit)
        self._sparc_thread.sparc_error.connect(self.error.emit)
        self._sparc_thread.start()

        self.started.emit()

    @staticmethod
    def _split_spectrum(spectrum, std, instrument_config):
        """
        Splits a spectrum into Bayer and non-Bayer bands.

        Uses the number of RGB bands as the Bayer cutoff:
          - ZCAM: 3 (L0R, L0G, L0B are the first 3 bands in cube order)
          - PCAM: 0 (no Bayer bands)

        The cube bands are in the order they were loaded, so we identify
        the Bayer bands positionally (first N bands) then sort each group
        independently by wavelength for display.

        Returns:
            nb_wls, nb_spectrum, nb_std, bayer_wls, bayer_spectrum, bayer_std
            All as plain Python lists, wavelength-sorted within each group.
        """
        instrument      = instrument_config.get('instrument', 'ZCAM')
        n_rgb           = 3 if instrument == 'ZCAM' else 0
        all_wavelengths = np.array(instrument_config.get('wavelengths', []))

        spectrum = np.array(spectrum)
        std      = np.array(std)
        n        = len(spectrum)
        wls      = all_wavelengths[:n]

        # Split positionally in cube band order (Bayer bands are always first)
        bayer_wls_raw  = wls[:n_rgb]
        bayer_spec_raw = spectrum[:n_rgb]
        bayer_std_raw  = std[:n_rgb]

        nb_wls_raw  = wls[n_rgb:]
        nb_spec_raw = spectrum[n_rgb:]
        nb_std_raw  = std[n_rgb:]

        # Sort each group by wavelength for display
        if len(nb_wls_raw) > 0:
            ix          = np.argsort(nb_wls_raw)
            nb_wls      = nb_wls_raw[ix].tolist()
            nb_spectrum = nb_spec_raw[ix].tolist()
            nb_std      = nb_std_raw[ix].tolist()
        else:
            nb_wls, nb_spectrum, nb_std = [], [], []

        if len(bayer_wls_raw) > 0:
            ix             = np.argsort(bayer_wls_raw)
            bayer_wls      = bayer_wls_raw[ix].tolist()
            bayer_spectrum = bayer_spec_raw[ix].tolist()
            bayer_std      = bayer_std_raw[ix].tolist()
        else:
            bayer_wls, bayer_spectrum, bayer_std = [], [], []

        return nb_wls, nb_spectrum, nb_std, bayer_wls, bayer_spectrum, bayer_std

    def extract_roi_data(self, result, instrument_config):
        """
        Extracts ROI data with spectra from SparcResult.

        Uses instrument_config to determine bayer_cutoff and wavelengths,
        so this works correctly for both ZCAM and PCAM.
        """
        rois = []
        for i, (roi_rect, spectrum, std) in enumerate(
            zip(result.final_rois, result.final_spectra, result.final_stds)
        ):
            x, y, w, h = roi_rect

            mask = np.zeros(result.segments.shape, dtype=bool)
            mask[y:y+h, x:x+w] = True

            nb_wls, nb_spec, nb_std, bwls, bspec, bstd = self._split_spectrum(
                spectrum, std, instrument_config
            )

            rois.append({
                'roi':               roi_rect,
                'mask':              mask,
                'spectrum':          nb_spec,
                'std':               nb_std,
                'wavelengths':       nb_wls,
                'bayer_spectrum':    bspec,
                'bayer_std':         bstd,
                'bayer_wavelengths': bwls,
                'mineral':           f'ROI_{i+1}',
            })

        return rois

    def update_roi_spectrum(self, cube, rect, instrument_config):
        """
        Calculates spectrum for a modified ROI rectangle.

        Args:
            cube: The hyperspectral data cube (bands, height, width)
            rect: Tuple (x, y, w, h)
            instrument_config: Dict from state.instrument_config

        Returns:
            dict with spectrum keys matching extract_roi_data
        """
        x, y, w, h = map(int, rect)
        h_cube, w_cube = cube.shape[1], cube.shape[2]
        x = max(0, min(x, w_cube - 1))
        y = max(0, min(y, h_cube - 1))
        w = max(1, min(w, w_cube - x))
        h = max(1, min(h, h_cube - y))

        crop = cube[:, y:y+h, x:x+w]

        if np.ma.is_masked(crop):
            flat     = crop.reshape(crop.shape[0], -1)
            spectrum = np.ma.mean(flat, axis=1).filled(np.nan)
            std      = np.ma.std(flat, axis=1).filled(np.nan)
        else:
            spectrum = np.nanmean(crop, axis=(1, 2))
            std      = np.nanstd(crop, axis=(1, 2))

        nb_wls, nb_spec, nb_std, bwls, bspec, bstd = self._split_spectrum(
            spectrum, std, instrument_config
        )

        return {
            'roi':               (x, y, w, h),
            'spectrum':          nb_spec,
            'std':               nb_std,
            'wavelengths':       nb_wls,
            'bayer_spectrum':    bspec,
            'bayer_std':         bstd,
            'bayer_wavelengths': bwls,
        }