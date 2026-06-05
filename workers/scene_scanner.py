"""Background thread for scanning IOF files and generating scene thumbnails."""

import re
import numpy as np
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap

from sparc.data.loading import _scan_and_split, _bandset_from_group


_PCAM_FILENAME_RE = re.compile(
    r'^\d P \d{9} [A-Z]{3} [A-Z0-9]{4} [A-Z]\d{4} [LR]\d [A-Z0-9].+$',
    re.IGNORECASE | re.VERBOSE,
)


def detect_instrument(folder_path):
    """Return 'PCAM' if Pancam filenames are found in the folder, 'ZCAM' otherwise."""
    for f in Path(folder_path).rglob('*'):
        if f.suffix.upper() in ('.IMG', '.IMQ') and _PCAM_FILENAME_RE.match(f.name):
            return 'PCAM'
    return 'ZCAM'


class SceneScanThread(QThread):
    """Scans an IOF folder and emits thumbnails as scenes are found.

    Auto-detects instrument from filename patterns.
    complete is True when all expected bands are present.
    sort_key is (sol, sequence, pointing) for ordering in the panel.
    """

    scene_found   = pyqtSignal(str, object, str, str, object, int, str, bool, object)
    scan_complete = pyqtSignal(int)
    scan_error    = pyqtSignal(str)

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        try:
            instrument = detect_instrument(self.folder_path)
            if instrument == 'PCAM':
                scenes = self._find_pcam_scenes(self.folder_path)
                for scene_id, (path, seq_id, obs_ix) in scenes.items():
                    try:
                        pixmap, metadata, complete = self._load_pcam_thumbnail(path, seq_id, obs_ix)
                        if pixmap is not None:
                            pma     = metadata.get('pma')
                            sol     = metadata.get('sol', '?')
                            seq     = metadata.get('sequence', scene_id)
                            full_id = (f"Sol{sol:04d}_{seq}_PMA{pma}"
                                       if isinstance(sol, int) and pma is not None
                                       else scene_id)
                            self.scene_found.emit(
                                full_id, pixmap,
                                self._label(metadata, path, obs_ix),
                                str(path), seq_id, obs_ix, 'PCAM',
                                complete, self._sort_key(metadata),
                            )
                    except Exception as e:
                        import traceback
                        self.scan_error.emit(f"Thumbnail failed for {scene_id}: {e}\n{traceback.format_exc()}")
                        continue
            else:
                scenes = self._find_zcam_scenes(self.folder_path)
                for scene_id, (path, seq_id, obs_ix) in scenes.items():
                    try:
                        pixmap, metadata, complete = self._load_zcam_thumbnail(path, seq_id, obs_ix)
                        if pixmap is not None:
                            self.scene_found.emit(
                                scene_id, pixmap,
                                self._label(metadata, path, obs_ix),
                                str(path), seq_id, obs_ix, 'ZCAM',
                                complete, self._sort_key(metadata),
                            )
                    except Exception:
                        continue

            self.scan_complete.emit(len(scenes))

        except Exception as e:
            self.scan_error.emit(str(e))

    # ------------------------------------------------------------------
    # ZCAM
    # ------------------------------------------------------------------

    def _find_zcam_scenes(self, folder_path):
        scenes = {}
        for parent_dir in {f.parent for f in Path(folder_path).rglob('*.IMG') if f.is_file()}:
            try:
                for obs_ix, group in enumerate(_scan_and_split(parent_dir)):
                    try:
                        bs = _bandset_from_group(group)
                        if len(bs.metadata) >= 3:
                            scene_id = bs.name or f"{parent_dir.name}_{obs_ix:03d}"
                            scenes[scene_id] = (parent_dir, None, obs_ix)
                    except Exception:
                        continue
            except Exception:
                continue
        return scenes

    def _load_zcam_thumbnail(self, path, seq_id, obs_ix):
        from marslab.imgops.imgutils import crop
        from asdf_settings import rapidlooks

        groups = _scan_and_split(path, seq_id)
        if obs_ix >= len(groups):
            return None, None, False

        bs       = _bandset_from_group(groups[obs_ix])
        metadata = self._zcam_metadata(bs, seq_id, path)

        if 'BAND' not in bs.metadata.columns:
            return None, None, False

        available = bs.metadata['BAND'].tolist()

        from sparc.core.constants import get_instrument_config
        n_expected = len(get_instrument_config('ZCAM')['wavelengths'])
        complete   = len(available) >= n_expected

        band = next((b for b in ('R1', 'L1', 'R0R', 'L0R') if b in available), None)
        if band is None:
            return None, None, False

        bs.load([band])
        if '0' in band:
            bs.bulk_debayer([band])

        crop_settings = rapidlooks.CROP_SETTINGS["crop"]
        gray = crop(bs.get_band(band), crop_settings).astype(np.float32)
        return self._to_grayscale_pixmap(gray), metadata, complete

    def _zcam_metadata(self, bs, seq_id, path):
        metadata = {}
        if hasattr(bs, 'metadata') and bs.metadata is not None:
            for field, key in (('SOL', 'sol'), ('SEQ_ID', 'sequence')):
                if field in bs.metadata.columns:
                    try:
                        vals = bs.metadata[field].unique()
                        if len(vals) > 0 and vals[0] is not None:
                            metadata[key] = int(vals[0]) if key == 'sol' else str(vals[0])
                    except Exception:
                        pass
            if 'RSM' in bs.metadata.columns:
                try:
                    metadata['rsm'] = int(bs.metadata['RSM'].min())
                except Exception:
                    pass
        metadata.setdefault('sol', '?')
        metadata.setdefault('sequence', seq_id or path.name)
        return metadata

    # ------------------------------------------------------------------
    # PCAM
    # ------------------------------------------------------------------

    def _find_pcam_scenes(self, folder_path):
        from sparc.utils.pancam_helpers import scan_pcam_files, split_pcam_observations

        scenes = {}
        for parent_dir in {f.parent for f in Path(folder_path).rglob('*')
                           if f.suffix.upper() in ('.IMG', '.IMQ')}:
            try:
                products = scan_pcam_files(parent_dir)
                obs_ix   = 0
                for _, group in products.groupby('SEQ_ID'):
                    for obs in split_pcam_observations(group):
                        seq_id   = obs['SEQ_ID'].iloc[0]
                        scene_id = f"{seq_id}_{obs_ix:03d}"
                        scenes[scene_id] = (parent_dir, seq_id, obs_ix)
                        obs_ix  += 1
            except Exception:
                continue
        return scenes

    def _load_pcam_thumbnail(self, path, seq_id, obs_ix):
        from sparc.utils.pancam_helpers import scan_pcam_files, split_pcam_observations
        import pdr

        products     = scan_pcam_files(path, seq_id=seq_id)
        observations = []
        for _, group in products.groupby('SEQ_ID'):
            observations.extend(split_pcam_observations(group))

        if obs_ix >= len(observations):
            return None, None, False
        observation = observations[obs_ix]

        available = set(observation['BAND'].tolist())

        from sparc.core.constants import get_instrument_config
        n_expected = len(get_instrument_config('PCAM')['wavelengths'])
        complete   = len(available) >= n_expected

        metadata = {}
        metadata.setdefault('sequence', seq_id or path.name)
        metadata['sol'] = '?'

        band = next((b for b in ('L5', 'L4', 'L6', 'L3') if b in available), None)
        if band is None:
            return None, None, False

        row   = observation[observation['BAND'] == band].iloc[0]
        fpath = row['PATH']
        d     = pdr.Data(fpath)
        label = d.metadata

        try:
            metadata['sol'] = int(label['PLANET_DAY_NUMBER'])
        except Exception:
            pass
        try:
            metadata['sequence'] = str(label['SEQUENCE_ID']).strip()
        except Exception:
            pass
        try:
            rmc = label['ROVER_MOTION_COUNTER']
            metadata['pma'] = int(rmc[3])  # PMA is index 3: (SITE, DRIVE, IDD, PMA, HGA)
        except Exception:
            pass

        scale  = label['DERIVED_IMAGE_PARMS']['RADIANCE_SCALING_FACTOR']
        offset = label['DERIVED_IMAGE_PARMS']['RADIANCE_OFFSET']
        dn     = d['IMAGE'].copy().astype(np.float32)
        dn     = np.where((dn == 0) | (dn == 4095), np.nan, dn)
        gray   = dn * scale + offset

        return self._to_grayscale_pixmap(gray), metadata, complete

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _sort_key(metadata):
        """Return (sol, sequence, pointing) for panel ordering.

        Unknown sol sorts to the end. pointing is rsm for ZCAM, pma for PCAM.
        """
        sol      = metadata.get('sol', '?')
        sol      = sol if isinstance(sol, int) else float('inf')
        sequence = metadata.get('sequence', '')
        pointing = metadata.get('rsm', metadata.get('pma', float('inf')))
        return (sol, sequence, pointing)

    @staticmethod
    def _label(metadata, path, obs_ix):
        sol      = metadata.get('sol', '?')
        sequence = metadata.get('sequence', path.name)
        if 'rsm' in metadata:
            return f"Sol {sol} | {sequence} | RSM{metadata['rsm']}"
        if 'pma' in metadata:
            return f"Sol {sol} | {sequence} | PMA{metadata['pma']}"
        return f"Sol {sol} | {sequence} | Obs {obs_ix:03d}"

    @staticmethod
    def _to_grayscale_pixmap(gray: np.ndarray) -> QPixmap:
        """Percentile-stretch a single-band float array and return a grayscale QPixmap."""
        gray  = np.ma.filled(gray, np.nan) if np.ma.is_masked(gray) else np.asarray(gray)
        gray  = np.nan_to_num(gray, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
        valid = gray[gray > 0]
        if valid.size > 0:
            lo, hi = np.percentile(valid, [1, 98])
            gray   = np.clip((gray - lo) / (hi - lo) if hi > lo else gray, 0.0, 1.0)
        img = (np.stack([gray] * 3, axis=-1) * 255).astype(np.uint8)
        img = np.ascontiguousarray(img)
        h, w = img.shape[:2]
        return QPixmap.fromImage(QImage(img.data, w, h, 3 * w, QImage.Format_RGB888).copy())