from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QFileDialog


class SceneController(QObject):
    """Handles scene scanning and loading operations."""

    scan_started = pyqtSignal()
    scan_stopped = pyqtSignal()
    # Added instrument (str) to scene_found signature
    scene_found = pyqtSignal(str, object, str, str, object, int, str)
    scan_complete = pyqtSignal(int)
    scan_error = pyqtSignal(str)

    load_started = pyqtSignal()
    load_stopped = pyqtSignal()
    load_complete = pyqtSignal(object)
    load_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._scan_thread = None
        self._load_thread = None
        # Cache now stores (folder_path, seq_id, obs_ix, instrument)
        self._scene_cache = {}

    def open_folder_dialog(self, parent):
        """Opens folder selection dialog."""
        return QFileDialog.getExistingDirectory(parent, "Select IOF Data Folder", "")

    def start_scan(self, folder_path):
        """Starts background scene scanning."""
        from workers.scene_scanner import SceneScanThread

        self._scene_cache.clear()

        self._scan_thread = SceneScanThread(folder_path)
        self._scan_thread.scene_found.connect(self._on_scene_found)
        self._scan_thread.scan_complete.connect(self.scan_complete.emit)
        self._scan_thread.scan_error.connect(self.scan_error.emit)
        self._scan_thread.start()

        self.scan_started.emit()

    def _on_scene_found(self, scene_id, pixmap, filename, folder_path, seq_id, obs_ix, instrument):
        """Caches scene info (including instrument) and forwards signal."""
        self._scene_cache[scene_id] = (folder_path, seq_id, obs_ix, instrument)
        self.scene_found.emit(scene_id, pixmap, filename, folder_path, seq_id, obs_ix, instrument)

    def start_load(self, scene_id):
        """Starts background scene loading."""
        from workers.scene_loader import SceneLoadThread

        if scene_id not in self._scene_cache:
            self.load_error.emit(f"Scene {scene_id} not found in cache")
            return None

        folder_path, seq_id, obs_ix, instrument = self._scene_cache[scene_id]

        self._load_thread = SceneLoadThread(folder_path, seq_id, obs_ix, instrument)
        self._load_thread.load_complete.connect(self.load_complete.emit)
        self._load_thread.load_error.connect(self.load_error.emit)
        self._load_thread.start()

        self.load_started.emit()
        return scene_id

    def get_scene_info(self, scene_id):
        """Returns cached scene info as (folder_path, seq_id, obs_ix, instrument)."""
        return self._scene_cache.get(scene_id)

    def clear_cache(self):
        """Clears scene cache."""
        self._scene_cache.clear()