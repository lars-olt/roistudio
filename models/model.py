import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal


# Internal instrument selection. Change this to switch between instruments.
# Will be replaced by a GUI dropdown in a future update.
INSTRUMENT = "ZCAM"  # Options: "ZCAM", "PCAM"


class Model(QObject):
    """Manages all data for ROIStudio."""

    data_changed = pyqtSignal()
    scene_loaded = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._spec_data = np.array([])
        self._roi_data = []
        self._sparc_load_result = None
        self._iof_folder_path = None
        self._instrument = INSTRUMENT

    @property
    def instrument(self):
        return self._instrument

    @instrument.setter
    def instrument(self, value):
        if value not in ("ZCAM", "PCAM"):
            raise ValueError(f"Unsupported instrument: {value}. Must be 'ZCAM' or 'PCAM'.")
        self._instrument = value

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
            # Keep instrument in sync with what was actually loaded
            if isinstance(result, dict) and 'instrument' in result:
                self._instrument = result['instrument']
            self.scene_loaded.emit(result)

    @property
    def iof_folder_path(self):
        return self._iof_folder_path

    @iof_folder_path.setter
    def iof_folder_path(self, path):
        self._iof_folder_path = path