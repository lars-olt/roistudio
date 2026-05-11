"""Main application controller - wires signals and delegates to focused handlers."""

import numpy as np
from PyQt5.QtCore import QObject
import yaml

from .scene_controller import SceneController
from .sparc_controller import SparcController
from .color_manager import ColorManager
from . import scene_callbacks, sparc_callbacks, roi_controller, sel_controller
from utils.rendering import render_images
from utils.paths import _get_config_path


class Controller(QObject):
    """Coordinates all application logic between model and view."""

    def __init__(self, model, view):
        super().__init__()
        self._model             = model
        self._view              = view
        self._current_scene_id  = None
        self._current_rois_data = []
        self._current_colors    = []
        self._current_color_names = []
        self._is_split_screen   = False

        self.config_path = _get_config_path()
        self.load_config()

        self.color_manager     = ColorManager(self._model.instrument)
        self.scene_controller  = SceneController()
        self.sparc_controller  = SparcController()

        self._connect_view_signals()
        self._connect_controller_signals()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            self.config = {'sam_model_path': ''}
            self.save_config()

    def save_config(self):
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f)

    def set_sam_path(self):
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self._view, "Select SAM Model File", "", "Model Files (*.pth);;All Files (*)"
        )
        if path:
            self.config['sam_model_path'] = path
            self.save_config()
            self._view.show_status_message(f"SAM model path set: {path}")

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_view_signals(self):
        self._view.set_sam_path_signal.connect(self.set_sam_path)
        self._view.open_folder_signal.connect(self._open_iof_folder)
        self._view.export_sel_signal.connect(self._export_sel)
        self._view.load_sel_signal.connect(self._load_sel)
        self._view.scene_dropped_signal.connect(self._load_scene_by_id)
        self._view.run_algorithm_signal.connect(self._run_algorithm)
        self._view.scene_double_clicked_signal.connect(self._load_scene_by_id)
        self._view.pixel_hover_callback = self._on_pixel_hover
        self._view.apply_preset_signal.connect(self._apply_preset)

        panel = self._view.panel_image_editing
        panel.roi_changed.connect(self._on_roi_changed)
        panel.roi_deleted.connect(self._on_roi_deleted)
        panel.roi_created.connect(self._on_roi_created)
        panel.split_screen_toggled.connect(self._on_split_screen_toggled)
        panel.rgb_bands_changed.connect(self._on_rgb_bands_changed)

    def _connect_controller_signals(self):
        sc = self.scene_controller
        sc.scan_started.connect(self._view.start_loading)
        sc.scan_stopped.connect(self._view.stop_loading)
        sc.scene_found.connect(self._on_scene_found)
        sc.scan_complete.connect(self._on_scan_complete)
        sc.scan_error.connect(self._on_scan_error)
        sc.load_started.connect(self._view.start_loading)
        sc.load_stopped.connect(self._view.stop_loading)
        sc.load_complete.connect(self._on_scene_load_complete)
        sc.load_error.connect(self._on_scene_load_error)

        sp = self.sparc_controller
        sp.started.connect(self._view.start_loading)
        sp.stopped.connect(self._view.stop_loading)
        sp.status_update.connect(self._view.show_status_message)
        sp.complete.connect(self._on_sparc_complete)
        sp.error.connect(self._on_sparc_error)

    # ------------------------------------------------------------------
    # Scene scanning / loading
    # ------------------------------------------------------------------

    def _open_iof_folder(self):
        folder_path = self.scene_controller.open_folder_dialog(self._view)
        if folder_path:
            self._model.iof_folder_path = folder_path
            self._view.clear_thumbnails()
            self.scene_controller.clear_cache()
            self.scene_controller.start_scan(folder_path)
            self._view.show_status_message("Scanning for IOF files...")

    def _load_scene_by_id(self, scene_id):
        if not self.scene_controller.get_scene_info(scene_id):
            self._view.show_status_message(f"Error: scene {scene_id} not found in cache")
            return
        self._view.show_status_message(f"Loading scene: {scene_id}")
        self._current_scene_id  = self.scene_controller.start_load(scene_id)
        self._current_rois_data = []
        self._current_colors    = []
        self._current_color_names = []
        self.color_manager.reset()

    def _on_scene_found(self, scene_id, pixmap, filename, folder_path, seq_id, obs_ix, instrument):
        scene_callbacks.on_scene_found(scene_id, pixmap, filename, self._view)

    def _on_scan_complete(self, total_scenes):
        scene_callbacks.on_scan_complete(total_scenes, self._view)

    def _on_scan_error(self, error_msg):
        scene_callbacks.on_scan_error(error_msg, self._view)

    def _on_scene_load_complete(self, load_result):
        scene_callbacks.on_scene_load_complete(
            load_result, self._current_scene_id, self._model, self._view
        )
        self._render_current_images()

    def _on_scene_load_error(self, error_msg):
        scene_callbacks.on_scene_load_error(error_msg, self._view)

    # ------------------------------------------------------------------
    # SPARC
    # ------------------------------------------------------------------

    def _run_algorithm(self):
        sparc_callbacks.run_algorithm(
            self._model, self._view,
            self.scene_controller, self.sparc_controller,
            self._current_scene_id,
            self.config.get('sam_model_path', ''),
            self._view.panel_parameter_selection.get_parameters(),
        )

    def _on_sparc_complete(self, result):
        try:
            outcome = sparc_callbacks.on_sparc_complete(
                result, self._model, self._view,
                self.sparc_controller, self.color_manager,
            )
            if outcome is not None:
                self._current_rois_data, self._current_colors, self._current_color_names = outcome
        except Exception as e:
            self._view.stop_loading()
            self._view.show_status_message(f"Error visualizing results: {e}")
            import traceback; traceback.print_exc()

    def _on_sparc_error(self, error_msg):
        sparc_callbacks.on_sparc_error(error_msg, self._view)

    # ------------------------------------------------------------------
    # ROI editing
    # ------------------------------------------------------------------

    def _has_dual_cubes(self):
        lr = self._model.sparc_load_result
        return (lr is not None
                and 'left_cube' in lr
                and 'right_cube' in lr
                and 'merged_band_recipe' in lr)

    def _on_roi_created(self, rect, camera):
        if self._model.sparc_load_result is None:
            return
        try:
            roi_data    = roi_controller.on_roi_created(
                rect, camera,
                self._model.sparc_load_result,
                self._get_instrument_config(),
                self.sparc_controller,
                self._has_dual_cubes(),
            )
            color, name = self.color_manager.next()
            self._current_rois_data.append(roi_data)
            self._current_colors.append(color)
            self._current_color_names.append(name)
            self._update_roi_view()
            self._view.action_export_sel.setEnabled(True)
            self._view.show_status_message("ROI created")
        except Exception as e:
            self._view.show_status_message(f"Error creating ROI: {e}")

    def _on_roi_deleted(self, roi_index):
        if not (0 <= roi_index < len(self._current_rois_data)):
            return
        try:
            color = self._current_colors.pop(roi_index)
            name  = self._current_color_names.pop(roi_index)
            self.color_manager.recycle(color, name)
            self._current_rois_data.pop(roi_index)
            self._update_roi_view()
            self._view.action_export_sel.setEnabled(bool(self._current_rois_data))
            self._view.show_status_message(f"ROI {roi_index + 1} deleted")
        except Exception as e:
            self._view.show_status_message(f"Error deleting ROI: {e}")

    def _on_roi_changed(self, roi_index, new_rect, camera):
        if self._model.sparc_load_result is None or roi_index >= len(self._current_rois_data):
            return
        try:
            self._current_rois_data[roi_index] = roi_controller.on_roi_changed(
                roi_index, new_rect, camera,
                self._current_rois_data,
                self._model.sparc_load_result,
                self._get_instrument_config(),
                self.sparc_controller,
                self._has_dual_cubes(),
            )
            self._view.panel_spectral_view.plot_roi_spectra(
                self._current_rois_data, self._current_colors
            )
        except Exception as e:
            self._view.show_status_message(f"Error updating ROI: {e}")

    def _update_roi_view(self):
        self._view.panel_image_editing.set_rois(
            self._current_rois_data, self._current_colors, self._current_color_names
        )
        self._view.panel_spectral_view.plot_roi_spectra(
            self._current_rois_data, self._current_colors
        )

    # ------------------------------------------------------------------
    # SEL export / import
    # ------------------------------------------------------------------

    def _export_sel(self):
        sel_controller.export_sel(
            self._view, self._model,
            self._current_rois_data,
            self._current_color_names,
            self.color_manager,
        )

    def _load_sel(self):
        outcome = sel_controller.load_sel(
            self._view, self._model,
            self._get_instrument_config(),
            self.sparc_controller,
            self._has_dual_cubes(),
            self.color_manager,
        )
        if outcome is None:
            return

        self._current_rois_data, self._current_colors, self._current_color_names = outcome
        self._update_roi_view()
        self._view.action_export_sel.setEnabled(True)

    # ------------------------------------------------------------------
    # Hover preview
    # ------------------------------------------------------------------

    def _on_pixel_hover(self, x, y):
        if self._model.sparc_load_result is None:
            return
        try:
            cube = self._model.sparc_load_result.get('cube')
            if cube is None or y >= cube.shape[1] or x >= cube.shape[2]:
                return

            full_spectrum = cube[:, y, x]
            if np.ma.is_masked(full_spectrum):
                if full_spectrum.mask.all():
                    return
                full_spectrum = np.ma.filled(full_spectrum, np.nan)
            if not np.isfinite(full_spectrum).any():
                return

            instrument_config = self._get_instrument_config()
            all_wls    = np.array(instrument_config.get('wavelengths', []))
            instrument = instrument_config.get('instrument', 'ZCAM')
            n_rgb      = 3 if instrument == 'ZCAM' else 0

            nb_spectrum = full_spectrum[n_rgb:]
            nb_wls      = all_wls[n_rgb:n_rgb + len(nb_spectrum)]
            bayer_wls   = all_wls[:n_rgb]

            sort_ix = np.argsort(nb_wls)
            self._view.panel_spectral_view.plot_preview_spectrum_separate(
                nb_wls[sort_ix], nb_spectrum[sort_ix], bayer_wls, full_spectrum[:n_rgb]
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_current_images(self):
        if self._model.sparc_load_result is None:
            return
        render_images(
            self._model.sparc_load_result,
            self._view.panel_image_editing,
            self._is_split_screen,
        )

    def _on_rgb_bands_changed(self, r, g, b, use_dcs, camera):
        self._render_current_images()

    # ------------------------------------------------------------------
    # Presets and split screen
    # ------------------------------------------------------------------

    def _apply_preset(self, preset: dict):
        if self._model.sparc_load_result is None:
            return
        camera = preset['camera']
        if not self._is_split_screen and camera == 'right':
            camera = 'single'
        self._view.panel_image_editing.apply_preset(
            camera, preset['r'], preset['g'], preset['b'], preset['dcs']
        )

    def _on_split_screen_toggled(self, is_split):
        self._is_split_screen = is_split

        if not is_split and self._current_rois_data:
            homography = (self._model.sparc_load_result or {}).get('homography_matrix')
            roi_controller.sync_left_rois(self._current_rois_data, homography)

        if self._model.sparc_load_result is not None:
            self._render_current_images()
            if self._current_rois_data:
                self._view.panel_image_editing.set_rois(
                    self._current_rois_data, self._current_colors, self._current_color_names
                )
        self._view.show_status_message(
            f"Switched to {'split-screen' if is_split else 'single'} mode"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_instrument_config(self):
        load_result = self._model.sparc_load_result
        return sparc_callbacks.get_instrument_config_for_scene(load_result)