from PyQt5.QtCore import QThread, pyqtSignal
from pathlib import Path
import re
import numpy as np
import pandas as pd
from PyQt5.QtGui import QImage, QPixmap


_PCAM_FILENAME_RE = re.compile(
    r'^\d P \d{9} [A-Z]{3} [A-Z0-9]{4} [A-Z]\d{4} [LR]\d [A-Z0-9].+$',
    re.IGNORECASE | re.VERBOSE,
)


def _make_zcam_bandset_fallback(parent_dir, seq_id=None):
    """
    Build a ZcamBandSet bypassing rapid's cluster_observations.
    On Windows, asdf computes the stem column from the directory path rather
    than the file stem, so all files in a scene share one stem and compete as
    siblings. rate_cal_offset keeps only the single best-scoring file, dropping
    everything else. This fallback deduplicates per filter directly - one file
    per filter, chosen by the same cal_offset score - and hands the result
    straight to ZcamBandSet.
    """
    from asdf.scan import scan_zcam_files, rate_cal_offset
    from asdf.zcam_bandset import ZcamBandSet
    from functools import reduce
    from operator import mul

    all_obs = scan_zcam_files(parent_dir)
    if seq_id:
        all_obs = all_obs[
            all_obs['SEQ_ID'].str.lower().str.contains(str(seq_id).lower())
        ]

    # drop off-size subframes (focus/context frames) - keep only the
    # drop off-size subframes (focus/context frames) - keep only files
    # with the largest frame size
    frame_areas = all_obs['SUBFRAME'].map(lambda s: reduce(mul, s[2:]))
    all_obs     = all_obs[frame_areas == frame_areas.max()]

    keep_rows = []
    for _filt, group in all_obs.groupby('FILTER'):
        if len(group) == 1:
            keep_rows.append(group.iloc[0])
        else:
            scores = rate_cal_offset(group)
            keep_rows.append(group.loc[scores[scores].index[0]])

    deduped = pd.DataFrame(keep_rows).reset_index(drop=True)
    bs = ZcamBandSet(deduped)
    bs.format_metadata()
    return bs


def detect_instrument(folder_path):
    """Return 'PCAM' if Pancam filenames are found in the folder, 'ZCAM' otherwise."""
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
                                scene_id, self._numpy_to_pixmap(rgb_img),
                                f"Sol {metadata.get('sol', '?')} | "
                                f"{metadata.get('sequence', path.name)} | "
                                f"Obs {obs_ix:03d}",
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
                            self.scene_found.emit(
                                scene_id, self._numpy_to_pixmap(rgb_img),
                                f"Sol {metadata.get('sol', '?')} | "
                                f"{metadata.get('sequence', path.name)} | "
                                f"Obs {obs_ix:03d}",
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
        from rapid.helpers import get_zcam_bandset

        folder      = Path(folder_path)
        parent_dirs = {f.parent for f in folder.rglob('*.IMG') if f.is_file()}
        scenes      = {}

        for parent_dir in parent_dirs:
            obs_ix = 0
            while obs_ix < 100:
                try:
                    bs = get_zcam_bandset(
                        parent_dir, seq_id=None,
                        observation_ix=obs_ix, load=False
                    )
                    if len(bs.metadata) < 3:
                        bs    = _make_zcam_bandset_fallback(parent_dir)
                        filts = bs.metadata["BAND"].sort_values()
                        if len(filts) > 0:
                            scenes[f"{parent_dir.name}_{obs_ix:03d}"] = (parent_dir, None, obs_ix)
                        break

                    filts = bs.metadata["BAND"].sort_values()
                    if len(filts) > 0:
                        scenes[f"{parent_dir.name}_{obs_ix:03d}"] = (parent_dir, None, obs_ix)
                        obs_ix += 1
                    else:
                        break
                except Exception:
                    break

        return scenes

    def _load_zcam_thumbnail(self, path, seq_id, obs_ix):
        from rapid.helpers import get_zcam_bandset
        from marslab.imgops.imgutils import crop
        from asdf_settings import rapidlooks

        bs = get_zcam_bandset(path, seq_id=seq_id, observation_ix=obs_ix, load=False)
        if len(bs.metadata) < 3:
            bs = _make_zcam_bandset_fallback(path, seq_id=seq_id)

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
        r = crop(bs.get_band(rgb_bands[0]), crop_settings)
        g = crop(bs.get_band(rgb_bands[1]), crop_settings)
        b = crop(bs.get_band(rgb_bands[2]), crop_settings)

        return self._stretch_rgb(np.stack([r, g, b], axis=-1)), metadata

    # ------------------------------------------------------------------
    # PCAM
    # ------------------------------------------------------------------

    def _find_pcam_scenes(self, folder_path):
        from sparc.utils.pancam_helpers import scan_pcam_files

        folder      = Path(folder_path)
        parent_dirs = {f.parent for f in folder.rglob('*')
                       if f.suffix.upper() in ('.IMG', '.IMQ')}
        scenes      = {}

        for parent_dir in parent_dirs:
            try:
                products = scan_pcam_files(parent_dir)
                for obs_ix, (seq_id, _) in enumerate(products.groupby('SEQ_ID')):
                    scenes[f"{parent_dir.name}_{obs_ix:03d}"] = (parent_dir, seq_id, obs_ix)
            except Exception:
                continue

        return scenes

    def _load_pcam_thumbnail(self, path, seq_id, obs_ix):
        from sparc.utils.pancam_helpers import get_pcam_bandset
        import pdr

        bs = get_pcam_bandset(path, seq_id=seq_id, observation_ix=obs_ix, load=False)

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

        if 'BAND' not in bs.metadata.columns:
            return None, None

        rgb_bands = ['L2', 'L5', 'L6']
        if not all(b in bs.metadata['BAND'].tolist() for b in rgb_bands):
            return None, None

        bs.load(rgb_bands)

        bands = {}
        for _, row in bs.metadata[bs.metadata['BAND'].isin(rgb_bands)].iterrows():
            band   = row['BAND']
            label  = pdr.Data(row['PATH']).metadata
            scale  = label['DERIVED_IMAGE_PARMS']['RADIANCE_SCALING_FACTOR']
            offset = label['DERIVED_IMAGE_PARMS']['RADIANCE_OFFSET']
            dn     = bs.get_band(band).copy().astype(np.float32)
            dn     = np.where((dn == 0) | (dn == 4095), np.nan, dn)
            bands[band] = dn * scale + offset

        rgb = np.stack([np.nan_to_num(bands[b], nan=0.0) for b in rgb_bands], axis=-1)
        return self._stretch_rgb(rgb), metadata

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _stretch_rgb(self, rgb):
        rgb     = np.nan_to_num(rgb, nan=0.0, posinf=0.0, neginf=0.0)
        lo, hi  = (np.percentile(rgb[rgb > 0], [1, 98])
                   if np.any(rgb > 0) else (0, 1))
        rgb     = np.clip((rgb - lo) / (hi - lo) if hi > lo else rgb, 0, 1)
        return (rgb * 255).astype(np.uint8)

    def _numpy_to_pixmap(self, img_array):
        img_array = np.ascontiguousarray(img_array)
        h, w      = img_array.shape[:2]
        q_image   = QImage(img_array.data, w, h, 3 * w, QImage.Format_RGB888)
        return QPixmap.fromImage(q_image.copy())