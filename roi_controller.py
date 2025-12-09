import yaml
import numpy as np
from pathlib import Path
from PyQt5.QtCore import QObject, QThread, pyqtSignal, QPointF
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QPolygonF

from sparc.core.functional import run_sparc
from sparc.core.config import SparcConfig, LoadConfig, SegmentConfig, SegmentationBackend, ROIBackend
from sparc.core.constants import WAVELENGTHS
from sparc.data.loading import load_cube
from colors import Colors


class SparcRunThread(QThread):
    """
    background thread for running SPARC algorithm without blocking UI.
    """
    status_update = pyqtSignal(str)
    sparc_complete = pyqtSignal(object)  # emits SparcResult
    sparc_error = pyqtSignal(str)
    
    def __init__(self, sam_path, folder_path, seq_id, obs_ix):
        super().__init__()
        self.sam_path = sam_path
        self.folder_path = folder_path
        self.seq_id = seq_id
        self.obs_ix = obs_ix
    
    def run(self):
        try:
            from sparc.core.config import SegmentationBackend, ROIBackend
            
            self.status_update.emit("Loading scene...")
            
            config = SparcConfig(
                load=LoadConfig(
                    iof_path=self.folder_path,
                    seq_id=self.seq_id,
                    obs_ix=self.obs_ix,
                    do_apply_pixmaps=True,
                    ignore_bayers=False
                ),
                segment=SegmentConfig(
                    sam_model_path=self.sam_path,
                    backend=SegmentationBackend.GPU  # Enable GPU
                )
            )
            
            # Enable threading for ROI extraction
            config.roi.backend = ROIBackend.THREADED
            
            self.status_update.emit("Running SPARC pipeline...")
            result = run_sparc(
                iof_path=self.folder_path,
                sam_model_path=self.sam_path,
                config=config
            )
            
            self.sparc_complete.emit(result)
            
        except Exception as e:
            self.sparc_error.emit(str(e))


class SceneScanThread(QThread):
    """
    background thread for scanning IOF files and generating thumbnails.
    only loads RGB bayer bands for speed - full SPARC load happens on scene selection.
    """
    scene_found = pyqtSignal(str, object, str, str, object, int)  # scene_id, pixmap, filename, folder_path, seq_id, obs_ix
    scan_complete = pyqtSignal(int)  # total scenes found
    scan_error = pyqtSignal(str)  # error message

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        """
        scans folder for IOF files and generates thumbnails.
        validates filter files exist and loads only RGB for thumbnails.
        """
        try:
            scenes = self.find_iof_scenes(self.folder_path)
            
            for scene_id, (path, seq_id, obs_ix) in scenes.items():
                try:
                    # just load RGB bayer image for thumbnail
                    rgb_img, metadata = self.load_rgb_thumbnail(path, seq_id, obs_ix)
                    
                    if rgb_img is not None:
                        pixmap = self.numpy_to_pixmap(rgb_img)
                        
                        # create descriptive filename with sol and sequence info
                        sol = metadata.get('sol', 'N/A')
                        sequence = metadata.get('sequence', path.name)
                        filename = f"Sol {sol} | {sequence} | Obs {obs_ix:03d}"
                        
                        # emit scene found with cached info for later loading
                        self.scene_found.emit(
                            scene_id, 
                            pixmap, 
                            filename,
                            str(path),
                            seq_id,
                            obs_ix
                        )
                    
                except Exception as e:
                    # skip scenes that fail to load
                    continue
            
            self.scan_complete.emit(len(scenes))
            
        except Exception as e:
            self.scan_error.emit(str(e))

    def load_rgb_thumbnail(self, path, seq_id, obs_ix):
        """
        loads just the RGB bayer image for thumbnail generation.
        validates that RGB bayer bands exist.
        
        returns:
            tuple: (rgb_img, metadata) or (None, None)
                rgb_img : np.ndarray or None
                metadata : dict with 'sol' and 'sequence' keys
        """
        from rapid.helpers import get_zcam_bandset
        from marslab.imgops.imgutils import crop
        from asdf_settings import rapidlooks
        
        try:
            # get bandset without loading
            bs = get_zcam_bandset(path, seq_id=seq_id, observation_ix=obs_ix, load=False)
            
            # extract metadata
            metadata = {}
            if hasattr(bs, 'metadata') and bs.metadata is not None:
                # extract sol from SOL column
                if 'SOL' in bs.metadata.columns:
                    try:
                        sol_values = bs.metadata['SOL'].unique()
                        if len(sol_values) > 0 and sol_values[0] is not None:
                            metadata['sol'] = int(sol_values[0])
                    except:
                        pass
                
                # extract sequence from SEQ_ID column
                if 'SEQ_ID' in bs.metadata.columns:
                    try:
                        seq_values = bs.metadata['SEQ_ID'].unique()
                        if len(seq_values) > 0 and seq_values[0] is not None:
                            metadata['sequence'] = str(seq_values[0])
                    except:
                        pass
            
            # set defaults if not found
            if 'sol' not in metadata:
                metadata['sol'] = '?'
                    
            if 'sequence' not in metadata:
                # use seq_id parameter if available, otherwise folder name
                if seq_id:
                    metadata['sequence'] = seq_id
                else:
                    metadata['sequence'] = path.name
            
            # check metadata for available bands (bs.raw is empty when load=False)
            if 'BAND' not in bs.metadata:
                return None, None
            
            available_bands = bs.metadata['BAND'].tolist()
            
            # check if RGB bayer bands exist in metadata
            # note: we need R0R, R0G, R0B (right camera bayer) or L0R, L0G, L0B (left camera bayer)
            # or the non-bayer R1, G1, B1 if they exist
            required_rgb_bands = ['R1', 'G1', 'B1']
            
            # check if standard RGB bands exist
            has_rgb = all(band in available_bands for band in required_rgb_bands)
            
            if not has_rgb:
                # fall back to right camera bayer
                required_rgb_bands = ['R0R', 'R0G', 'R0B']
                has_rgb = all(band in available_bands for band in required_rgb_bands)
                
            if not has_rgb:
                # fall back to left camera bayer
                required_rgb_bands = ['L0R', 'L0G', 'L0B']
                has_rgb = all(band in available_bands for band in required_rgb_bands)
            
            if not has_rgb:
                return None, None
            
            # load the RGB bands
            bs.load(required_rgb_bands)
            
            # debayer if needed (for bayer patterns like R0R, R0G, R0B)
            if any('0' in band for band in required_rgb_bands):
                bs.bulk_debayer(required_rgb_bands)
            
            # crop and create RGB image
            crop_settings = rapidlooks.CROP_SETTINGS["crop"]
            
            # get the bands (handle both naming conventions)
            if 'R1' in required_rgb_bands:
                r_band = crop(bs.get_band('R1'), crop_settings)
                g_band = crop(bs.get_band('G1'), crop_settings)
                b_band = crop(bs.get_band('B1'), crop_settings)
            elif 'R0R' in required_rgb_bands:
                r_band = crop(bs.get_band('R0R'), crop_settings)
                g_band = crop(bs.get_band('R0G'), crop_settings)
                b_band = crop(bs.get_band('R0B'), crop_settings)
            else:  # L0R, L0G, L0B
                r_band = crop(bs.get_band('L0R'), crop_settings)
                g_band = crop(bs.get_band('L0G'), crop_settings)
                b_band = crop(bs.get_band('L0B'), crop_settings)
            
            # stack and normalize to 0-255
            rgb_img = np.stack([r_band, g_band, b_band], axis=-1)
            
            # handle any NaN or inf values
            rgb_img = np.nan_to_num(rgb_img, nan=0.0, posinf=0.0, neginf=0.0)
            
            # normalize to 0-255
            img_min = rgb_img.min()
            img_max = rgb_img.max()
            if img_max > img_min:
                rgb_img = (rgb_img - img_min) / (img_max - img_min)
            else:
                rgb_img = np.zeros_like(rgb_img)
            rgb_img = (rgb_img * 255).astype(np.uint8)
            
            return rgb_img, metadata
            
        except Exception as e:
            return None, None

    def find_iof_scenes(self, folder_path):
        """
        finds all unique IOF scenes in folder and one level down.
        
        returns:
            dict: {scene_id: (path, seq_id, obs_ix)}
        """
        folder = Path(folder_path)
        img_files = []
        
        # scan current folder and one level down
        for img_file in folder.rglob('*.IMG'):
            if img_file.is_file():
                img_files.append(img_file)
        
        # group by unique observations
        scenes = {}
        checked_dirs = set()
        
        # get unique parent directories
        parent_dirs = set(img_file.parent for img_file in img_files)
        
        for parent_dir in parent_dirs:
            if parent_dir in checked_dirs:
                continue
            checked_dirs.add(parent_dir)
            
            seq_id = None
            obs_ix = 0
            
            # increment obs_ix until we can't find more observations
            while obs_ix < 100:
                try:
                    from rapid.helpers import get_zcam_bandset
                    
                    # test if this observation exists
                    bs = get_zcam_bandset(
                        parent_dir,
                        seq_id=seq_id,
                        observation_ix=obs_ix,
                        load=False
                    )
                    
                    # check if it has required files
                    filts = bs.metadata["BAND"].sort_values()
                    if len(filts) > 0:
                        scene_id = f"{parent_dir.name}_{obs_ix:03d}"
                        scenes[scene_id] = (parent_dir, seq_id, obs_ix)
                        obs_ix += 1
                    else:
                        break
                        
                except Exception:
                    # this obs_ix doesn't exist, move to next directory
                    break
        
        return scenes

    def numpy_to_pixmap(self, img_array):
        """
        converts numpy array to QPixmap.
        
        parameters:
            img_array : np.ndarray
                RGB image array (H, W, 3)
        
        returns:
            pixmap : QPixmap
        """
        # make a copy to ensure data is contiguous and writable
        img_array = np.ascontiguousarray(img_array)
        
        # handle NaN and inf values
        img_array = np.nan_to_num(img_array, nan=0.0, posinf=1.0, neginf=0.0)
        
        # normalize to 0-255 uint8
        if img_array.dtype != np.uint8:
            # check if already in 0-255 range
            if img_array.max() <= 1.0:
                img_array = (img_array * 255).astype(np.uint8)
            else:
                # normalize from current range
                img_min = img_array.min()
                img_max = img_array.max()
                if img_max > img_min:
                    img_array = ((img_array - img_min) / (img_max - img_min) * 255).astype(np.uint8)
                else:
                    img_array = np.zeros_like(img_array, dtype=np.uint8)
        
        height, width, channel = img_array.shape
        bytes_per_line = 3 * width
        
        q_image = QImage(
            img_array.data,
            width,
            height,
            bytes_per_line,
            QImage.Format_RGB888
        )
        
        # make a copy of the QImage to avoid data lifetime issues
        q_image = q_image.copy()
        
        return QPixmap.fromImage(q_image)


class SceneLoadThread(QThread):
    """
    background thread for loading a scene without blocking UI.
    """
    load_complete = pyqtSignal(object)  # emits load_result
    load_error = pyqtSignal(str)  # emits error message
    
    def __init__(self, folder_path, seq_id, obs_ix):
        super().__init__()
        self.folder_path = folder_path
        self.seq_id = seq_id
        self.obs_ix = obs_ix
    
    def run(self):
        """
        loads the scene in background.
        """
        try:
            from sparc.data.loading import load_cube
            
            load_result = load_cube(
                iof_path=self.folder_path,
                seq_id=self.seq_id,
                obs_ix=self.obs_ix,
                do_apply_pixmaps=True,
                ignore_bayers=False
            )
            
            self.load_complete.emit(load_result)
            
        except Exception as e:
            self.load_error.emit(str(e))


class Controller(QObject):
    """
    controls logic for ROIStudio.
    """
    def __init__(self, model, view):
        super().__init__()
        self._model = model
        self._view = view
        self._scan_thread = None
        self._load_thread = None
        self._sparc_thread = None
        self._scene_cache = {}  # maps scene_id to (path, seq_id, obs_ix)
        self._current_scene_id = None  # track scene being loaded

        # load config
        self.config_path = 'config.yml'
        self.load_config()

        # connect signals/slots
        self._view.set_sam_path_signal.connect(self.set_sam_path)
        self._view.open_folder_signal.connect(self.open_iof_folder)
        self._view.scene_dropped_signal.connect(self.load_scene_by_id)
        self._view.run_algorithm_signal.connect(self.run_algorithm)
        
        # connect pixel hover for spectral preview
        self._view.pixel_hover_callback = self.on_pixel_hover

    def load_config(self):
        """
        loads configuration from yaml file.
        """
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            self.config = {'sam_model_path': ''}
            self.save_config()

    def save_config(self):
        """
        saves configuration to yaml file.
        """
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f)

    def set_sam_path(self):
        """
        opens file dialog to set SAM model path.
        """
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
        """
        opens folder dialog and scans for IOF files.
        """
        folder_path = QFileDialog.getExistingDirectory(
            self._view,
            "Select IOF Data Folder",
            ""
        )

        if folder_path:
            self._model.iof_folder_path = folder_path
            self._view.show_status_message(f"Scanning folder: {folder_path}")
            
            # clear existing thumbnails
            self._view.clear_thumbnails()
            self._scene_cache.clear()
            
            # scan for IOF files and generate thumbnails
            self.scan_iof_folder(folder_path)

    def scan_iof_folder(self, folder_path):
        """
        scans folder for IOF files and populates thumbnail grid.
        
        parameters:
            folder_path : str
                path to folder containing IOF data
        """
        # start loading indicator
        self._view.start_loading()
        
        # create and start background thread
        self._scan_thread = SceneScanThread(folder_path)
        self._scan_thread.scene_found.connect(self.on_scene_found)
        self._scan_thread.scan_complete.connect(self.on_scan_complete)
        self._scan_thread.scan_error.connect(self.on_scan_error)
        self._scan_thread.start()
        
        self._view.show_status_message("Scanning for IOF files...")

    def on_scene_found(self, scene_id, pixmap, filename, folder_path, seq_id, obs_ix):
        """
        handles scene found event from scan thread.
        caches scene info for later full SPARC loading.
        """
        # cache scene info for later loading
        self._scene_cache[scene_id] = (folder_path, seq_id, obs_ix)
        self._view.add_scene_thumbnail(scene_id, pixmap, filename)

    def on_scan_complete(self, total_scenes):
        """
        handles scan completion.
        """
        self._view.stop_loading()
        self._view.show_status_message(
            f"Scan complete. Found {total_scenes} scene(s)."
        )

    def on_scan_error(self, error_msg):
        """
        handles scan error.
        """
        self._view.stop_loading()
        self._view.show_status_message(f"Scan error: {error_msg}")

    def numpy_to_pixmap(self, img_array):
        """
        converts numpy array to QPixmap.
        
        parameters:
            img_array : np.ndarray
                RGB image array (H, W, 3)
        
        returns:
            pixmap : QPixmap
        """
        # make a copy to ensure data is contiguous and writable
        img_array = np.ascontiguousarray(img_array)
        
        # handle NaN and inf values
        img_array = np.nan_to_num(img_array, nan=0.0, posinf=1.0, neginf=0.0)
        
        # normalize to 0-255 uint8
        if img_array.dtype != np.uint8:
            # check if already in 0-255 range
            if img_array.max() <= 1.0:
                img_array = (img_array * 255).astype(np.uint8)
            else:
                # normalize from current range
                img_min = img_array.min()
                img_max = img_array.max()
                if img_max > img_min:
                    img_array = ((img_array - img_min) / (img_max - img_min) * 255).astype(np.uint8)
                else:
                    img_array = np.zeros_like(img_array, dtype=np.uint8)
        
        height, width, channel = img_array.shape
        bytes_per_line = 3 * width
        
        q_image = QImage(
            img_array.data,
            width,
            height,
            bytes_per_line,
            QImage.Format_RGB888
        )
        
        # make a copy of the QImage to avoid data lifetime issues
        q_image = q_image.copy()
        
        return QPixmap.fromImage(q_image)

    def load_scene_by_id(self, scene_id):
        """
        loads a scene by its id (called when dropped on canvas).
        displays RGB image on canvas after loading.
        uses background thread to keep UI responsive.
        
        parameters:
            scene_id : str
                unique identifier for the scene
        """
        if scene_id not in self._scene_cache:
            self._view.show_status_message(f"Error: Scene {scene_id} not found in cache")
            return

        # show loading message and indicator
        self._view.show_status_message(f"Loading scene: {scene_id}")
        self._view.start_loading()
        
        # store scene_id for later use in callbacks
        self._current_scene_id = scene_id
        
        # get cached scene info
        folder_path, seq_id, obs_ix = self._scene_cache[scene_id]
        
        # create and start background loading thread
        self._load_thread = SceneLoadThread(folder_path, seq_id, obs_ix)
        self._load_thread.load_complete.connect(self.on_scene_load_complete)
        self._load_thread.load_error.connect(self.on_scene_load_error)
        self._load_thread.start()

    def on_scene_load_complete(self, load_result):
        """
        handles successful scene load from background thread.
        """
        # store in model
        self._model.sparc_load_result = load_result
        
        # select the scene in the thumbnail grid
        self._view.select_scene(self._current_scene_id)
        
        # extract RGB image and display on canvas
        if 'rgb_img' in load_result:
            rgb_img = load_result['rgb_img']
            pixmap = self.numpy_to_pixmap(rgb_img)
            self._view.panel_image_editing.set_image(pixmap)
            
            # stop loading and show completion message
            self._view.stop_loading()
            self._view.show_status_message(
                f"Scene loaded: {load_result['id']}"
            )
        else:
            self._view.stop_loading()
            self._view.show_status_message("Error: No RGB image in load result")

    def on_scene_load_error(self, error_msg):
        """
        handles scene load error from background thread.
        """
        self._view.stop_loading()
        self._view.show_status_message(f"Error loading scene: {error_msg}")
    
    def on_pixel_hover(self, x, y):
        """
        extracts and plots spectrum for hovered pixel.
        uses the merged cube from sparc_load_result for accurate preview.
        """
        if self._model.sparc_load_result is None:
            return
        
        try:
            # use the merged cube directly
            cube = self._model.sparc_load_result.get('cube')
            if cube is None:
                return
            
            # check bounds
            if y >= cube.shape[1] or x >= cube.shape[2]:
                return
            
            # extract full spectrum at pixel location
            full_spectrum = cube[:, y, x]
            
            # handle masked arrays
            if np.ma.is_masked(full_spectrum):
                if full_spectrum.mask.all():
                    return
                full_spectrum = np.ma.filled(full_spectrum, np.nan)
            
            # check for invalid values
            if not np.isfinite(full_spectrum).any():
                return
            
            # separate Bayer and non-Bayer
            bayer_spectrum = full_spectrum[:3]
            non_bayer_spectrum = full_spectrum[3:]
            
            bayer_wls = WAVELENGTHS[:3]
            non_bayer_wls = np.array(WAVELENGTHS[3:])
            
            # sort non-Bayer by wavelength
            sort_indices = np.argsort(non_bayer_wls)
            non_bayer_wls_sorted = non_bayer_wls[sort_indices]
            non_bayer_spectrum_sorted = non_bayer_spectrum[sort_indices]
            
            # pass sorted non-Bayer and unsorted Bayer separately
            self._view.panel_spectral_view.plot_preview_spectrum_separate(
                non_bayer_wls_sorted, 
                non_bayer_spectrum_sorted,
                bayer_wls,
                bayer_spectrum
            )
            
        except Exception as e:
            pass
    
    def hex_to_rgb(self, hex_color):
        """
        converts hex color string to RGB tuple.
        
        parameters:
            hex_color : str
                hex color string (e.g., "#FF5733" or "FF5733")
        
        returns:
            tuple: (r, g, b) values 0-255
        """
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def run_algorithm(self, algorithm_name):
        """
        runs the selected SPARC algorithm and visualizes results.
        """
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
        
        # start loading indicator
        self._view.show_status_message("Initializing SPARC algorithm...")
        self._view.start_loading()
        
        # get scene info
        scene_id = self._current_scene_id
        folder_path, seq_id, obs_ix = self._scene_cache[scene_id]
        
        # create and start background thread
        self._sparc_thread = SparcRunThread(sam_path, folder_path, seq_id, obs_ix)
        self._sparc_thread.status_update.connect(self.on_sparc_status_update)
        self._sparc_thread.sparc_complete.connect(self.on_sparc_complete)
        self._sparc_thread.sparc_error.connect(self.on_sparc_error)
        self._sparc_thread.start()
    
    def on_sparc_status_update(self, message):
        """
        handles status updates from SPARC thread.
        """
        self._view.show_status_message(message)
    
    def on_sparc_complete(self, result):
        """
        handles successful SPARC completion from background thread.
        """
        try:
            from marslab.compat import mertools
            
            if result.final_rois is None or len(result.final_rois) == 0:
                self._view.show_status_message("SPARC found no ROIs")
                self._view.stop_loading()
                return
            
            num_rois = len(result.final_rois)
            
            self._view.show_status_message(f"Visualizing {num_rois} ROIs...")
            
            # get color list from mertools
            hex_colors = list(mertools.MERSPECT_M20_COLOR_MAPPINGS.values())
            color_list = [self.hex_to_rgb(c) for c in hex_colors]
            
            rois_with_spectra = self.extract_sparc_results(result)
            self.visualize_rois(rois_with_spectra, color_list)
            
            # use new method that stores ROI spectra
            self._view.panel_spectral_view.plot_roi_spectra(rois_with_spectra, color_list)
            
            self._view.stop_loading()
            self._view.show_status_message(f"SPARC complete: {num_rois} ROIs found")
            
        except Exception as e:
            self._view.stop_loading()
            self._view.show_status_message(f"Error visualizing results: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def on_sparc_error(self, error_msg):
        """
        handles SPARC error from background thread.
        """
        self._view.stop_loading()
        self._view.show_status_message(f"Error running SPARC: {error_msg}")
        import traceback
        traceback.print_exc()
    
    def extract_sparc_results(self, result):
        """
        extracts ROI data with spectra from SparcResult.
        
        parameters:
            result : SparcResult
                completed SPARC pipeline result
                
        returns:
            list of dicts with 'roi', 'spectrum', 'std', 'bayer_spectrum', 'bayer_std' keys
        """
        rois = []
        
        # Separate Bayer and non-Bayer
        bayer_wls = WAVELENGTHS[:3]
        non_bayer_wls = np.array(WAVELENGTHS[3:])
        
        # Sort non-Bayer wavelengths for proper line plotting
        sort_indices = np.argsort(non_bayer_wls)
        non_bayer_wls_sorted = non_bayer_wls[sort_indices]
        
        # create ROI dictionaries
        for i, (roi_rect, spectrum, std) in enumerate(zip(result.final_rois, result.final_spectra, result.final_stds)):
            x, y, w, h = roi_rect
            
            # create mask from rectangle
            mask = np.zeros(result.segments.shape, dtype=bool)
            mask[y:y+h, x:x+w] = True
            
            # separate bayer and non-bayer spectra
            bayer_spectrum = spectrum[:3].tolist()
            non_bayer_spectrum = spectrum[3:]
            
            # separate bayer and non-bayer stds
            bayer_std = std[:3].tolist()
            non_bayer_std = std[3:]
            
            # sort non-bayer by wavelength
            non_bayer_spectrum_sorted = non_bayer_spectrum[sort_indices].tolist()
            non_bayer_std_sorted = non_bayer_std[sort_indices].tolist()
            
            rois.append({
                'roi': roi_rect,
                'mask': mask,
                'spectrum': non_bayer_spectrum_sorted,
                'std': non_bayer_std_sorted,
                'wavelengths': non_bayer_wls_sorted.tolist(),
                'bayer_spectrum': bayer_spectrum,
                'bayer_std': bayer_std,
                'bayer_wavelengths': bayer_wls,
                'mineral': f'ROI_{i+1}'
            })
        
        return rois
    
    def visualize_rois(self, rois, color_list):
        """
        overlays ROIs on the canvas image using mertools colors.
        """
        rgb_pixmap = self._view.panel_image_editing.canvas_container.canvas.image
        if rgb_pixmap is None:
            return
        
        image = rgb_pixmap.toImage()
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        
        for i, roi_data in enumerate(rois):
            color = color_list[i % len(color_list)]
            x, y, w, h = roi_data['roi']
            
            qcolor = QColor(*color, 80)
            painter.setPen(QPen(QColor(*color), 2))
            painter.setBrush(qcolor)
            painter.drawRect(x, y, w, h)
        
        painter.end()
        self._view.panel_image_editing.set_image(QPixmap.fromImage(image))