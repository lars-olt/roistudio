from PyQt5.QtCore import QThread, pyqtSignal
from sparc.core.functional import run_sparc
from sparc.core.config import (
    SparcConfig, LoadConfig, SegmentConfig, SpectralConfig,
    SegmentationBackend, ROIBackend
)


class SparcRunThread(QThread):
    """Background thread for running SPARC pipeline."""

    status_update = pyqtSignal(str)
    sparc_complete = pyqtSignal(object)
    sparc_error = pyqtSignal(str)

    def __init__(self, sam_path, folder_path, seq_id, obs_ix, instrument,
                 max_components=9):
        super().__init__()
        self.sam_path       = sam_path
        self.folder_path    = folder_path
        self.seq_id         = seq_id
        self.obs_ix         = obs_ix
        self.instrument     = instrument
        self.max_components = max_components

    def run(self):
        """Executes SPARC pipeline."""
        try:
            self.status_update.emit("Loading scene...")

            config = SparcConfig(
                load=LoadConfig(
                    iof_path=self.folder_path,
                    instrument=self.instrument,
                    seq_id=self.seq_id,
                    obs_ix=self.obs_ix,
                    do_apply_pixmaps=True,
                    ignore_bayers=False,
                ),
                segment=SegmentConfig(
                    sam_model_path=self.sam_path,
                    backend=SegmentationBackend.GPU,
                ),
                spectral=SpectralConfig(
                    max_components=self.max_components,
                ),
            )
            config.roi.backend = ROIBackend.THREADED

            self.status_update.emit("Running SPARC pipeline...")
            result = run_sparc(
                iof_path=self.folder_path,
                sam_model_path=self.sam_path,
                config=config,
            )

            self.sparc_complete.emit(result)

        except Exception as e:
            self.sparc_error.emit(str(e))