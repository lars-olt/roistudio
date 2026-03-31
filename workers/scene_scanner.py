from PyQt5.QtCore import QThread, pyqtSignal
from pathlib import Path
import re
import numpy as np
from PyQt5.QtGui import QImage, QPixmap


# Pancam filename pattern (from pancam_helpers.py)
_PCAM_FILENAME_RE = re.compile(
    r'^\d'
    r'P'
    r'\d{9}'
    r'[A-Z]{3}'
    r'[A-Z0-9]{4}'
    r'[A-Z]\d{4}'
    r'[LR]\d'
    r'[A-Z0-9]'
    r'.+$',
    re.IGNORECASE,
)


def detect_instrument(folder_path):
    """
    Detects instrument type from filenames in folder.

    Returns 'PCAM' if Pancam filenames are found, 'ZCAM' otherwise.
    Pancam files match the MER naming convention (1P<SCLK>...).
    ZCAM files are assumed if no Pancam match is found.
    """
    folder = Path(folder_path)
    for f in folder.rglob('*'):
        if f.suffix.upper() in ('.IMG', '.IMQ'):
            if _PCAM_FILENAME_RE.match(f.name):
                return 'PCAM'
    return 'ZCAM'


class SceneScanThread(QThread):
    """
    Background thread for scanning IOF files and generating thumbnails.
    Auto-detects instrument (ZCAM or PCAM) from filename patterns.
    """
    # scene_id, pixmap, filename, folder_path, seq_id, obs_ix, instrument
    scene_found = pyqtSignal(str, object, str, str, object, int, str)
    scan_complete = pyqtSignal(int)
    scan_error = pyqtSignal(str)

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
                            pixmap = self._numpy_to_pixmap(rgb_img)
                            sol = metadata.get('sol', '?')
                            sequence = metadata.get('sequence', path.name)
                            filename = f"Sol {sol} | {sequence} | Obs {obs_ix:03d}"
                            self.scene_found.emit(
                                scene_id, pixmap, filename,
                                str(path), seq_id, obs_ix, 'PCAM'
                            )
                    except Exception:
                        continue
            else:
                scenes = self._find_zcam_scenes(self.folder_path)
                for scene_id, (path, seq_id, obs_ix) in scenes.items():
                    try:
                        rgb_img, metadata = self._load_zcam_thumbnail(path, seq_id, obs_ix)
                        if rgb_img is not None:
                            pixmap = self._numpy_to_pixmap(rgb_img)
                            sol = metadata.get('sol', '?')
                            sequence = metadata.get('sequence', path.name)
                            filename = f"Sol {sol} | {sequence} | Obs {obs_ix:03d}"
                            self.scene_found.emit(
                                scene_id, pixmap, filename,
                                str(path), seq_id, obs_ix, 'ZCAM'
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
        """Finds all unique ZCAM IOF scenes in folder and subdirectories."""
        from rapid.helpers import get_zcam_bandset

        folder = Path(folder_path)
        img_files = [f for f in folder.rglob('*.IMG') if f.is_file()]

        scenes = {}
        checked_dirs = set()
        parent_dirs = set(f.parent for f in img_files)

        for parent_dir in parent_dirs:
            if parent_dir in checked_dirs:
                continue
            checked_dirs.add(parent_dir)

            obs_ix = 0
            while obs_ix < 100:
                try:
                    bs = get_zcam_bandset(
                        parent_dir, seq_id=None,
                        observation_ix=obs_ix, load=False
                    )
                    filts = bs.metadata["BAND"].sort_values()
                    if len(filts) > 0:
                        scene_id = f"{parent_dir.name}_{obs_ix:03d}"
                        scenes[scene_id] = (parent_dir, None, obs_ix)
                        obs_ix += 1
                    else:
                        break
                except Exception:
                    break

        return scenes

    def _load_zcam_thumbnail(self, path, seq_id, obs_ix):
        """Loads RGB bayer bands for a ZCAM thumbnail."""
        from rapid.helpers import get_zcam_bandset
        from marslab.imgops.imgutils import crop
        from asdf_settings import rapidlooks

        bs = get_zcam_bandset(path, seq_id=seq_id, observation_ix=obs_ix, load=False)

        metadata = {}
        if hasattr(bs, 'metadata') and bs.metadata is not None:
            if 'SOL' in bs.metadata.columns:
                try:
                    vals = bs.metadata['SOL'].unique()
                    if len(vals) > 0 and vals[0] is not None:
                        metadata['sol'] = int(vals[0])
                except Exception:
                    pass
            if 'SEQ_ID' in bs.metadata.columns:
                try:
                    vals = bs.metadata['SEQ_ID'].unique()
                    if len(vals) > 0 and vals[0] is not None:
                        metadata['sequence'] = str(vals[0])
                except Exception:
                    pass

        metadata.setdefault('sol', '?')
        metadata.setdefault('sequence', seq_id or path.name)

        if 'BAND' not in bs.metadata:
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
        r = crop(bs.get_band(rgb_bands[0]), crop_settings)
        g = crop(bs.get_band(rgb_bands[1]), crop_settings)
        b = crop(bs.get_band(rgb_bands[2]), crop_settings)

        rgb_img = self._stretch_rgb(np.stack([r, g, b], axis=-1))
        return rgb_img, metadata

    # ------------------------------------------------------------------
    # PCAM
    # ------------------------------------------------------------------

    def _find_pcam_scenes(self, folder_path):
        """Finds all unique Pancam IOF scenes in folder and subdirectories."""
        from sparc.utils.pancam_helpers import scan_pcam_files, get_pcam_bandset

        folder = Path(folder_path)
        img_files = [f for f in folder.rglob('*') if f.suffix.upper() in ('.IMG', '.IMQ')]

        scenes = {}
        checked_dirs = set()
        parent_dirs = set(f.parent for f in img_files)

        for parent_dir in parent_dirs:
            if parent_dir in checked_dirs:
                continue
            checked_dirs.add(parent_dir)

            try:
                products = scan_pcam_files(parent_dir)
                clusters = {k: v for k, v in products.groupby('SEQ_ID')}
                for obs_ix, (seq_id, _) in enumerate(clusters.items()):
                    scene_id = f"{parent_dir.name}_{obs_ix:03d}"
                    scenes[scene_id] = (parent_dir, seq_id, obs_ix)
            except Exception:
                continue

        return scenes

    def _load_pcam_thumbnail(self, path, seq_id, obs_ix):
        """Loads L2/L5/L6 bands for a Pancam thumbnail."""
        from sparc.utils.pancam_helpers import get_pcam_bandset
        import pdr

        bs = get_pcam_bandset(path, seq_id=seq_id, observation_ix=obs_ix, load=False)

        metadata = {}
        if hasattr(bs, 'metadata') and bs.metadata is not None:
            if 'SOL' in bs.metadata.columns:
                try:
                    vals = bs.metadata['SOL'].unique()
                    if len(vals) > 0 and vals[0] is not None:
                        metadata['sol'] = int(vals[0])
                except Exception:
                    pass
            if 'SEQ_ID' in bs.metadata.columns:
                try:
                    vals = bs.metadata['SEQ_ID'].unique()
                    if len(vals) > 0 and vals[0] is not None:
                        metadata['sequence'] = str(vals[0])
                except Exception:
                    pass

        metadata.setdefault('sol', '?')
        metadata.setdefault('sequence', seq_id or path.name)

        if 'BAND' not in bs.metadata:
            return None, None

        available = bs.metadata['BAND'].tolist()
        rgb_bands = ['L2', 'L5', 'L6']
        if not all(b in available for b in rgb_bands):
            return None, None

        bs.load(rgb_bands)

        # Convert DN -> IOF using PDS label scale/offset, same as _load_pcam_cube
        bands = {}
        for _, row in bs.metadata[bs.metadata['BAND'].isin(rgb_bands)].iterrows():
            band = row['BAND']
            label = pdr.Data(row['PATH']).metadata
            scale  = label['DERIVED_IMAGE_PARMS']['RADIANCE_SCALING_FACTOR']
            offset = label['DERIVED_IMAGE_PARMS']['RADIANCE_OFFSET']
            dn = bs.get_band(band).copy().astype(np.float32)
            dn = np.where((dn == 0) | (dn == 4095), np.nan, dn)
            bands[band] = dn * scale + offset

        r = np.nan_to_num(bands['L2'], nan=0.0)
        g = np.nan_to_num(bands['L5'], nan=0.0)
        b = np.nan_to_num(bands['L6'], nan=0.0)

        rgb_img = self._stretch_rgb(np.stack([r, g, b], axis=-1))
        return rgb_img, metadata

    # ------------------------------------------------------------------
    # Shared utilities
    # ------------------------------------------------------------------

    def _stretch_rgb(self, rgb):
        """Percentile stretch to uint8."""
        rgb = np.nan_to_num(rgb, nan=0.0, posinf=0.0, neginf=0.0)
        lo, hi = np.percentile(rgb[rgb > 0], [1, 98]) if np.any(rgb > 0) else (0, 1)
        rgb = np.clip((rgb - lo) / (hi - lo) if hi > lo else rgb, 0, 1)
        return (rgb * 255).astype(np.uint8)

    def _numpy_to_pixmap(self, img_array):
        """Converts uint8 HxWx3 numpy array to QPixmap."""
        img_array = np.ascontiguousarray(img_array)
        h, w = img_array.shape[:2]
        q_image = QImage(img_array.data, w, h, 3 * w, QImage.Format_RGB888)
        return QPixmap.fromImage(q_image.copy())