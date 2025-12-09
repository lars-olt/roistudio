from PyQt5.QtCore import QThread, pyqtSignal
from pathlib import Path
import numpy as np
from PyQt5.QtGui import QImage, QPixmap
from rapid.helpers import get_zcam_bandset
from marslab.imgops.imgutils import crop
from asdf_settings import rapidlooks

class SceneScanThread(QThread):
    """
    Background thread for scanning IOF files and generating thumbnails.
    Restored to legacy logic: loads RGB bayer bands for speed and iterates observations.
    """
    scene_found = pyqtSignal(str, object, str, str, object, int)  # scene_id, pixmap, filename, folder_path, seq_id, obs_ix
    scan_complete = pyqtSignal(int)  # total scenes found
    scan_error = pyqtSignal(str)  # error message

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        """
        Scans folder for IOF files and generates thumbnails.
        """
        try:
            scenes = self.find_iof_scenes(self.folder_path)
            
            for scene_id, (path, seq_id, obs_ix) in scenes.items():
                try:
                    # Just load RGB bayer image for thumbnail
                    rgb_img, metadata = self.load_rgb_thumbnail(path, seq_id, obs_ix)
                    
                    if rgb_img is not None:
                        pixmap = self.numpy_to_pixmap(rgb_img)
                        
                        # Create descriptive filename with sol and sequence info
                        sol = metadata.get('sol', 'N/A')
                        sequence = metadata.get('sequence', path.name)
                        filename = f"Sol {sol} | {sequence} | Obs {obs_ix:03d}"
                        
                        # Emit scene found with cached info for later loading
                        self.scene_found.emit(
                            scene_id, 
                            pixmap, 
                            filename,
                            str(path),
                            seq_id,
                            obs_ix
                        )
                    
                except Exception:
                    # Skip scenes that fail to load
                    continue
            
            self.scan_complete.emit(len(scenes))
            
        except Exception as e:
            self.scan_error.emit(str(e))

    def load_rgb_thumbnail(self, path, seq_id, obs_ix):
        """
        Loads just the RGB bayer image for thumbnail generation.
        Validates that RGB bayer bands exist.
        """
        try:
            # Get bandset without loading
            bs = get_zcam_bandset(path, seq_id=seq_id, observation_ix=obs_ix, load=False)
            
            # Extract metadata
            metadata = {}
            if hasattr(bs, 'metadata') and bs.metadata is not None:
                # Extract sol
                if 'SOL' in bs.metadata.columns:
                    try:
                        sol_values = bs.metadata['SOL'].unique()
                        if len(sol_values) > 0 and sol_values[0] is not None:
                            metadata['sol'] = int(sol_values[0])
                    except:
                        pass
                
                # Extract sequence
                if 'SEQ_ID' in bs.metadata.columns:
                    try:
                        seq_values = bs.metadata['SEQ_ID'].unique()
                        if len(seq_values) > 0 and seq_values[0] is not None:
                            metadata['sequence'] = str(seq_values[0])
                    except:
                        pass
            
            # Set defaults
            if 'sol' not in metadata:
                metadata['sol'] = '?'
            if 'sequence' not in metadata:
                if seq_id:
                    metadata['sequence'] = seq_id
                else:
                    metadata['sequence'] = path.name
            
            if 'BAND' not in bs.metadata:
                return None, None
            
            available_bands = bs.metadata['BAND'].tolist()
            
            # Check for RGB bands (R1/G1/B1 or R0*/L0*)
            required_rgb_bands = ['R1', 'G1', 'B1']
            has_rgb = all(band in available_bands for band in required_rgb_bands)
            
            if not has_rgb:
                required_rgb_bands = ['R0R', 'R0G', 'R0B']
                has_rgb = all(band in available_bands for band in required_rgb_bands)
                
            if not has_rgb:
                required_rgb_bands = ['L0R', 'L0G', 'L0B']
                has_rgb = all(band in available_bands for band in required_rgb_bands)
            
            if not has_rgb:
                return None, None
            
            # Load the RGB bands
            bs.load(required_rgb_bands)
            
            # Debayer if needed
            if any('0' in band for band in required_rgb_bands):
                bs.bulk_debayer(required_rgb_bands)
            
            crop_settings = rapidlooks.CROP_SETTINGS["crop"]
            
            # Get the bands
            if 'R1' in required_rgb_bands:
                r_band = crop(bs.get_band('R1'), crop_settings)
                g_band = crop(bs.get_band('G1'), crop_settings)
                b_band = crop(bs.get_band('B1'), crop_settings)
            elif 'R0R' in required_rgb_bands:
                r_band = crop(bs.get_band('R0R'), crop_settings)
                g_band = crop(bs.get_band('R0G'), crop_settings)
                b_band = crop(bs.get_band('R0B'), crop_settings)
            else:
                r_band = crop(bs.get_band('L0R'), crop_settings)
                g_band = crop(bs.get_band('L0G'), crop_settings)
                b_band = crop(bs.get_band('L0B'), crop_settings)
            
            # Stack and normalize
            rgb_img = np.stack([r_band, g_band, b_band], axis=-1)
            rgb_img = np.nan_to_num(rgb_img, nan=0.0, posinf=0.0, neginf=0.0)
            
            img_min = rgb_img.min()
            img_max = rgb_img.max()
            if img_max > img_min:
                rgb_img = (rgb_img - img_min) / (img_max - img_min)
            else:
                rgb_img = np.zeros_like(rgb_img)
            rgb_img = (rgb_img * 255).astype(np.uint8)
            
            return rgb_img, metadata
            
        except Exception:
            return None, None

    def find_iof_scenes(self, folder_path):
        """
        Finds all unique IOF scenes in folder and one level down.
        """
        folder = Path(folder_path)
        img_files = []
        
        # Scan current folder and one level down
        for img_file in folder.rglob('*.IMG'):
            if img_file.is_file():
                img_files.append(img_file)
        
        scenes = {}
        checked_dirs = set()
        
        parent_dirs = set(img_file.parent for img_file in img_files)
        
        for parent_dir in parent_dirs:
            if parent_dir in checked_dirs:
                continue
            checked_dirs.add(parent_dir)
            
            seq_id = None
            obs_ix = 0
            
            # Increment obs_ix until we can't find more observations
            while obs_ix < 100:
                try:
                    # Test if this observation exists
                    bs = get_zcam_bandset(
                        parent_dir,
                        seq_id=seq_id,
                        observation_ix=obs_ix,
                        load=False
                    )
                    
                    filts = bs.metadata["BAND"].sort_values()
                    if len(filts) > 0:
                        scene_id = f"{parent_dir.name}_{obs_ix:03d}"
                        scenes[scene_id] = (parent_dir, seq_id, obs_ix)
                        obs_ix += 1
                    else:
                        break
                        
                except Exception:
                    break
        
        return scenes

    def numpy_to_pixmap(self, img_array):
        """Converts numpy array to QPixmap."""
        img_array = np.ascontiguousarray(img_array)
        height, width, channel = img_array.shape
        bytes_per_line = 3 * width
        
        q_image = QImage(
            img_array.data,
            width,
            height,
            bytes_per_line,
            QImage.Format_RGB888
        )
        return QPixmap.fromImage(q_image.copy())