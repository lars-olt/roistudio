import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal

from workers.sparc_runner import SparcRunThread


class SparcController(QObject):
    """Handles SPARC pipeline execution and spectrum computation."""

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
        self._sparc_thread = SparcRunThread(
            sam_path, folder_path, seq_id, obs_ix, instrument,
            params, load_result, presegmented,
        )
        self._sparc_thread.status_update.connect(self.status_update.emit)
        self._sparc_thread.sparc_complete.connect(self.complete.emit)
        self._sparc_thread.sparc_error.connect(self.error.emit)
        self._sparc_thread.start()
        self.started.emit()

    # ------------------------------------------------------------------
    # Spectrum helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _slice_cube(cube, rect):
        """Mean spectrum and std over a (x, y, w, h) rect."""
        x, y, w, h = (max(0, int(v)) for v in rect)
        h_c, w_c   = cube.shape[1], cube.shape[2]
        x = min(x, w_c - 1); w = max(1, min(w, w_c - x))
        y = min(y, h_c - 1); h = max(1, min(h, h_c - y))
        crop = cube[:, y:y+h, x:x+w]
        if np.ma.is_masked(crop):
            flat = crop.reshape(crop.shape[0], -1)
            return np.ma.mean(flat, axis=1).filled(np.nan), np.ma.std(flat, axis=1).filled(np.nan)
        return np.nanmean(crop, axis=(1, 2)), np.nanstd(crop, axis=(1, 2))

    def compute_dual_spectrum(self, load_result, left_rect, right_rect):
        """
        Compute merged and per-camera spectra from the band recipe.

        Returns:
            merged: (spectrum, std) - stereo bands averaged, shape (n_bands,)
            left:   (spectrum, std, wavelengths) - all left-camera bands incl. stereo
            right:  (spectrum, std, wavelengths) - all right-camera bands incl. stereo
        """
        recipe     = load_result['merged_band_recipe']
        left_keys  = load_result['left_band_keys']
        right_keys = load_result['right_band_keys']
        wl_lookup  = load_result['bandset'].metadata.set_index('BAND')['WAVELENGTH'].to_dict()

        left_spec,  left_std  = self._slice_cube(load_result['left_cube'],  left_rect)
        right_spec, right_std = self._slice_cube(load_result['right_cube'], right_rect)

        left_idx  = {name: i for i, name in enumerate(left_keys)}
        right_idx = {name: i for i, name in enumerate(right_keys)}

        merged_spec = np.empty(len(recipe))
        merged_std  = np.empty(len(recipe))
        left_bands  = []  # (wavelength, value, std)
        right_bands = []

        for i, (source, _name, l_key, r_key) in enumerate(recipe):
            if source == 'stereo':
                ls, lstd = left_spec[left_idx[l_key]],   left_std[left_idx[l_key]]
                rs, rstd = right_spec[right_idx[r_key]], right_std[right_idx[r_key]]
                merged_spec[i] = (ls + rs) / 2
                merged_std[i]  = np.sqrt((lstd**2 + rstd**2) / 2)
                left_bands.append( (wl_lookup[l_key], ls, lstd))
                right_bands.append((wl_lookup[r_key], rs, rstd))
            elif source == 'left_only':
                merged_spec[i] = left_spec[left_idx[l_key]]
                merged_std[i]  = left_std[left_idx[l_key]]
                left_bands.append((wl_lookup[l_key],
                                   left_spec[left_idx[l_key]],
                                   left_std[left_idx[l_key]]))
            else:
                merged_spec[i] = right_spec[right_idx[r_key]]
                merged_std[i]  = right_std[right_idx[r_key]]
                right_bands.append((wl_lookup[r_key],
                                    right_spec[right_idx[r_key]],
                                    right_std[right_idx[r_key]]))

        def _sorted_camera_bands(bands):
            if not bands:
                return [], [], []
            bands.sort(key=lambda t: t[0])
            wls  = [t[0] for t in bands]
            spec = [t[1] for t in bands]
            std  = [t[2] for t in bands]
            return wls, spec, std

        l_wls, l_spec, l_std = _sorted_camera_bands(left_bands)
        r_wls, r_spec, r_std = _sorted_camera_bands(right_bands)

        return (
            (merged_spec, merged_std),
            (l_spec, l_std, l_wls),
            (r_spec, r_std, r_wls),
        )

    @staticmethod
    def _split_spectrum(spectrum, std, instrument_config):
        """
        Split into non-Bayer (plotted as a line) and Bayer (plotted as dots)
        bands, each wavelength-sorted.
        """
        instrument = instrument_config.get('instrument', 'ZCAM')
        n_rgb      = 3 if instrument == 'ZCAM' else 0
        wls        = np.array(instrument_config.get('wavelengths', []))[:len(spectrum)]

        spectrum = np.array(spectrum)
        std      = np.array(std)

        nb_ix   = np.argsort(wls[n_rgb:])
        nb_wls  = wls[n_rgb:][nb_ix].tolist()
        nb_spec = spectrum[n_rgb:][nb_ix].tolist()
        nb_std  = std[n_rgb:][nb_ix].tolist()

        if n_rgb > 0:
            b_ix   = np.argsort(wls[:n_rgb])
            b_wls  = wls[:n_rgb][b_ix].tolist()
            b_spec = spectrum[:n_rgb][b_ix].tolist()
            b_std  = std[:n_rgb][b_ix].tolist()
        else:
            b_wls = b_spec = b_std = []

        return nb_wls, nb_spec, nb_std, b_wls, b_spec, b_std

    def update_roi_spectrum_dual(self, load_result, left_rect, right_rect, instrument_config):
        """Recompute ROI display data after a rect has moved."""
        (merged_spec, merged_std), (l_spec, l_std, l_wls), (r_spec, r_std, r_wls) = \
            self.compute_dual_spectrum(load_result, left_rect, right_rect)

        nb_wls, nb_spec, nb_std, bwls, bspec, bstd = self._split_spectrum(
            merged_spec, merged_std, instrument_config
        )
        return {
            'spectrum':            nb_spec,
            'std':                 nb_std,
            'wavelengths':         nb_wls,
            'bayer_spectrum':      bspec,
            'bayer_std':           bstd,
            'bayer_wavelengths':   bwls,
            'left_spectrum':       l_spec,
            'left_std':            l_std,
            'left_wavelengths':    l_wls,
            'right_spectrum':      r_spec,
            'right_std':           r_std,
            'right_wavelengths':   r_wls,
        }

    def update_roi_spectrum(self, cube, rect, instrument_config):
        """Single-cube fallback for manual ROI creation."""
        spectrum, std = self._slice_cube(cube, rect)
        x, y, w, h    = (max(0, int(v)) for v in rect)
        nb_wls, nb_spec, nb_std, bwls, bspec, bstd = self._split_spectrum(
            spectrum, std, instrument_config
        )
        return {
            'roi':               (x, y, w, h),
            'right_rect':        (x, y, w, h),
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
        }

    def extract_roi_data(self, result, instrument_config):
        """Build the ROI data list from a SparcResult."""
        rois = []
        for i, (right_rect, left_rect, spectrum, std) in enumerate(
            zip(result.final_rois, result.final_left_rois,
                result.final_spectra, result.final_stds)
        ):
            x, y, w, h = right_rect
            mask = np.zeros(result.segments.shape, dtype=bool)
            mask[y:y+h, x:x+w] = True
            nb_wls, nb_spec, nb_std, bwls, bspec, bstd = self._split_spectrum(
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
                # per-camera fields populated after recompute in on_sparc_complete
                'left_spectrum':     [],
                'left_std':          [],
                'left_wavelengths':  [],
                'right_spectrum':    [],
                'right_std':         [],
                'right_wavelengths': [],
                'mineral':           f'ROI_{i+1}',
            })
        return rois