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

        self.color_palette      = []
        self.color_name_palette = []
        self.color_stack        = []
        self.next_color_index   = 0

        self.config_path = _get_config_path()
        self.load_config()
        self._init_color_palette()

        self.scene_controller = SceneController()
        self.sparc_controller = SparcController()

        self._connect_view_signals()
        self._connect_controller_signals()

    def _init_color_palette(self):
        from marslab.compat import mertools
        from sparc.utils.sel_writer import _MASK_DEFAULTS, _normalize_instrument

        all_colors = list(mertools.MERSPECT_M20_COLOR_MAPPINGS.items())
        instrument = self._model.instrument
        first_id   = _MASK_DEFAULTS[_normalize_instrument(instrument)]['first_id']
        offset     = max(0, first_id - 1)
        available  = all_colors[offset:]

        preferred = [
            'red', 'magenta', 'cyan', 'orange', 'azure', 'purple',
            'lime', 'rust', 'green', 'blue', 'yellow', 'magenta 2+', 'magenta -3',
        ]

        name_to_item = {k.lower(): (k, v) for k, v in available}
        ordered      = [name_to_item[n] for n in preferred if n in name_to_item]
        remainder    = [(k, v) for k, v in available if k.lower() not in {n for n in preferred}]
        final        = ordered + remainder

        self.color_palette      = [hex_to_rgb(v) for k, v in final]
        self.color_name_palette = [k             for k, v in final]

    def _connect_view_signals(self):
        self._view.set_sam_path_signal.connect(self.set_sam_path)
        self._view.open_folder_signal.connect(self.open_iof_folder)
        self._view.load_sel_signal.connect(self.load_sel)
        self._view.export_sel_signal.connect(self.export_sel)
        self._view.scene_dropped_signal.connect(self.load_scene_by_id)
        self._view.run_algorithm_signal.connect(self.run_algorithm)
        self._view.scene_double_clicked_signal.connect(self.load_scene_by_id)
        self._view.pixel_hover_callback = self.on_pixel_hover
        self._view.apply_preset_signal.connect(self.apply_preset)

        panel = self._view.panel_image_editing
        panel.roi_changed.connect(self.on_roi_changed)
        panel.roi_deleted.connect(self.on_roi_deleted)
        panel.roi_created.connect(self.on_roi_created)
        panel.split_screen_toggled.connect(self.on_split_screen_toggled)
        panel.rgb_bands_changed.connect(self.on_rgb_bands_changed)

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
    # SEL Import
    # ------------------------------------------------------------------
    
    def load_sel(self):
        if self._model.sparc_load_result is None:
            self._view.show_status_message("No scene loaded - cannot load SEL.")
            return

        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self._view, "Load SEL File", "", "SEL Files (*.sel);;All Files (*)"
        )
        if not path:
            return

        try:
            from sparc.utils.sel_writer import read_sel

            load_result = self._model.sparc_load_result
            instrument  = load_result.get('instrument', 'ZCAM').strip().upper()

            right_rois, left_rois = read_sel(path, instrument)

            if instrument in {'ZCAM', 'MCZ'}:
                from asdf_settings import rapidlooks
                crop    = rapidlooks.CROP_SETTINGS["crop"]
                col_off = int(crop[0])
                row_off = int(crop[2])
            else:
                col_off, row_off = 0, 0

            # shift from full-sensor back to cropped-image coordinates
            if col_off or row_off:
                right_rois = right_rois.copy(); right_rois[:, 0] -= col_off; right_rois[:, 1] -= row_off
                left_rois  = left_rois.copy();  left_rois[:, 0]  -= col_off; left_rois[:, 1]  -= row_off

            instrument_config = self._get_instrument_config()

            self._current_rois_data   = []
            self._current_colors      = []
            self._current_color_names = []
            self.color_stack          = []
            self.next_color_index     = 0

            for right_rect, left_rect in zip(right_rois, left_rois):
                right_rect = tuple(int(v) for v in right_rect)
                left_rect  = tuple(int(v) for v in left_rect)

                if self._has_dual_cubes():
                    spec_data = self.sparc_controller.update_roi_spectrum_dual(
                        load_result, left_rect, right_rect, instrument_config
                    )
                else:
                    spec_data = self.sparc_controller.update_roi_spectrum(
                        load_result['cube'], right_rect, instrument_config
                    )

                color, name = self._get_next_color()
                self._current_colors.append(color)
                self._current_color_names.append(name)
                self._current_rois_data.append({
                    'roi':        right_rect,
                    'right_rect': right_rect,
                    'left_rect':  left_rect,
                    'mineral':    'Loaded ROI',
                    **spec_data,
                })

            self._view.panel_image_editing.set_rois(
                self._current_rois_data, self._current_colors, self._current_color_names
            )
            self._view.panel_spectral_view.plot_roi_spectra(
                self._current_rois_data, self._current_colors
            )
            self._view.action_export_sel.setEnabled(True)
            self._view.show_status_message(
                f"Loaded {len(self._current_rois_data)} ROI(s) from {path}"
            )

        except Exception as e:
            self._view.show_status_message(f"Load SEL failed: {e}")
            import traceback; traceback.print_exc()

    # ------------------------------------------------------------------
    # SEL export
    # ------------------------------------------------------------------

    def export_sel(self):
        if not self._current_rois_data:
            self._view.show_status_message("No ROIs to export.")
            return

        load_result = self._model.sparc_load_result
        if load_result is None:
            self._view.show_status_message("No scene loaded - cannot export SEL.")
            return

        from PyQt5.QtWidgets import QFileDialog
        scene_id = load_result.get('id', 'scene')
        output_path, _ = QFileDialog.getSaveFileName(
            self._view, "Export SEL File",
            f"{scene_id}.sel", "SEL Files (*.sel);;All Files (*)",
        )
        if not output_path:
            return

        try:
            from sparc.utils.sel_writer import export_sel as _write_sel, filenames_from_load_result

            instrument = load_result.get('instrument', 'ZCAM').strip().upper()
            n_rois     = len(self._current_rois_data)

            right_rois = np.array([r['right_rect'] for r in self._current_rois_data], dtype=np.int32)
            left_rois  = np.array([r.get('left_rect', r['right_rect'])
                                   for r in self._current_rois_data], dtype=np.int32)

            if instrument in {'ZCAM', 'MCZ'}:
                from asdf_settings import rapidlooks
                crop     = rapidlooks.CROP_SETTINGS["crop"]
                col_off  = int(crop[0])
                row_off  = int(crop[2])
                raw_band = next(iter(load_result["base_bands"].values()))
                ch, cw   = raw_band.shape
                full_H   = ch + crop[2] + crop[3]
                full_W   = cw + crop[0] + crop[1]
            else:
                col_off, row_off = 0, 0
                full_H, full_W   = load_result['rgb_img'].shape[:2]

            if col_off or row_off:
                right_rois = right_rois.copy()
                right_rois[:, 0] += col_off
                right_rois[:, 1] += row_off
                left_rois = left_rois.copy()
                left_rois[:, 0] += col_off
                left_rois[:, 1] += row_off

            left_names, right_names = filenames_from_load_result(load_result, n_rois)
            _write_sel(
                output_path     = output_path,
                final_rois      = right_rois,
                final_left_rois = left_rois,
                image_shape     = (full_H, full_W),
                left_filenames  = left_names,
                right_filenames = right_names,
                instrument      = instrument,
            )
            self._view.show_status_message(f"Exported {n_rois} ROI(s) to {output_path}")

        except Exception as e:
            self._view.show_status_message(f"Export failed: {e}")
            import traceback; traceback.print_exc()

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
        if not self.scene_controller.get_scene_info(scene_id):
            self._view.show_status_message(f"Error: scene {scene_id} not found in cache")
            return
        self._view.show_status_message(f"Loading scene: {scene_id}")
        self._current_scene_id = self.scene_controller.start_load(scene_id)

    def _on_scene_load_complete(self, load_result):
        self._model.sparc_load_result = load_result
        self._current_rois_data   = []
        self._current_colors      = []
        self._current_color_names = []
        self.color_stack          = []
        self.next_color_index     = 0
        self._view.action_load_sel.setEnabled(True)
        self._view.action_export_sel.setEnabled(False)
        self._view.select_scene(self._current_scene_id)
        self._view.enable_presets(True)

        if 'rgb_img' not in load_result:
            self._view.stop_loading()
            self._view.show_status_message("Error: no RGB image in load result")
            return

        if 'homography_matrix' in load_result:
            self._view.panel_image_editing.canvas_container.set_homography_matrix(
                load_result['homography_matrix']
            )

        base_bands = load_result.get('base_bands', {})
        band_names = list(base_bands.keys())
        if band_names:
            instrument  = load_result.get('instrument', 'ZCAM')
            right_bands = [b for b in band_names if b.startswith('R')] or band_names
            left_bands  = [b for b in band_names if b.startswith('L')] or band_names
            if instrument == 'ZCAM':
                r_r, g_r, b_r = 'R0R', 'R0G', 'R0B'
                r_l, g_l, b_l = 'L0R', 'L0G', 'L0B'
            else:
                r_r, g_r, b_r = 'R2', 'R1', 'R1'
                r_l, g_l, b_l = 'L2', 'L5', 'L6'
            self._view.panel_image_editing.set_band_names(
                right_bands, left_bands,
                r_r, g_r, b_r,
                r_l, g_l, b_l,
            )

        self._render_current_images()
        self._view.panel_image_editing.set_rois([], [], [])
        self._view.panel_spectral_view.clear_roi_spectra()
        self._view.panel_spectral_view.clear_plot()
        self._view.stop_loading()
        self._view.show_status_message(f"Scene loaded: {load_result['id']}")

    def _on_scene_load_error(self, error_msg):
        self._view.stop_loading()
        self._view.show_status_message(f"Error loading scene: {error_msg}")
        self._view.enable_presets(False)

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
            self._view.show_status_message("Error: scene info not found.")
            return

        folder_path, seq_id, obs_ix, instrument = scene_info
        params = self._view.panel_parameter_selection.get_parameters()

        self._view.show_status_message("Starting SPARC pipeline...")
        self.sparc_controller.start_sparc(
            sam_path, folder_path, seq_id, obs_ix, instrument,
            params      = params,
            load_result = self._model.sparc_load_result,
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

            load_result = self._model.sparc_load_result
            if self._has_dual_cubes():
                for i, roi in enumerate(self._current_rois_data):
                    spec_data = self.sparc_controller.update_roi_spectrum_dual(
                        load_result, roi['left_rect'], roi['right_rect'], instrument_config
                    )
                    self._current_rois_data[i] = {**roi, **spec_data}

            self.color_stack      = []
            self.next_color_index = 0
            self._current_colors      = []
            self._current_color_names = []
            for _ in self._current_rois_data:
                color, name = self._get_next_color()
                self._current_colors.append(color)
                self._current_color_names.append(name)

            self._view.panel_image_editing.set_rois(
                self._current_rois_data, self._current_colors, self._current_color_names
            )
            self._view.panel_spectral_view.plot_roi_spectra(
                self._current_rois_data, self._current_colors
            )
            self._view.action_export_sel.setEnabled(True)
            self._view.stop_loading()
            self._view.show_status_message(f"SPARC complete: {len(result.final_rois)} ROIs found")

        except Exception as e:
            self._view.stop_loading()
            self._view.show_status_message(f"Error visualizing results: {e}")
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
            color, name = self.color_stack.pop()
            return color, name
        idx   = self.next_color_index % len(self.color_palette)
        color = self.color_palette[idx]
        name  = self.color_name_palette[idx]
        self.next_color_index += 1
        return color, name

    def _recycle_color(self, color, name):
        self.color_stack.append((color, name))

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
            color, name       = self._get_next_color()

            if self._has_dual_cubes():
                homography = load_result.get('homography_matrix')
                if camera == 'left':
                    left_rect  = tuple(rect)
                    right_rect = self._left_rect_to_right(left_rect, homography) or left_rect
                else:
                    right_rect = tuple(rect)
                    left_rect  = (right_rect_to_left_inscribed(right_rect, homography)
                                if homography is not None else right_rect) or right_rect
                spec_data = self.sparc_controller.update_roi_spectrum_dual(
                    load_result, left_rect, right_rect, instrument_config
                )
            else:
                right_rect = left_rect = tuple(rect)
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
            self._current_color_names.append(name)
            self._view.panel_image_editing.set_rois(
                self._current_rois_data, self._current_colors, self._current_color_names
            )
            self._view.panel_spectral_view.plot_roi_spectra(
                self._current_rois_data, self._current_colors
            )
            self._view.action_export_sel.setEnabled(True)
            self._view.show_status_message("ROI created")

        except Exception as e:
            self._view.show_status_message(f"Error creating ROI: {e}")

    def on_roi_deleted(self, roi_index):
        if not (0 <= roi_index < len(self._current_rois_data)):
            return
        try:
            color = self._current_colors.pop(roi_index)
            name  = self._current_color_names.pop(roi_index)
            self._recycle_color(color, name)
            self._current_rois_data.pop(roi_index)
            self._view.panel_image_editing.set_rois(
                self._current_rois_data, self._current_colors, self._current_color_names
            )
            self._view.panel_spectral_view.plot_roi_spectra(
                self._current_rois_data, self._current_colors
            )
            self._view.action_export_sel.setEnabled(bool(self._current_rois_data))
            self._view.show_status_message(f"ROI {roi_index + 1} deleted")
        except Exception as e:
            self._view.show_status_message(f"Error deleting ROI: {e}")

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
                else:
                    right_rect = tuple(new_rect)
                    left_rect  = self._apply_rect_delta(
                        roi_data.get('left_rect', roi_data['roi']),
                        roi_data['roi'], new_rect
                    )
                spec_data = self.sparc_controller.update_roi_spectrum_dual(
                    load_result, left_rect, right_rect, instrument_config
                )
            else:
                right_rect = left_rect = tuple(new_rect)
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
            self._view.show_status_message(f"Error updating ROI: {e}")

    @staticmethod
    def _left_rect_to_right(left_rect, homography_matrix):
        if homography_matrix is None:
            return left_rect
        import cv2
        x, y, w, h = left_rect
        corners = np.array([[x, y], [x+w, y], [x+w, y+h], [x, y+h]], dtype=np.float32)
        rc = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), homography_matrix).reshape(-1, 2)
        rx, ry = float(rc[:, 0].min()), float(rc[:, 1].min())
        return (rx, ry, float(rc[:, 0].max()) - rx, float(rc[:, 1].max()) - ry)

    @staticmethod
    def _apply_rect_delta(left_rect, old_right_rect, new_right_rect):
        ox, oy, ow, oh = old_right_rect
        nx, ny, nw, nh = new_right_rect
        lx, ly, lw, lh = left_rect
        return (lx + nx - ox, ly + ny - oy,
                lw * (nw / ow if ow > 0 else 1.0),
                lh * (nh / oh if oh > 0 else 1.0))

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
            all_wls    = np.array(instrument_config.get('wavelengths', []))
            instrument = instrument_config.get('instrument', 'ZCAM')
            n_rgb      = 3 if instrument == 'ZCAM' else 0

            nb_spectrum    = full_spectrum[n_rgb:]
            nb_wls         = all_wls[n_rgb:n_rgb + len(nb_spectrum)]
            bayer_spectrum = full_spectrum[:n_rgb]
            bayer_wls      = all_wls[:n_rgb]

            sort_ix = np.argsort(nb_wls)
            self._view.panel_spectral_view.plot_preview_spectrum_separate(
                nb_wls[sort_ix], nb_spectrum[sort_ix], bayer_wls, bayer_spectrum
            )
        except Exception:
            pass
    
    # ------------------------------------------------------------------
    # Stretch presets
    # ------------------------------------------------------------------
    
    def apply_preset(self, preset: dict):
        load_result = self._model.sparc_load_result
        if load_result is None:
            return
        camera = preset['camera']
        # In single mode, right-camera presets target the single canvas
        if not self._is_split_screen and camera == 'right':
            camera = 'single'
        self._view.panel_image_editing.apply_preset(
            camera, preset['r'], preset['g'], preset['b'], preset['dcs']
        )

    # ------------------------------------------------------------------
    # Split screen
    # ------------------------------------------------------------------

    def on_split_screen_toggled(self, is_split):
        self._is_split_screen = is_split
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
    # RGB band rendering
    # ------------------------------------------------------------------

    @staticmethod
    def _bands_to_pixmap(r_arr, g_arr, b_arr, use_dcs=False):
        """
        Stretch three band arrays to uint8 RGB.
        DCS off: enhance_color (same as the default pipeline image).
        DCS on:  decorrelation stretch (Gillespie et al. 1986) with
                 per-channel 0.5–99.5 percentile clip.
        """
        if use_dcs:
            H, W    = r_arr.shape
            invalid = ~np.isfinite(r_arr) | ~np.isfinite(g_arr) | ~np.isfinite(b_arr)
            r = np.where(invalid, 0.0, r_arr).astype(np.float32)
            g = np.where(invalid, 0.0, g_arr).astype(np.float32)
            b = np.where(invalid, 0.0, b_arr).astype(np.float32)

            vecs  = np.stack([r, g, b], axis=-1).reshape(-1, 3)
            valid = vecs[~invalid.ravel()]
            if valid.shape[0] < 4:
                return numpy_to_pixmap(np.zeros((H, W, 3), dtype=np.uint8))

            cov          = np.cov(valid.T).astype(np.float32)
            eigvals, V   = np.linalg.eig(cov)
            T            = (V @ np.diag(1.0 / np.sqrt(np.abs(eigvals))) @ V.T).astype(np.float32)
            means        = valid.mean(axis=0)
            dcs          = ((vecs - means) @ T + means + (means - means @ T)).reshape(H, W, 3)

            result       = np.zeros((H, W, 3), dtype=np.float32)
            valid_2d     = ~invalid
            for c in range(3):
                ch       = dcs[:, :, c]
                v        = ch[valid_2d]
                if v.size == 0:
                    continue
                lo, hi   = np.percentile(v, [0.5, 99.5])
                result[:, :, c] = np.clip((ch - lo) / (hi - lo) if hi > lo else ch, 0.0, 1.0)
            result[invalid] = 0.0
            return numpy_to_pixmap(np.ascontiguousarray(result * 255, dtype=np.uint8))
        else:
            from marslab.imgops.imgutils import enhance_color
            rgb    = np.stack([r_arr, g_arr, b_arr], axis=-1).astype(float)
            result = enhance_color(np.ma.masked_invalid(rgb), bounds=(0, 1), stretch=0.1)
            return numpy_to_pixmap(
                np.ascontiguousarray(np.ma.filled(result, 0) * 255, dtype=np.uint8)
            )

    def _make_pixmap(self, r_band, g_band, b_band, base_bands, use_dcs=False):
        if not all(b in base_bands for b in (r_band, g_band, b_band)):
            return None
        return self._bands_to_pixmap(
            base_bands[r_band], base_bands[g_band], base_bands[b_band], use_dcs
        )

    def _render_current_images(self):
        """
        Canonical image render - reads current overlay selections and pushes
        pixmaps to the canvas. Called on scene load, band change, and split toggle.
        """
        load_result = self._model.sparc_load_result
        if load_result is None:
            return

        base_bands = load_result.get('base_bands', {})
        panel      = self._view.panel_image_editing

        if self._is_split_screen:
            r_r, g_r, b_r, dcs_r = panel.get_selected_bands('right')
            r_l, g_l, b_l, dcs_l = panel.get_selected_bands('left')

            right_pixmap = (self._make_pixmap(r_r, g_r, b_r, base_bands, dcs_r)
                            if r_r and g_r and b_r else None)
            left_pixmap  = (self._make_pixmap(r_l, g_l, b_l, base_bands, dcs_l)
                            if r_l and g_l and b_l else None)

            right_pixmap = right_pixmap or numpy_to_pixmap(
                load_result.get('right_rgb_img', load_result['rgb_img'])
            )
            left_pixmap  = left_pixmap  or numpy_to_pixmap(
                load_result.get('left_rgb_img', load_result['rgb_img'])
            )
            panel.canvas_container.set_camera_images(left_pixmap, right_pixmap)
        else:
            r, g, b, dcs = panel.get_selected_bands('single')
            if r and g and b:
                pixmap = self._make_pixmap(r, g, b, base_bands, dcs)
                if pixmap:
                    panel.set_image(pixmap)
            else:
                panel.set_image(numpy_to_pixmap(load_result['rgb_img']))

    def on_rgb_bands_changed(self, r, g, b, use_dcs, camera):
        self._render_current_images()