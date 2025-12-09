import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal


class Model(QObject):
    """
    manages all data for ROIStudio.
    """
    # signals for data changes
    data_changed = pyqtSignal()
    scene_loaded = pyqtSignal(dict)  # emits sparc load_result

    def __init__(self):
        super().__init__()
        self._spec_data = np.array([])
        self._roi_data = []
        self._sparc_load_result = None
        self._iof_folder_path = None

    @property
    def spec_data(self):
        return self._spec_data

    @spec_data.setter
    def spec_data(self, data):
        self._spec_data = data
        self.data_changed.emit()

    @property
    def roi_data(self):
        return self._roi_data

    @roi_data.setter
    def roi_data(self, data):
        self._roi_data = data

    @property
    def sparc_load_result(self):
        return self._sparc_load_result

    @sparc_load_result.setter
    def sparc_load_result(self, result):
        self._sparc_load_result = result
        if result is not None:
            self.scene_loaded.emit(result)

    @property
    def iof_folder_path(self):
        return self._iof_folder_path

    @iof_folder_path.setter
    def iof_folder_path(self, path):
        self._iof_folder_path = path
