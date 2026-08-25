"""Persistence for user-interface state that is safe to carry between sessions."""

from PyQt5.QtCore import QByteArray, QSettings

from .scale import Scale


_SETTINGS_VERSION = 1


class UISettings:
    """Save and restore display preferences without mixing them with scene state."""

    def __init__(self, settings=None, application_name='ROIStudio'):
        self._settings = (
            settings
            if settings is not None
            else QSettings(
                QSettings.IniFormat,
                QSettings.UserScope,
                'ROIStudio',
                application_name,
            )
        )

    def _is_current(self) -> bool:
        return self._value('version', 0, int) == _SETTINGS_VERSION

    def _value(self, key, default, value_type):
        try:
            return self._settings.value(key, default, type=value_type)
        except (TypeError, ValueError):
            return default

    def restore_scale(self):
        """Restore scale before widgets are built to avoid a startup resize."""
        if self._is_current():
            Scale.set_user_offset(
                self._value('scale/user_offset', Scale.user_offset, float)
            )

    def restore_view(self, view):
        if not self._is_current():
            return

        geometry = self._settings.value('window/geometry')
        if isinstance(geometry, QByteArray):
            view.restoreGeometry(geometry)

        main_splitter = self._settings.value('splitters/main')
        if isinstance(main_splitter, QByteArray):
            view.main_splitter.restoreState(main_splitter)

        left_splitter = self._settings.value('splitters/left')
        if isinstance(left_splitter, QByteArray):
            view.left_splitter.restoreState(left_splitter)

        view.set_mode(
            self._value('window/upper_left_panel', view.mode, str)
        )
        view.set_roi_labels_visible(
            self._value(
                'display/roi_labels',
                view.action_roi_labels.isChecked(),
                bool,
            )
        )

        panel = view.panel_settings
        sections = panel.section_states()
        panel.apply_section_states({
            key: self._value(f'sections/{key}', expanded, bool)
            for key, expanded in sections.items()
        })

        display = panel.display_preferences()
        panel.apply_display_preferences(
            y_min=self._value('spectral/y_min', display['y_min'], float),
            y_max=self._value('spectral/y_max', display['y_max'], float),
            merge_spectra=self._value(
                'spectral/merge_spectra',
                display['merge_spectra'],
                bool,
            ),
            line_width=self._value(
                'spectral/line_width',
                display['line_width'],
                float,
            ),
        )
        panel.set_paired_roi_drawing_enabled(
            self._value(
                'editing/paired_roi_drawing',
                panel.paired_roi_drawing_enabled(),
                bool,
            )
        )

    def save(self, view):
        panel = view.panel_settings
        display = panel.display_preferences()

        self._settings.setValue('version', _SETTINGS_VERSION)
        self._settings.setValue('scale/user_offset', Scale.user_offset)
        self._settings.setValue('window/geometry', view.saveGeometry())
        self._settings.setValue('window/upper_left_panel', view.mode)
        self._settings.setValue('splitters/main', view.main_splitter.saveState())
        self._settings.setValue('splitters/left', view.left_splitter.saveState())
        self._settings.setValue(
            'display/roi_labels',
            view.action_roi_labels.isChecked(),
        )

        for key, expanded in panel.section_states().items():
            self._settings.setValue(f'sections/{key}', expanded)

        for key, value in display.items():
            self._settings.setValue(f'spectral/{key}', value)
        self._settings.setValue(
            'editing/paired_roi_drawing',
            panel.paired_roi_drawing_enabled(),
        )

        self._settings.sync()
