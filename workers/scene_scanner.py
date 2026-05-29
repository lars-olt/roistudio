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
    """

    scene_found   = pyqtSignal(str, object, str, str, object, int, str)
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
                        rgb_img, metadata = self._load_pcam_thumbnail(path, seq_id, obs_ix)
                        if rgb_img is not None:
                            self.scene_found.emit(
                                scene_id,
                                self._to_pixmap(rgb_img),
                                self._label(metadata, path, obs_ix),
                                str(path), seq_id, obs_ix, 'PCAM',
                            )
                    except Exception as e:
                        import traceback
                        self.scan_error.emit(f"Thumbnail failed for {scene_id}: {e}\n{traceback.format_exc()}")
                        continue
            else:
                scenes = self._find_zcam_scenes(self.folder_path)
                for scene_id, (path, seq_id, obs_ix) in scenes.items():
                    try:
                        rgb_img, metadata = self._load_zcam_thumbnail(path, seq_id, obs_ix)
                        if rgb_img is not None:
                            self.scene_found.emit(
                                scene_id,
                                self._to_pixmap(rgb_img),
                                self._label(metadata, path, obs_ix),
                                str(path), seq_id, obs_ix, 'ZCAM',
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
                            scenes[f"{parent_dir.name}_{obs_ix:03d}"] = (parent_dir, None, obs_ix)
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
            return None, None

        bs       = _bandset_from_group(groups[obs_ix])
        metadata = self._zcam_metadata(bs, seq_id, path)

        if 'BAND' not in bs.metadata.columns:
            return None, None

        available = bs.metadata['BAND'].tolist()
        for candidate in (['R1', 'G1', 'B1'], ['R0R', 'R0G', 'R0B'], ['L0R', 'L0G', 'L0B']):
            if all(b in available for b in candidate):
                rgb_bands = candidate
                break
        else:
            return None, None

        bs.load(rgb_bands)
        if any('0' in b for b in rgb_bands):
            bs.bulk_debayer(rgb_bands)

        crop_settings = rapidlooks.CROP_SETTINGS["crop"]
        bands = [crop(bs.get_band(b), crop_settings) for b in rgb_bands]
        return self._stretch_rgb(np.stack(bands, axis=-1)), metadata

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
        metadata.setdefault('sol', '?')
        metadata.setdefault('sequence', seq_id or path.name)
        return metadata

    # ------------------------------------------------------------------
    # PCAM
    # ------------------------------------------------------------------

    def _find_pcam_scenes(self, folder_path):
        from sparc.utils.pancam_helpers import scan_pcam_files

        scenes = {}
        for parent_dir in {f.parent for f in Path(folder_path).rglob('*')
                           if f.suffix.upper() in ('.IMG', '.IMQ')}:
            try:
                products = scan_pcam_files(parent_dir)
                for obs_ix, (seq_id, _) in enumerate(products.groupby('SEQ_ID')):
                    scenes[f"{parent_dir.name}_{obs_ix:03d}"] = (parent_dir, seq_id, obs_ix)
            except Exception:
                continue
        return scenes

    def _load_pcam_thumbnail(self, path, seq_id, obs_ix):
        from sparc.utils.pancam_helpers import scan_pcam_files, get_pcam_bandset
        import pdr

        # Build the metadata directly - we only need PATH, BAND, and scaling params.
        # We bypass PcamBandSet.load() because it uses an internal file reference
        # that doesn't respect our PATH normalization on lowercase-extension files.
        products    = scan_pcam_files(path, seq_id=seq_id)
        clusters    = {k: v for k, v in products.groupby('SEQ_ID')}
        observation = list(clusters.values())[obs_ix]

        metadata = {}
        metadata.setdefault('sequence', seq_id or path.name)
        metadata['sol'] = '?'

        rgb_bands = ['L4', 'L5', 'L6']
        rows = observation[observation['BAND'].isin(rgb_bands)]
        if len(rows) < len(rgb_bands):
            return None, None

        bands = {}
        first_label = None
        for _, row in rows.iterrows():
            band   = row['BAND']
            fpath  = row['PATH']
            d      = pdr.Data(fpath)
            label  = d.metadata
            if first_label is None:
                first_label = label
            scale  = label['DERIVED_IMAGE_PARMS']['RADIANCE_SCALING_FACTOR']
            offset = label['DERIVED_IMAGE_PARMS']['RADIANCE_OFFSET']
            dn     = d['IMAGE'].copy().astype(np.float32)
            dn     = np.where((dn == 0) | (dn == 4095), np.nan, dn)
            bands[band] = dn * scale + offset

        if first_label is not None:
            try:
                metadata['sol'] = int(first_label['PLANET_DAY_NUMBER'])
            except Exception:
                pass
            try:
                metadata['sequence'] = str(first_label['SEQUENCE_ID']).strip()
            except Exception:
                pass

        if not all(b in bands for b in rgb_bands):
            return None, None

        rgb = np.stack([np.nan_to_num(bands[b], nan=0.0) for b in rgb_bands], axis=-1)
        return self._stretch_rgb(rgb), metadata

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _label(metadata, path, obs_ix):
        return (f"Sol {metadata.get('sol', '?')} | "
                f"{metadata.get('sequence', path.name)} | "
                f"Obs {obs_ix:03d}")

    @staticmethod
    def _stretch_rgb(rgb):
        rgb    = np.nan_to_num(rgb, nan=0.0, posinf=0.0, neginf=0.0)
        lo, hi = (np.percentile(rgb[rgb > 0], [1, 98]) if np.any(rgb > 0) else (0, 1))
        rgb    = np.clip((rgb - lo) / (hi - lo) if hi > lo else rgb, 0, 1)
        return (rgb * 255).astype(np.uint8)

    @staticmethod
    def _to_pixmap(img_array):
        img_array = np.ascontiguousarray(img_array)
        h, w      = img_array.shape[:2]
        return QPixmap.fromImage(QImage(img_array.data, w, h, 3 * w, QImage.Format_RGB888).copy())