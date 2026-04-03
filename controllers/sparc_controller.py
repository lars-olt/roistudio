from PyQt5.QtCore import QObject, pyqtSignal
import numpy as np


class SparcController(QObject):
    """Handles SPARC pipeline execution."""

    started       = pyqtSignal()
    stopped       = pyqtSignal()
    status_update = pyqtSignal(str)
    complete      = pyqtSignal(object)
    error         = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._sparc_thread = None

    def start_sparc(self, sam_path, folder_path, seq_id, obs_ix, instrument, max_components=9):
        from workers.sparc_runner import SparcRunThread
        self._sparc_thread = SparcRunThread(
            sam_path, folder_path, seq_id, obs_ix, instrument, max_components
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
        h_c, w_c = cube.shape[1], cube.shape[2]
        x = min(x, w_c - 1);  w = max(1, min(w, w_c - x))
        y = min(y, h_c - 1);  h = max(1, min(h, h_c - y))
        crop = cube[:, y:y+h, x:x+w]
        if np.ma.is_masked(crop):
            flat     = crop.reshape(crop.shape[0], -1)
            spectrum = np.ma.mean(flat, axis=1).filled(np.nan)
            std      = np.ma.std(flat,  axis=1).filled(np.nan)
        else:
            spectrum = np.nanmean(crop, axis=(1, 2))
            std      = np.nanstd(crop,  axis=(1, 2))
        return spectrum, std

    def compute_dual_spectrum(self, load_result, left_rect, right_rect):
        """
        Compute the merged spectrum from separate left- and right-camera rects.

        Driven by merged_band_recipe from load_result, which maps every merged-cube
        band to its named source band(s) in left_cube and right_cube. This is
        instrument-agnostic: ZCAM shared bands are positional; PCAM stereo pairs
        are scattered - but the recipe always tells us exactly which band index
        to read from which raw cube.

        left_rect and right_rect are in their respective camera's pixel space.
        """
        recipe     = load_result['merged_band_recipe']
        left_keys  = load_result['left_band_keys']
        right_keys = load_result['right_band_keys']
        left_cube  = load_result['left_cube']
        right_cube = load_result['right_cube']

        # Slice both raw cubes once; index into them by band name.
        left_spec,  left_std  = self._slice_cube(left_cube,  left_rect)
        right_spec, right_std = self._slice_cube(right_cube, right_rect)

        left_idx  = {name: i for i, name in enumerate(left_keys)}
        right_idx = {name: i for i, name in enumerate(right_keys)}

        spectrum = np.empty(len(recipe))
        std      = np.empty(len(recipe))

        for i, (source, _name, l_key, r_key) in enumerate(recipe):
            if source == 'stereo':
                ls = left_spec[left_idx[l_key]];   lstd = left_std[left_idx[l_key]]
                rs = right_spec[right_idx[r_key]];  rstd = right_std[right_idx[r_key]]
                spectrum[i] = (ls + rs) / 2
                std[i]      = np.sqrt((lstd**2 + rstd**2) / 2)
            elif source == 'left_only':
                spectrum[i] = left_spec[left_idx[l_key]]
                std[i]      = left_std[left_idx[l_key]]
            else:  # right_only
                spectrum[i] = right_spec[right_idx[r_key]]
                std[i]      = right_std[right_idx[r_key]]

        return spectrum, std

    def update_roi_spectrum_dual(self, load_result, left_rect, right_rect, instrument_config):
        """Recompute ROI display data after either rect has moved."""
        spectrum, std = self.compute_dual_spectrum(load_result, left_rect, right_rect)
        nb_wls, nb_spec, nb_std, bwls, bspec, bstd = self._split_spectrum(
            spectrum, std, instrument_config
        )
        return {
            'spectrum':          nb_spec,
            'std':               nb_std,
            'wavelengths':       nb_wls,
            'bayer_spectrum':    bspec,
            'bayer_std':         bstd,
            'bayer_wavelengths': bwls,
        }

    @staticmethod
    def _split_spectrum(spectrum, std, instrument_config):
        """Split into non-Bayer (line) and Bayer (dots) bands, each wavelength-sorted."""
        instrument      = instrument_config.get('instrument', 'ZCAM')
        n_rgb           = 3 if instrument == 'ZCAM' else 0
        all_wavelengths = np.array(instrument_config.get('wavelengths', []))

        spectrum = np.array(spectrum)
        std      = np.array(std)
        n        = len(spectrum)
        wls      = all_wavelengths[:n]

        bayer_wls_raw  = wls[:n_rgb];      nb_wls_raw  = wls[n_rgb:]
        bayer_spec_raw = spectrum[:n_rgb]; nb_spec_raw = spectrum[n_rgb:]
        bayer_std_raw  = std[:n_rgb];      nb_std_raw  = std[n_rgb:]

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
                'mineral':           f'ROI_{i+1}',
            })
        return rois

    def update_roi_spectrum(self, cube, rect, instrument_config):
        """Single-cube fallback for manual ROI creation."""
        spectrum, std = self._slice_cube(cube, rect)
        x, y, w, h = (max(0, int(v)) for v in rect)
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
        }