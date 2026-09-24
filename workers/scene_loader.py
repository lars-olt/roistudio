from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal
from sparc.data.loading import load_cube


class SceneLoadThread(QThread):
    """Background thread for loading full scene data."""

    load_complete = pyqtSignal(object)
    load_error    = pyqtSignal(str)

    def __init__(self, folder_path, seq_id, obs_ix, instrument):
        super().__init__()
        self.folder_path = str(Path(folder_path).expanduser().absolute())
        self.seq_id      = seq_id
        self.obs_ix      = obs_ix
        self.instrument  = instrument

    def run(self):
        try:
            load_result = load_cube(
                iof_path         = self.folder_path,
                instrument       = self.instrument,
                seq_id           = self.seq_id,
                obs_ix           = self.obs_ix,
                do_apply_pixmaps = True,
                ignore_bayers    = False,
                crop_zcam        = False,
            )
            # Keep the loaded scene's location, independent of later scans or saves.
            load_result['source_folder'] = self.folder_path
            self.load_complete.emit(load_result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.load_error.emit(str(e))
