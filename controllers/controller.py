from PyQt5.QtCore import QObject
import yaml
import numpy as np
from sparc.core.constants import WAVELENGTHS

from .scene_controller import SceneController
from .sparc_controller import SparcController
from utils.converters import numpy_to_pixmap, hex_to_rgb
from utils.visualizers import visualize_rois_on_image


class Controller(QObject):
    """Main controller coordinating all application logic."""
    
    def __init__(self, model, view):
        super().__init__()
        self._model = model
        self._view = view
        self._current_scene_id = None
        
        self.config_path = 'config.yml'
        self.load_config()
        
        self.scene_controller = SceneController()
        self.sparc_controller = SparcController()
        
        self._connect_view_signals()
        self._connect_controller_signals()
    
    def _connect_view_signals(self):
        """Connects view signals to controller methods."""
        self._view.set_sam_path_signal.connect(self.set_sam_path)
        self._view.open_folder_signal.connect(self.open_iof_folder)
        self._view.scene_dropped_signal.connect(self.load_scene_by_id)
        self._view.run_algorithm_signal.connect(self.run_algorithm)
        self._view.pixel_hover_callback = self.on_pixel_hover
    
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
    
    def _on_scene_found(self, scene_id, pixmap, filename, folder_path, seq_id, obs_ix):
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
        
        self._view.select_scene(self._current_scene_id)
        
        if 'rgb_img' in load_result:
            rgb_img = load_result['rgb_img']
            pixmap = numpy_to_pixmap(rgb_img)
            self._view.panel_image_editing.set_image(pixmap)
            
            self._view.stop_loading()
            self._view.show_status_message(f"Scene loaded: {load_result['id']}")
        else:
            self._view.stop_loading()
            self._view.show_status_message("Error: No RGB image in load result")
    
    def _on_scene_load_error(self, error_msg):
        """Handles scene load error."""
        self._view.stop_loading()
        self._view.show_status_message(f"Error loading scene: {error_msg}")
    
    def run_algorithm(self, algorithm_name):
        """Runs the selected SPARC algorithm."""
        if algorithm_name != "full algorithm":
            self._view.show_status_message(f"Algorithm '{algorithm_name}' not yet implemented")
            return
        
        if self._model.sparc_load_result is None:
            self._view.show_status_message("No scene loaded. Please load a scene first.")
            return
        
        sam_path = self.config.get('sam_model_path')
        if not sam_path:
            self._view.show_status_message("SAM model path not set. Please set it in File menu.")
            return
        
        self._view.show_status_message("Initializing SPARC algorithm...")
        
        scene_info = self.scene_controller.get_scene_info(self._current_scene_id)
        folder_path, seq_id, obs_ix = scene_info
        
        self.sparc_controller.start_sparc(sam_path, folder_path, seq_id, obs_ix)
    
    def _on_sparc_complete(self, result):
        """Handles successful SPARC completion."""
        try:
            from marslab.compat import mertools
            
            if result.final_rois is None or len(result.final_rois) == 0:
                self._view.show_status_message("SPARC found no ROIs")
                self._view.stop_loading()
                return
            
            num_rois = len(result.final_rois)
            
            self._view.show_status_message(f"Visualizing {num_rois} ROIs...")
            
            hex_colors = list(mertools.MERSPECT_M20_COLOR_MAPPINGS.values())
            color_list = [hex_to_rgb(c) for c in hex_colors]
            
            rois_with_spectra = self.sparc_controller.extract_roi_data(result)
            
            rgb_pixmap = self._view.panel_image_editing.canvas_container.canvas.image
            if rgb_pixmap:
                updated_pixmap = visualize_rois_on_image(rgb_pixmap, rois_with_spectra, color_list)
                self._view.panel_image_editing.set_image(updated_pixmap)
            
            self._view.panel_spectral_view.plot_roi_spectra(rois_with_spectra, color_list)
            
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
            
            bayer_spectrum = full_spectrum[:3]
            non_bayer_spectrum = full_spectrum[3:]
            
            bayer_wls = WAVELENGTHS[:3]
            non_bayer_wls = np.array(WAVELENGTHS[3:])
            
            sort_indices = np.argsort(non_bayer_wls)
            non_bayer_wls_sorted = non_bayer_wls[sort_indices]
            non_bayer_spectrum_sorted = non_bayer_spectrum[sort_indices]
            
            self._view.panel_spectral_view.plot_preview_spectrum_separate(
                non_bayer_wls_sorted,
                non_bayer_spectrum_sorted,
                bayer_wls,
                bayer_spectrum
            )
            
        except Exception as e:
            pass