from pathlib import Path
import inspect

from PyQt5.QtCore import QThread, pyqtSignal
from sparc.data.loading import load_cube
from sparc.core.config import AlignmentConfig
from utils.scene_camera import display_camera


class SceneLoadThread(QThread):
    """Background thread for loading full scene data."""

    load_complete = pyqtSignal(object)
    load_error    = pyqtSignal(str)

    def __init__(self, folder_path, seq_id, obs_ix, instrument, alignment_method='homography', device='auto'):
        super().__init__()
        self.folder_path = str(Path(folder_path).expanduser().absolute())
        self.seq_id      = seq_id
        self.obs_ix      = obs_ix
        self.instrument  = instrument
        self.alignment_method = alignment_method
        self.device = device

    def run(self):
        try:
            load_options = dict(
                iof_path         = self.folder_path,
                instrument       = self.instrument,
                seq_id           = self.seq_id,
                obs_ix           = self.obs_ix,
                do_apply_pixmaps = True,
                ignore_bayers    = False,
                crop_zcam        = False,
                alignment        = AlignmentConfig(method=self.alignment_method, device=self.device),
            )
            # Older editable SPARC checkouts always return cropped ZCAM data.
            # Record that origin so ROIStudio does not crop the margins twice.
            parameters = inspect.signature(load_cube).parameters
            legacy_crop = ('crop_zcam' not in parameters and not any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()
            ))
            if legacy_crop:
                load_options.pop('crop_zcam')
            load_result = load_cube(**load_options)
            if legacy_crop and self.instrument == 'ZCAM':
                from sparc.data.loading import ZCAM_CROP
                load_result['sensor_crop'] = tuple(ZCAM_CROP)
            load_result.setdefault('alignment_method', 'homography')
            load_result['compute_device'] = self.device
            # Keep the loaded scene's location, independent of later scans or saves.
            load_result['source_folder'] = self.folder_path
            load_result['rgb_img'] = load_result.get(
                f'{display_camera(load_result)}_rgb_img', load_result['rgb_img'],
            )
            self.load_complete.emit(load_result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.load_error.emit(str(e))
