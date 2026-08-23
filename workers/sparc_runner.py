import traceback

from PyQt5.QtCore import QThread, pyqtSignal

from sparc.core.functional import run_sparc, run_sparc_from_load_result
from sparc.core.config import (
    SparcConfig, LoadConfig, SegmentConfig,
    ROIConfig, SpectralConfig,
    SegmentationBackend, ROIBackend,
)
from sparc.utils.memory import release_cuda_memory


class SparcRunThread(QThread):
    """Runs the SPARC pipeline in a background thread."""

    status_update  = pyqtSignal(str)
    sparc_complete = pyqtSignal(object)
    sparc_error    = pyqtSignal(str)

    def __init__(self, sam_path, folder_path, seq_id, obs_ix, instrument,
                 params=None, load_result=None, presegmented=None):
        super().__init__()
        self.sam_path      = sam_path
        self.folder_path   = folder_path
        self.seq_id        = seq_id
        self.obs_ix        = obs_ix
        self.instrument    = instrument
        self.params        = params or {}
        self.load_result   = load_result
        self.presegmented  = presegmented

    def run(self):
        result = None
        error_message = None
        try:
            seg  = self.params.get('segment', {})
            roi  = self.params.get('roi', {})
            spec = self.params.get('spectral', {})

            config = SparcConfig(
                load=LoadConfig(
                    iof_path         = self.folder_path,
                    instrument       = self.instrument,
                    seq_id           = self.seq_id,
                    obs_ix           = self.obs_ix,
                    do_apply_pixmaps = True,
                    ignore_bayers    = False,
                ),
                segment=SegmentConfig(
                    sam_model_path      = self.sam_path,
                    backend             = SegmentationBackend.GPU,
                    preserve_background = seg.get('preserve_background', False),
                    points_per_side     = seg.get('points_per_side', 32),
                    pred_iou_thresh     = seg.get('pred_iou_thresh', 0.88),
                ),
                roi=ROIConfig(
                    backend                 = ROIBackend.THREADED,
                    edge_offset             = roi.get('edge_offset', 10),
                    allowed_variance        = roi.get('allowed_variance', 1.0),
                    area_threshold          = roi.get('area_threshold', 50),
                    albedo_ratio_threshold  = roi.get('albedo_ratio_threshold', 0.80),
                    min_cluster_area        = roi.get('min_cluster_area', 500),
                    min_clean_area          = roi.get('min_clean_area', 4000),
                    morph_opening_threshold = roi.get('morph_opening_threshold', 1000),
                    max_subclusters         = roi.get('max_subclusters', 10),
                ),
                spectral=SpectralConfig(
                    max_components = spec.get('max_components', 9),
                ),
            )

            self.status_update.emit("Running SPARC pipeline...")

            if self.load_result is not None:
                result = run_sparc_from_load_result(
                    self.load_result, config,
                    presegmented=self.presegmented,
                )
            else:
                self.status_update.emit("Loading scene...")
                result = run_sparc(
                    iof_path       = self.folder_path,
                    sam_model_path = self.sam_path,
                    config         = config,
                )

        except Exception as e:
            error_message = f"{e}\n\n{traceback.format_exc()}"
        finally:
            # A finished worker must not keep a previous scene alive.
            self.load_result = None
            self.presegmented = None

        # Run after the except block so traceback frames no longer retain SAM
        # tensors. This also releases PyTorch's unused caching-allocator blocks.
        release_cuda_memory()

        if error_message is not None:
            self.sparc_error.emit(error_message)
        else:
            self.sparc_complete.emit(result)
