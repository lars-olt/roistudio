from PyQt5.QtCore import QObject
import yaml
import numpy as np

from .scene_controller import SceneController
from .sparc_controller import SparcController
from utils.converters import numpy_to_pixmap, hex_to_rgb
from utils.visualizers import visualize_rois_on_image
from sparc.core.constants import get_instrument_config


class Controller(QObject):
    """Main controller coordinating all application logic."""

    def __init__(self, model, view):
        super().__init__()
        self._model = model
        self._view = view
        self._current_scene_id = None

        self._current_rois_data = []
        self._current_colors = []

        self._is_split_screen = False

        self.color_palette = []
        self.color_stack = []
        self.next_color_index = 0

        self.config_path = 'config.yml'
        self.load_config()
        self._init_color_palette()

        self.scene_controller = SceneController()
        self.sparc_controller = SparcController()

        self._connect_view_signals()
        self._connect_controller_signals()

    def _init_color_palette(self):
        """Initializes the color palette."""
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
        """Connects view signals to controller methods."""
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
        """Connects sub-controller signals."""
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

    def load_config(self):
        """Loads configuration from yaml file."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            self.config = {'sam_model_path': ''}
            self.save_config()

    def save_config(self):
        """Saves configuration to yaml file."""
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f)

    def set_sam_path(self):
        """Opens file dialog to set SAM model path."""
        from PyQt5.QtWidgets import QFileDialog

        sam_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Select SAM Model File",
            "",
            "Model Files (*.pth);;All Files (*)"
        )

        if sam_path:
            self.config['sam_model_path'] = sam_path
            self.save_config()
            self._view.show_status_message(f"SAM model path set: {sam_path}")

    def open_iof_folder(self):
        """Opens folder dialog and scans for IOF files."""
        folder_path = self.scene_controller.open_folder_dialog(self._view)

        if folder_path:
            self._model.iof_folder_path = folder_path
            self._view.show_status_message(f"Scanning folder: {folder_path}")

            self._view.clear_thumbnails()
            self.scene_controller.clear_cache()

            self.scene_controller.start_scan(folder_path)
            self._view.show_status_message("Scanning for IOF files...")

    def _on_scene_found(self, scene_id, pixmap, filename, folder_path, seq_id, obs_ix, instrument):
        """Handles scene found event."""
        self._view.add_scene_thumbnail(scene_id, pixmap, filename)

    def _on_scan_complete(self, total_scenes):
        """Handles scan completion."""
        self._view.stop_loading()
        self._view.show_status_message(f"Scan complete. Found {total_scenes} scene(s).")

    def _on_scan_error(self, error_msg):
        """Handles scan error."""
        self._view.stop_loading()
        self._view.show_status_message(f"Scan error: {error_msg}")

    def load_scene_by_id(self, scene_id):
        """Loads a scene by its id."""
        scene_info = self.scene_controller.get_scene_info(scene_id)
        if not scene_info:
            self._view.show_status_message(f"Error: Scene {scene_id} not found in cache")
            return

        self._view.show_status_message(f"Loading scene: {scene_id}")
        self._current_scene_id = self.scene_controller.start_load(scene_id)

    def _on_scene_load_complete(self, load_result):
        """Handles successful scene load."""
        self._model.sparc_load_result = load_result
        self._current_rois_data = []
        self._current_colors = []
        self.color_stack = []
        self.next_color_index = 0

        self._view.select_scene(self._current_scene_id)

        if 'rgb_img' in load_result:
            if 'homography_matrix' in load_result:
                self._view.panel_image_editing.canvas_container.set_homography_matrix(
                    load_result['homography_matrix']
                )

            if self._is_split_screen and 'left_rgb_img' in load_result and 'right_rgb_img' in load_result:
                left_pixmap = numpy_to_pixmap(load_result['left_rgb_img'])
                right_pixmap = numpy_to_pixmap(load_result['right_rgb_img'])
                self._view.panel_image_editing.canvas_container.set_camera_images(left_pixmap, right_pixmap)
            else:
                rgb_img = load_result['rgb_img']
                pixmap = numpy_to_pixmap(rgb_img)
                self._view.panel_image_editing.set_image(pixmap)

            self._view.panel_image_editing.set_rois([])
            self._view.panel_spectral_view.clear_roi_spectra()
            self._view.panel_spectral_view.clear_plot()

            self._view.stop_loading()
            self._view.show_status_message(f"Scene loaded: {load_result['id']}")
        else:
            self._view.stop_loading()
            self._view.show_status_message("Error: No RGB image in load result")

    def _on_scene_load_error(self, error_msg):
        """Handles scene load error."""
        self._view.stop_loading()
        self._view.show_status_message(f"Error loading scene: {error_msg}")

    def run_algorithm(self):
        """Runs the SPARC pipeline."""
        if self._model.sparc_load_result is None:
            self._view.show_status_message("No scene loaded. Please load a scene first.")
            return

        sam_path = self.config.get('sam_model_path')
        if not sam_path:
            self._view.show_status_message("SAM model path not set. Please set it in File menu.")
            return

        self._view.show_status_message("Initializing SPARC algorithm...")

        scene_info = self.scene_controller.get_scene_info(self._current_scene_id)
        folder_path, seq_id, obs_ix, instrument = scene_info

        max_components = self._view.panel_parameter_selection.get_parameters()["spectral"]["max_components"]

        self.sparc_controller.start_sparc(sam_path, folder_path, seq_id, obs_ix, instrument, max_components)

    def _get_instrument_config(self):
        """
        Builds an instrument_config dict from the current load result.
        Falls back to get_instrument_config() defaults if wavelengths
        are not available on the bandset.
        """
        load_result = self._model.sparc_load_result
        instrument  = self._model.instrument

        cfg = get_instrument_config(instrument)

        bandset = load_result.get('bandset') if load_result else None
        if bandset is not None and hasattr(bandset, '_sparc_wavelengths'):
            cfg['wavelengths'] = bandset._sparc_wavelengths

        return cfg

    def _on_sparc_complete(self, result):
        """Handles successful SPARC completion."""
        try:
            if result.final_rois is None or len(result.final_rois) == 0:
                self._view.show_status_message("SPARC found no ROIs")
                self._view.stop_loading()
                return

            num_rois = len(result.final_rois)
            self._view.show_status_message(f"Visualizing {num_rois} ROIs...")

            instrument_config = get_instrument_config(result.instrument)
            instrument_config['wavelengths'] = result.wavelengths

            self._current_rois_data = self.sparc_controller.extract_roi_data(
                result, instrument_config
            )

            self.color_stack = []
            self.next_color_index = 0
            self._current_colors = []

            for _ in self._current_rois_data:
                color = self._get_next_color()
                self._current_colors.append(color)

            self._view.panel_image_editing.set_rois(self._current_rois_data, self._current_colors)
            self._view.panel_spectral_view.plot_roi_spectra(self._current_rois_data, self._current_colors)

            self._view.stop_loading()
            self._view.show_status_message(f"SPARC complete: {num_rois} ROIs found")

        except Exception as e:
            self._view.stop_loading()
            self._view.show_status_message(f"Error visualizing results: {str(e)}")
            import traceback
            traceback.print_exc()

    def _on_sparc_error(self, error_msg):
        """Handles SPARC error."""
        self._view.stop_loading()
        self._view.show_status_message(f"Error running SPARC: {error_msg}")
        import traceback
        traceback.print_exc()

    def _get_next_color(self):
        """Gets next color from stack (recycle) or queue (palette)."""
        if self.color_stack:
            return self.color_stack.pop()

        color = self.color_palette[self.next_color_index % len(self.color_palette)]
        self.next_color_index += 1
        return color

    def _recycle_color(self, color):
        """Pushes a color back onto the stack for recycling."""
        self.color_stack.append(color)

    def on_roi_created(self, rect):
        """Handles creation of a new ROI via Rectangle Tool."""
        if self._model.sparc_load_result is None:
            return

        try:
            cube              = self._model.sparc_load_result['cube']
            instrument_config = self._get_instrument_config()
            color             = self._get_next_color()

            new_roi_data = self.sparc_controller.update_roi_spectrum(
                cube, rect, instrument_config
            )
            new_roi_data['mineral'] = "Manual ROI"

            self._current_rois_data.append(new_roi_data)
            self._current_colors.append(color)

            self._view.panel_image_editing.set_rois(self._current_rois_data, self._current_colors)
            self._view.panel_spectral_view.plot_roi_spectra(self._current_rois_data, self._current_colors)

            self._view.show_status_message("ROI created")

        except Exception as e:
            self._view.show_status_message(f"Error creating ROI: {str(e)}")

    def on_roi_deleted(self, roi_index):
        """Handles deletion of an ROI."""
        if 0 <= roi_index < len(self._current_rois_data):
            try:
                deleted_color = self._current_colors.pop(roi_index)
                self._recycle_color(deleted_color)

                self._current_rois_data.pop(roi_index)

                self._view.panel_image_editing.set_rois(self._current_rois_data, self._current_colors)
                self._view.panel_spectral_view.plot_roi_spectra(self._current_rois_data, self._current_colors)

                self._view.show_status_message(f"ROI {roi_index + 1} deleted")

            except Exception as e:
                self._view.show_status_message(f"Error deleting ROI: {str(e)}")

    def on_roi_changed(self, roi_index, new_rect):
        """Handles interactive ROI changes. Re-calculates spectrum for the modified ROI."""
        if self._model.sparc_load_result is None or 'cube' not in self._model.sparc_load_result:
            return

        try:
            cube              = self._model.sparc_load_result['cube']
            instrument_config = self._get_instrument_config()

            updated_roi_data = self.sparc_controller.update_roi_spectrum(
                cube, new_rect, instrument_config
            )

            old_label = self._current_rois_data[roi_index].get('mineral', f'ROI_{roi_index + 1}')
            updated_roi_data['mineral'] = old_label

            self._current_rois_data[roi_index] = updated_roi_data

            self._view.panel_spectral_view.plot_roi_spectra(self._current_rois_data, self._current_colors)

        except Exception as e:
            self._view.show_status_message(f"Error updating ROI: {str(e)}")

    def on_pixel_hover(self, x, y):
        """Extracts and plots spectrum for hovered pixel."""
        if self._model.sparc_load_result is None:
            return

        try:
            cube = self._model.sparc_load_result.get('cube')
            if cube is None:
                return

            if y >= cube.shape[1] or x >= cube.shape[2]:
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

            bayer_wls = all_wavelengths[:n_rgb]
            nb_wls    = all_wavelengths[n_rgb:n_rgb + len(nb_spectrum)]

            sort_ix        = np.argsort(nb_wls)
            nb_wls_sorted  = nb_wls[sort_ix]
            nb_spec_sorted = nb_spectrum[sort_ix]

            self._view.panel_spectral_view.plot_preview_spectrum_separate(
                nb_wls_sorted,
                nb_spec_sorted,
                bayer_wls,
                bayer_spectrum
            )

        except Exception:
            pass

    def on_split_screen_toggled(self, is_split):
        """Handles split screen mode toggle."""
        self._is_split_screen = is_split

        if self._model.sparc_load_result is not None:
            load_result = self._model.sparc_load_result

            if is_split and 'left_rgb_img' in load_result and 'right_rgb_img' in load_result:
                left_pixmap  = numpy_to_pixmap(load_result['left_rgb_img'])
                right_pixmap = numpy_to_pixmap(load_result['right_rgb_img'])
                self._view.panel_image_editing.canvas_container.set_camera_images(left_pixmap, right_pixmap)

                if self._current_rois_data:
                    self._view.panel_image_editing.set_rois(self._current_rois_data, self._current_colors)
            else:
                if 'rgb_img' in load_result:
                    pixmap = numpy_to_pixmap(load_result['rgb_img'])
                    self._view.panel_image_editing.set_image(pixmap)

                    if self._current_rois_data:
                        self._view.panel_image_editing.set_rois(self._current_rois_data, self._current_colors)

        mode_text = "split-screen" if is_split else "single"
        self._view.show_status_message(f"Switched to {mode_text} mode")