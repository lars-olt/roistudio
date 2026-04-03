from PyQt5.QtCore import QObject
import yaml
import numpy as np

from .scene_controller import SceneController
from .sparc_controller import SparcController
from utils.converters import numpy_to_pixmap, hex_to_rgb
from sparc.core.constants import get_instrument_config
from sparc.utils.geometry import right_rect_to_left_inscribed
from utils.paths import _get_config_path


class Controller(QObject):
    """Main controller coordinating all application logic."""

    def __init__(self, model, view):
        super().__init__()
        self._model   = model
        self._view    = view
        self._current_scene_id = None

        self._current_rois_data = []
        self._current_colors    = []
        self._is_split_screen   = False

        self.color_palette    = []
        self.color_stack      = []
        self.next_color_index = 0

        self.config_path = _get_config_path()
        self.load_config()
        self._init_color_palette()

        self.scene_controller = SceneController()
        self.sparc_controller = SparcController()

        self._connect_view_signals()
        self._connect_controller_signals()

    def _init_color_palette(self):
        hex_colors = [
            "#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#00FFFF", "#FF00FF",
            "#FFA500", "#800080", "#008000", "#000080", "#800000", "#008080"
        ]
        try:
            from marslab.compat import mertools
            if hasattr(mertools, 'MERSPECT_M20_COLOR_MAPPINGS'):
                hex_colors = list(mertools.MERSPECT_M20_COLOR_MAPPINGS.values())
        except ImportError:
            pass
        self.color_palette = [hex_to_rgb(c) for c in hex_colors]

    def _connect_view_signals(self):
        self._view.set_sam_path_signal.connect(self.set_sam_path)
        self._view.open_folder_signal.connect(self.open_iof_folder)
        self._view.scene_dropped_signal.connect(self.load_scene_by_id)
        self._view.run_algorithm_signal.connect(self.run_algorithm)
        self._view.pixel_hover_callback = self.on_pixel_hover

        self._view.panel_image_editing.roi_changed.connect(self.on_roi_changed)
        self._view.panel_image_editing.roi_deleted.connect(self.on_roi_deleted)
        self._view.panel_image_editing.roi_created.connect(self.on_roi_created)

        self._view.panel_image_editing.split_screen_toggled.connect(self.on_split_screen_toggled)

    def _connect_controller_signals(self):
        self.scene_controller.scan_started.connect(self._view.start_loading)
        self.scene_controller.scan_stopped.connect(self._view.stop_loading)
        self.scene_controller.scene_found.connect(self._on_scene_found)
        self.scene_controller.scan_complete.connect(self._on_scan_complete)
        self.scene_controller.scan_error.connect(self._on_scan_error)

        self.scene_controller.load_started.connect(self._view.start_loading)
        self.scene_controller.load_stopped.connect(self._view.stop_loading)
        self.scene_controller.load_complete.connect(self._on_scene_load_complete)
        self.scene_controller.load_error.connect(self._on_scene_load_error)

        self.sparc_controller.started.connect(self._view.start_loading)
        self.sparc_controller.stopped.connect(self._view.stop_loading)
        self.sparc_controller.status_update.connect(self._view.show_status_message)
        self.sparc_controller.complete.connect(self._on_sparc_complete)
        self.sparc_controller.error.connect(self._on_sparc_error)

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
        sam_path, _ = QFileDialog.getOpenFileName(
            self._view, "Select SAM Model File", "", "Model Files (*.pth);;All Files (*)"
        )
        if sam_path:
            self.config['sam_model_path'] = sam_path
            self.save_config()
            self._view.show_status_message(f"SAM model path set: {sam_path}")

    # ------------------------------------------------------------------
    # Scene scanning / loading
    # ------------------------------------------------------------------

    def open_iof_folder(self):
        folder_path = self.scene_controller.open_folder_dialog(self._view)
        if folder_path:
            self._model.iof_folder_path = folder_path
            self._view.clear_thumbnails()
            self.scene_controller.clear_cache()
            self.scene_controller.start_scan(folder_path)
            self._view.show_status_message("Scanning for IOF files...")

    def _on_scene_found(self, scene_id, pixmap, filename, folder_path, seq_id, obs_ix, instrument):
        self._view.add_scene_thumbnail(scene_id, pixmap, filename)

    def _on_scan_complete(self, total_scenes):
        self._view.stop_loading()
        self._view.show_status_message(f"Scan complete. Found {total_scenes} scene(s).")

    def _on_scan_error(self, error_msg):
        self._view.stop_loading()
        self._view.show_status_message(f"Scan error: {error_msg}")

    def load_scene_by_id(self, scene_id):
        scene_info = self.scene_controller.get_scene_info(scene_id)
        if not scene_info:
            self._view.show_status_message(f"Error: Scene {scene_id} not found in cache")
            return
        self._view.show_status_message(f"Loading scene: {scene_id}")
        self._current_scene_id = self.scene_controller.start_load(scene_id)

    def _on_scene_load_complete(self, load_result):
        self._model.sparc_load_result = load_result
        self._current_rois_data = []
        self._current_colors    = []
        self.color_stack        = []
        self.next_color_index   = 0

        self._view.select_scene(self._current_scene_id)

        if 'rgb_img' not in load_result:
            self._view.stop_loading()
            self._view.show_status_message("Error: No RGB image in load result")
            return

        if 'homography_matrix' in load_result:
            self._view.panel_image_editing.canvas_container.set_homography_matrix(
                load_result['homography_matrix']
            )

        if self._is_split_screen and 'left_rgb_img' in load_result and 'right_rgb_img' in load_result:
            left_pixmap  = numpy_to_pixmap(load_result['left_rgb_img'])
            right_pixmap = numpy_to_pixmap(load_result['right_rgb_img'])
            self._view.panel_image_editing.canvas_container.set_camera_images(left_pixmap, right_pixmap)
        else:
            self._view.panel_image_editing.set_image(numpy_to_pixmap(load_result['rgb_img']))

        self._view.panel_image_editing.set_rois([])
        self._view.panel_spectral_view.clear_roi_spectra()
        self._view.panel_spectral_view.clear_plot()
        self._view.stop_loading()
        self._view.show_status_message(f"Scene loaded: {load_result['id']}")

    def _on_scene_load_error(self, error_msg):
        self._view.stop_loading()
        self._view.show_status_message(f"Error loading scene: {error_msg}")

    # ------------------------------------------------------------------
    # SPARC
    # ------------------------------------------------------------------

    def run_algorithm(self):
        if self._model.sparc_load_result is None:
            self._view.show_status_message("No scene loaded. Please load a scene first.")
            return
        sam_path = self.config.get('sam_model_path', '')
        if not sam_path:
            self._view.show_status_message("SAM model path not set. Use File → Set SAM Path.")
            return
        scene_info = self.scene_controller.get_scene_info(self._current_scene_id)
        if not scene_info:
            self._view.show_status_message("Error: Scene info not found.")
            return

        folder_path, seq_id, obs_ix, instrument = scene_info
        params         = self._view.panel_parameter_selection.get_parameters()
        max_components = params['spectral']['max_components']

        self._view.show_status_message("Starting SPARC pipeline...")
        self.sparc_controller.start_sparc(
            sam_path, folder_path, seq_id, obs_ix, instrument, max_components
        )

    def _get_instrument_config(self):
        load_result = self._model.sparc_load_result
        instrument  = load_result.get('instrument', 'ZCAM') if load_result else 'ZCAM'
        cfg = get_instrument_config(instrument)
        if load_result and hasattr(load_result.get('bandset'), '_sparc_wavelengths'):
            cfg['wavelengths'] = load_result['bandset']._sparc_wavelengths
        return cfg

    def _on_sparc_complete(self, result):
        try:
            if result.final_rois is None or len(result.final_rois) == 0:
                self._view.show_status_message("SPARC found no ROIs")
                self._view.stop_loading()
                return

            instrument_config = get_instrument_config(result.instrument)
            instrument_config['wavelengths'] = result.wavelengths

            self._current_rois_data = self.sparc_controller.extract_roi_data(
                result, instrument_config
            )
            self.color_stack      = []
            self.next_color_index = 0
            self._current_colors  = [self._get_next_color() for _ in self._current_rois_data]

            self._view.panel_image_editing.set_rois(self._current_rois_data, self._current_colors)
            self._view.panel_spectral_view.plot_roi_spectra(self._current_rois_data, self._current_colors)

            self._view.stop_loading()
            self._view.show_status_message(f"SPARC complete: {len(result.final_rois)} ROIs found")

        except Exception as e:
            self._view.stop_loading()
            self._view.show_status_message(f"Error visualizing results: {str(e)}")
            import traceback; traceback.print_exc()

    def _on_sparc_error(self, error_msg):
        self._view.stop_loading()
        self._view.show_status_message(f"Error running SPARC: {error_msg}")
        import traceback; traceback.print_exc()

    # ------------------------------------------------------------------
    # Color management
    # ------------------------------------------------------------------

    def _get_next_color(self):
        if self.color_stack:
            return self.color_stack.pop()
        color = self.color_palette[self.next_color_index % len(self.color_palette)]
        self.next_color_index += 1
        return color

    def _recycle_color(self, color):
        self.color_stack.append(color)

    # ------------------------------------------------------------------
    # ROI editing
    # ------------------------------------------------------------------

    def _has_dual_cubes(self):
        lr = self._model.sparc_load_result
        return lr is not None and 'left_cube' in lr and 'right_cube' in lr and 'merged_band_recipe' in lr

    def on_roi_created(self, rect, camera):
        if self._model.sparc_load_result is None:
            return
        try:
            load_result       = self._model.sparc_load_result
            instrument_config = self._get_instrument_config()
            color             = self._get_next_color()

            if self._has_dual_cubes():
                right_rect = tuple(rect)
                homography = load_result.get('homography_matrix')
                left_rect  = right_rect_to_left_inscribed(right_rect, homography) if homography is not None else right_rect
                if left_rect is None:
                    left_rect = right_rect
                spec_data = self.sparc_controller.update_roi_spectrum_dual(
                    load_result, left_rect, right_rect, instrument_config
                )
            else:
                right_rect = tuple(rect)
                left_rect  = right_rect
                spec_data  = self.sparc_controller.update_roi_spectrum(
                    load_result['cube'], rect, instrument_config
                )

            self._current_rois_data.append({
                'roi':        right_rect,
                'right_rect': right_rect,
                'left_rect':  left_rect,
                'mineral':    'Manual ROI',
                **spec_data,
            })
            self._current_colors.append(color)

            self._view.panel_image_editing.set_rois(self._current_rois_data, self._current_colors)
            self._view.panel_spectral_view.plot_roi_spectra(self._current_rois_data, self._current_colors)
            self._view.show_status_message("ROI created")

        except Exception as e:
            self._view.show_status_message(f"Error creating ROI: {str(e)}")

    def on_roi_deleted(self, roi_index):
        if not (0 <= roi_index < len(self._current_rois_data)):
            return
        try:
            self._recycle_color(self._current_colors.pop(roi_index))
            self._current_rois_data.pop(roi_index)
            self._view.panel_image_editing.set_rois(self._current_rois_data, self._current_colors)
            self._view.panel_spectral_view.plot_roi_spectra(self._current_rois_data, self._current_colors)
            self._view.show_status_message(f"ROI {roi_index + 1} deleted")
        except Exception as e:
            self._view.show_status_message(f"Error deleting ROI: {str(e)}")

    def on_roi_changed(self, roi_index, new_rect, camera):
        if self._model.sparc_load_result is None or roi_index >= len(self._current_rois_data):
            return
        try:
            load_result       = self._model.sparc_load_result
            instrument_config = self._get_instrument_config()
            roi_data          = self._current_rois_data[roi_index]

            if self._has_dual_cubes():
                if camera == 'right':
                    right_rect = tuple(new_rect)
                    left_rect  = roi_data.get('left_rect', roi_data['roi'])
                elif camera == 'left':
                    left_rect  = tuple(new_rect)
                    right_rect = roi_data['right_rect']
                else:  # single — move both together
                    right_rect = tuple(new_rect)
                    left_rect  = self._apply_rect_delta(
                        roi_data.get('left_rect', roi_data['roi']),
                        roi_data['roi'], new_rect
                    )

                spec_data = self.sparc_controller.update_roi_spectrum_dual(
                    load_result, left_rect, right_rect, instrument_config
                )
            else:
                right_rect = tuple(new_rect)
                left_rect  = right_rect
                spec_data  = self.sparc_controller.update_roi_spectrum(
                    load_result['cube'], new_rect, instrument_config
                )

            self._current_rois_data[roi_index] = {
                **roi_data,
                'roi':        right_rect,
                'right_rect': right_rect,
                'left_rect':  left_rect,
                **spec_data,
            }
            self._view.panel_spectral_view.plot_roi_spectra(
                self._current_rois_data, self._current_colors
            )

        except Exception as e:
            self._view.show_status_message(f"Error updating ROI: {str(e)}")

    @staticmethod
    def _apply_rect_delta(left_rect, old_right_rect, new_right_rect):
        """Propagate the translation and scale of a right-rect move onto the left rect."""
        ox, oy, ow, oh = old_right_rect
        nx, ny, nw, nh = new_right_rect
        lx, ly, lw, lh = left_rect
        dx = nx - ox
        dy = ny - oy
        sx = nw / ow if ow > 0 else 1.0
        sy = nh / oh if oh > 0 else 1.0
        return (lx + dx, ly + dy, lw * sx, lh * sy)

    # ------------------------------------------------------------------
    # Hover preview
    # ------------------------------------------------------------------

    def on_pixel_hover(self, x, y):
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
            all_wavelengths   = np.array(instrument_config.get('wavelengths', []))
            instrument        = instrument_config.get('instrument', 'ZCAM')
            n_rgb             = 3 if instrument == 'ZCAM' else 0

            bayer_spectrum = full_spectrum[:n_rgb]
            nb_spectrum    = full_spectrum[n_rgb:]
            bayer_wls      = all_wavelengths[:n_rgb]
            nb_wls         = all_wavelengths[n_rgb:n_rgb + len(nb_spectrum)]

            sort_ix = np.argsort(nb_wls)
            self._view.panel_spectral_view.plot_preview_spectrum_separate(
                nb_wls[sort_ix], nb_spectrum[sort_ix], bayer_wls, bayer_spectrum
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Split screen
    # ------------------------------------------------------------------

    def on_split_screen_toggled(self, is_split):
        self._is_split_screen = is_split
        load_result = self._model.sparc_load_result

        if load_result is not None:
            if is_split and 'left_rgb_img' in load_result and 'right_rgb_img' in load_result:
                left_pixmap  = numpy_to_pixmap(load_result['left_rgb_img'])
                right_pixmap = numpy_to_pixmap(load_result['right_rgb_img'])
                self._view.panel_image_editing.canvas_container.set_camera_images(left_pixmap, right_pixmap)
            elif 'rgb_img' in load_result:
                self._view.panel_image_editing.set_image(numpy_to_pixmap(load_result['rgb_img']))

            if self._current_rois_data:
                self._view.panel_image_editing.set_rois(self._current_rois_data, self._current_colors)

        mode = "split-screen" if is_split else "single"
        self._view.show_status_message(f"Switched to {mode} mode")