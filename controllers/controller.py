"""Main application controller - wires signals and delegates to focused handlers."""

import importlib

import numpy as np
from PyQt5.QtCore import QObject
import yaml

from .scene_controller import SceneController
from .sparc_controller import SparcController
from .color_manager import ColorManager
from . import scene_callbacks, roi_controller, sel_controller
from utils.rendering import render_images
from utils.paths import _get_config_path
from roi_groups import group_roi_regions, class_index_for_region
from presets import INSTRUMENT_PRESETS

# How much non-active ROI visuals dim while the metadata panel is open.
_METADATA_DIM = 0.4


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
        self._selection_data          = []
        self._selection_colors        = []
        self._selection_names         = []
        self._is_split_screen         = False
        self._paired_roi_drawing      = True
        self._split_pair_color_name   = None
        self._split_pair_eyes         = set()
        self._pending_recolor_index   = None  # ROI index being recolored, or None for the next color
        self._view_mode               = 'scene_loading'
        self._metadata_active_index   = None  # ROI highlighted by the metadata panel
        self._exposure                = 1.0   # RGB stretch exposure factor, neutral per scene
        self._algorithm_enabled       = bool(getattr(
            getattr(view, 'edition', None), 'algorithm_enabled', True
        ))
        self.algorithm_controller     = None
        self._sparc_callbacks         = None

        self.config_path = None
        self.config = {}
        if self._algorithm_enabled:
            self.config_path = _get_config_path()
            self.load_config()

        self.color_manager     = ColorManager(self._model.instrument)
        self.scene_controller  = SceneController()
        self.sparc_controller  = SparcController()
        if self._algorithm_enabled:
            # String-based imports keep the algorithm graph out of PyInstaller's
            # Lite analysis. The full spec explicitly includes these modules.
            algorithm_module = importlib.import_module(
                'controllers.algorithm_controller'
            )
            self.algorithm_controller = algorithm_module.AlgorithmController()
            self._sparc_callbacks = importlib.import_module(
                'controllers.sparc_callbacks'
            )

        self._connect_view_signals()
        self._connect_controller_signals()

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
        if self.config_path is None:
            return
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
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_view_signals(self):
        if self._algorithm_enabled:
            self._view.set_sam_path_signal.connect(self.set_sam_path)
        self._view.open_folder_signal.connect(self._open_iof_folder)
        self._view.export_sel_signal.connect(self._export_sel)
        self._view.load_sel_signal.connect(self._load_sel)
        self._view.load_fits_signal.connect(self._load_fits)
        self._view.export_context_signal.connect(self._export_context)
        self._view.export_fits_signal.connect(self._export_fits)
        self._view.scene_dropped_signal.connect(self._load_scene_by_id)
        if self._algorithm_enabled:
            self._view.run_algorithm_signal.connect(self._run_algorithm)
        self._view.scene_double_clicked_signal.connect(self._load_scene_by_id)
        self._view.pixel_hover_callback = self._on_pixel_hover
        self._view.apply_stretch_mode_signal.connect(self._apply_stretch_mode)
        self._view.delete_all_rois_signal.connect(self._delete_all_rois)

        panel = self._view.panel_image_editing
        panel.roi_changed.connect(self._on_roi_changed)
        panel.roi_deleted.connect(self._on_roi_deleted)
        panel.roi_created.connect(self._on_roi_created)
        panel.roi_too_small.connect(
            lambda: self._view.show_status_message("ROI too small - draw a larger rectangle.")
        )
        panel.split_screen_unavailable.connect(
            lambda: self._view.show_status_message("Split screen unavailable - scene has only one camera side.")
        )
        panel.split_screen_exit_requested.connect(self._on_split_screen_exit_requested)
        panel.split_screen_toggled.connect(self._on_split_screen_toggled)
        panel.rgb_bands_changed.connect(self._on_rgb_bands_changed)
        panel.roi_right_clicked.connect(self._on_roi_right_clicked)
        panel.active_color_palette_requested.connect(
            self._on_active_color_palette_requested
        )
        panel._swatch_grid.color_selected.connect(self._on_color_selected)
        panel._swatch_grid.spectrum_action_requested.connect(
            self._on_spectrum_action_requested
        )

        self._view.panel_roi_metadata.metadata_changed.connect(self._on_roi_metadata_changed)
        self._view.panel_roi_metadata.roi_activated.connect(self._on_roi_metadata_activated)
        self._view.mode_changed.connect(self._on_view_mode_changed)
        self._view.panel_settings.exposure_changed.connect(self._on_exposure_changed)
        self._view.panel_settings.paired_roi_drawing_changed.connect(
            self._on_paired_roi_drawing_changed
        )

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

        if self.algorithm_controller is not None:
            algorithm = self.algorithm_controller
            algorithm.started.connect(self._view.start_loading)
            algorithm.stopped.connect(self._view.stop_loading)
            algorithm.status_update.connect(self._view.show_status_message)
            algorithm.complete.connect(self._on_sparc_complete)
            algorithm.error.connect(self._on_sparc_error)

    # ------------------------------------------------------------------
    # Scene scanning / loading
    # ------------------------------------------------------------------

    def _open_iof_folder(self):
        folder_path = self.scene_controller.open_folder_dialog(self._view)
        if folder_path:
            self._model.iof_folder_path = folder_path
            self._view.clear_thumbnails()
            self.scene_controller.clear_cache()
            self.scene_controller.start_scan(folder_path)
            self._view.show_status_message("Scanning for IOF files...")

    def _load_scene_by_id(self, scene_id):
        if not self.scene_controller.get_scene_info(scene_id):
            self._view.show_status_message(f"Error: scene {scene_id} not found in cache")
            return
        self._view.show_status_message("Loading scene...")
        self._current_scene_id        = self.scene_controller.start_load(scene_id)
        self._current_rois_data       = []
        self._current_colors          = []
        self._current_color_names     = []
        self._selection_data          = []
        self._selection_colors        = []
        self._selection_names         = []
        self._split_pair_color_name   = None
        self._split_pair_eyes         = set()
        self._pending_recolor_index   = None
        self._metadata_active_index   = None
        self._exposure                = 1.0
        self._view.panel_settings.reset_exposure()
        self.color_manager.reset()
        self._view.panel_image_editing.set_rois([], [], [])
        self._view.panel_roi_metadata.set_rois([], [], [])
        self._view.panel_spectral_view.clear_roi_spectra()
        self._view.panel_spectral_view.clear_plot()
        self._view.set_export_enabled(False)
        self._view.set_science_notes('')   # notes describe the previous observation

    def _on_scene_found(self, scene_id, pixmap, filename, _folder, _seq_id, _obs_ix, _instrument, complete, sort_key):
        scene_callbacks.on_scene_found(scene_id, pixmap, filename, self._view, complete, sort_key)

    def _on_scan_complete(self, total_scenes):
        scene_callbacks.on_scan_complete(total_scenes, self._view)

    def _on_scan_error(self, error_msg):
        scene_callbacks.on_scan_error(error_msg, self._view)

    def _on_scene_load_complete(self, load_result):
        scene_callbacks.on_scene_load_complete(
            load_result, self._current_scene_id, self._model, self._view
        )
        self.color_manager.set_instrument(self._model.instrument)
        self._render_current_images()
        self._refresh_swatch()
        # enable crop tool now that a scene is loaded (single screen only)
        if not self._is_split_screen:
            self._view.panel_image_editing.set_crop_enabled(True)

    def _on_scene_load_error(self, error_msg):
        scene_callbacks.on_scene_load_error(error_msg, self._view)

    # ------------------------------------------------------------------
    # SPARC
    # ------------------------------------------------------------------

    def _run_algorithm(self):
        if self.algorithm_controller is None or self._sparc_callbacks is None:
            return
        self._sparc_callbacks.run_algorithm(
            self._model, self._view,
            self.scene_controller, self.algorithm_controller,
            self._current_scene_id,
            self.config.get('sam_model_path', ''),
            self._view.panel_settings.get_parameters(),
            crop_rect = self._view.panel_image_editing.get_crop_rect(),
        )

    def _on_sparc_complete(self, result):
        try:
            self._split_pair_color_name = None
            self._split_pair_eyes = set()
            # reserve colors already in use so new ROIs get distinct colors
            self.color_manager.reserve(self._current_color_names)
            outcome = self._sparc_callbacks.on_sparc_complete(
                result, self._model, self._view,
                self.algorithm_controller, self.sparc_controller,
                self.color_manager,
            )
            if outcome is not None:
                new_rois, new_colors, new_names = outcome
                self._current_rois_data   += new_rois
                self._current_colors      += new_colors
                self._current_color_names += new_names
                self._update_roi_view()
                self._view.set_export_enabled(True)
                self._refresh_swatch()
        except Exception as e:
            self._view.stop_loading()
            self._view.show_status_message(f"Error visualizing results: {e}")
            import traceback; traceback.print_exc()

    def _on_sparc_error(self, error_msg):
        if self._sparc_callbacks is not None:
            self._sparc_callbacks.on_sparc_error(error_msg, self._view)

    # ------------------------------------------------------------------
    # ROI editing
    # ------------------------------------------------------------------

    def _has_dual_cubes(self):
        lr = self._model.sparc_load_result
        return (lr is not None
                and 'left_cube' in lr
                and 'right_cube' in lr
                and 'merged_band_recipe' in lr)

    def _on_roi_created(self, rect, camera):
        if self._model.sparc_load_result is None:
            return
        try:
            paired_draw = (camera == 'single'
                           or (camera in {'left', 'right'}
                               and getattr(self, '_paired_roi_drawing', True)))
            roi_data    = roi_controller.on_roi_created(
                rect, camera,
                self._model.sparc_load_result,
                self._get_instrument_config(),
                self.sparc_controller,
                self._has_dual_cubes(),
                paired_draw=paired_draw,
            )
            color, name = self.color_manager.next()
            self._current_rois_data.append(roi_data)
            self._current_colors.append(color)
            self._current_color_names.append(name)
            self._update_split_color_cycle(
                name, 'single' if paired_draw else camera
            )
            self._update_roi_view()
            self._view.set_export_enabled(True)
            self._view.show_status_message("ROI created")
        except Exception as e:
            self._view.show_status_message(f"Error creating ROI: {e}")

    def _on_roi_deleted(self, roi_index, camera):
        if not (0 <= roi_index < len(self._current_rois_data)):
            return
        try:
            name = self._current_color_names[roi_index]
            color = self._current_colors[roi_index]
            class_index = class_index_for_region(
                group_roi_regions(
                    self._current_rois_data,
                    self._current_colors,
                    self._current_color_names,
                ),
                roi_index,
            )

            paired_delete = (camera == 'single'
                             or (camera in {'left', 'right'}
                                 and getattr(self, '_paired_roi_drawing', True)))
            removed_region = paired_delete
            if camera in {'left', 'right'} and not paired_delete:
                roi = dict(self._current_rois_data[roi_index])
                roi[f'{camera}_rect'] = None
                if roi.get('left_rect') is None and roi.get('right_rect') is None:
                    removed_region = True
                else:
                    load_result = self._model.sparc_load_result
                    spec_data = roi_controller.spectrum_data(
                        roi.get('left_rect'), roi.get('right_rect'),
                        load_result, self._get_instrument_config(),
                        self.sparc_controller, self._has_dual_cubes(),
                    )
                    roi['roi'] = roi_controller.canvas_rect(
                        roi, load_result.get('instrument', 'ZCAM')
                    )
                    self._current_rois_data[roi_index] = {**roi, **spec_data}

            if removed_region:
                self._current_colors.pop(roi_index)
                self._current_color_names.pop(roi_index)
                self._current_rois_data.pop(roi_index)
                if name not in self._current_color_names:
                    self.color_manager.recycle(color, name)
                    if class_index is not None:
                        self._view.panel_spectral_view.roi_removed(class_index)

            self._update_roi_view()
            self._view.set_export_enabled(bool(self._current_rois_data))
            if removed_region:
                self._view.show_status_message(f"{name} region deleted")
            elif camera in {'left', 'right'}:
                self._view.show_status_message(
                    f"{name} region removed from {camera} eye"
                )
        except Exception as e:
            self._view.show_status_message(f"Error deleting ROI: {e}")

    def _on_roi_changed(self, roi_index, new_rect, camera):
        if self._model.sparc_load_result is None or roi_index >= len(self._current_rois_data):
            return
        try:
            self._current_rois_data[roi_index] = roi_controller.on_roi_changed(
                roi_index, new_rect, camera,
                self._current_rois_data,
                self._model.sparc_load_result,
                self._get_instrument_config(),
                self.sparc_controller,
                self._has_dual_cubes(),
            )
            # The canvas has already applied this geometry interactively. A
            # full refresh would call CanvasContainer.set_rois(), which clears
            # its selected index and makes the resize handles disappear on
            # mouse release. Geometry edits do not change class membership or
            # eye coverage, so only the aggregate spectral data needs refresh.
            self._update_roi_view(refresh_canvas=False, refresh_metadata=False)
        except Exception as e:
            self._view.show_status_message(f"Error updating ROI: {e}")

    def _update_roi_view(self, refresh_canvas=True, refresh_metadata=True):
        self._rebuild_selection_data()
        if refresh_metadata:
            self._view.panel_roi_metadata.set_rois(
                self._selection_data, self._selection_colors,
                self._selection_names, instrument=self._model.instrument,
            )
        if refresh_canvas:
            self._refresh_canvas_rois()
        self._view.panel_spectral_view.plot_roi_spectra(
            self._selection_data, self._selection_colors
        )
        self._refresh_swatch()

    def _rebuild_selection_data(self):
        """Aggregate same-color region geometry, metadata, and spectra."""
        groups = group_roi_regions(
            self._current_rois_data,
            self._current_colors,
            self._current_color_names,
        )
        load_result = self._model.sparc_load_result
        instrument_config = self._get_instrument_config() if load_result is not None else {}
        selection_data = []
        for group in groups:
            left_rects = group['left_rects'] or None
            right_rects = group['right_rects'] or None
            spec_data = (
                roi_controller.spectrum_data(
                    left_rects, right_rects, load_result, instrument_config,
                    self.sparc_controller, self._has_dual_cubes(),
                ) if load_result is not None else {}
            )
            instrument = (load_result or {}).get('instrument', self._model.instrument)
            geometry = {
                'left_rect': group['left_rects'][0] if group['left_rects'] else None,
                'right_rect': group['right_rects'][0] if group['right_rects'] else None,
            }
            selection_data.append({
                'roi': roi_controller.canvas_rect(geometry, instrument),
                **geometry,
                'left_rects': group['left_rects'],
                'right_rects': group['right_rects'],
                'metadata': group['metadata'],
                'region_count': len(group['regions']),
                **spec_data,
            })
        self._selection_data = selection_data
        self._selection_colors = [group['color'] for group in groups]
        self._selection_names = [group['name'] for group in groups]

    def _refresh_canvas_rois(self):
        self._view.panel_image_editing.set_rois(
            self._current_rois_data, self._canvas_colors(), self._current_color_names
        )

    def _canvas_colors(self):
        """Return ROI colors, dimming inactive outlines in metadata mode."""
        colors = self._current_colors
        ix     = self._metadata_active_index
        if (self._view_mode != 'roi_metadata' or ix is None
                or not (0 <= ix < len(self._selection_names))):
            return colors
        active_name = self._selection_names[ix]
        return [
            color if self._current_color_names[i] == active_name
            else tuple(int(v * _METADATA_DIM) for v in color)
            for i, color in enumerate(colors)
        ]

    def _on_roi_metadata_activated(self, roi_index):
        self._metadata_active_index = roi_index
        self._refresh_metadata_highlight()

    def _on_view_mode_changed(self, mode):
        self._view_mode = mode
        self._refresh_metadata_highlight()

    def _refresh_metadata_highlight(self):
        self._refresh_canvas_rois()
        ix = self._metadata_active_index
        active_index = (ix if self._view_mode == 'roi_metadata'
                        and ix is not None
                        and 0 <= ix < len(self._selection_colors)
                        else None)
        self._view.panel_spectral_view.set_active_roi(active_index, _METADATA_DIM)

    def _on_roi_metadata_changed(self, class_index, metadata):
        """Store one metadata record on every region in a selection class."""
        if not 0 <= class_index < len(self._selection_names):
            return
        name = self._selection_names[class_index]
        for index, region_name in enumerate(self._current_color_names):
            if region_name == name:
                self._current_rois_data[index]['metadata'] = dict(metadata)

    def _refresh_swatch(self):
        """Sync the active color swatch and palette grid with current state."""
        panel             = self._view.panel_image_editing
        next_color, next_name = self.color_manager.peek()
        panel.set_active_color(next_color)
        panel.set_swatch_palette(
            self.color_manager.full_palette(),
            in_use_names  = self._current_color_names,
            selected_name = next_name,
        )

    def _on_roi_right_clicked(self, roi_index, global_pos, camera):
        """Open the palette and spectrum action for an existing ROI."""
        if not 0 <= roi_index < len(self._current_rois_data):
            return
        self._pending_recolor_index = roi_index
        panel = self._view.panel_image_editing
        panel.set_swatch_palette(
            self.color_manager.full_palette(),
            in_use_names  = self._current_color_names,
            selected_name = self._current_color_names[roi_index],
        )
        class_index = self._selection_names.index(self._current_color_names[roi_index])
        panel._swatch_grid.set_spectrum_action(
            True,
            self._view.panel_spectral_view.is_spectrum_hidden(class_index),
        )
        panel._swatch_grid.show_at(global_pos)

    def _on_active_color_palette_requested(self):
        """Make the toolbar palette unambiguously target the next draw."""
        self._pending_recolor_index = None

    def _on_spectrum_action_requested(self):
        roi_index = self._pending_recolor_index
        self._pending_recolor_index = None
        if roi_index is None or not 0 <= roi_index < len(self._current_rois_data):
            return
        name = self._current_color_names[roi_index]
        class_index = self._selection_names.index(name)
        panel = self._view.panel_spectral_view
        if panel.is_spectrum_hidden(class_index):
            panel.show_spectrum(class_index)
            action = "shown"
        else:
            panel.hide_spectrum(class_index)
            action = "hidden"
        self._view.show_status_message(f"Spectrum for {name} {action}")

    def _on_color_selected(self, color, name):
        """Handle a swatch pick - either recolor an ROI or set the next color."""
        if self._pending_recolor_index is not None:
            idx = self._pending_recolor_index
            self._pending_recolor_index = None
            if idx < len(self._current_rois_data):
                old_color = self._current_colors[idx]
                old_name  = self._current_color_names[idx]
                if old_name != name and self._current_color_names.count(old_name) == 1:
                    self.color_manager.recycle(old_color, old_name)
                self.color_manager.consume(name)
                self._current_colors[idx]      = color
                self._current_color_names[idx] = name
                target_metadata = next(
                    (r.get('metadata', {}) for i, r in enumerate(self._current_rois_data)
                     if i != idx and self._current_color_names[i] == name),
                    self._current_rois_data[idx].get('metadata', {}),
                )
                self._current_rois_data[idx]['metadata'] = dict(target_metadata)
                self._update_roi_view()
        else:
            held_name = self._split_pair_color_name
            if held_name is not None and held_name != name:
                # Choosing another color is how the user finishes an
                # intentional single-eye selection without drawing a mate.
                self.color_manager.consume(held_name)
                self._split_pair_color_name = None
                self._split_pair_eyes = set()
            self.color_manager.set_next(name)
            self._refresh_swatch()

    def _update_split_color_cycle(self, name, camera):
        """Hold a split-view color until it has been drawn in both eyes."""
        if camera not in {'left', 'right'}:
            self._split_pair_color_name = None
            self._split_pair_eyes = set()
            return

        if self._split_pair_color_name != name:
            self._split_pair_color_name = name
            self._split_pair_eyes = set()
        self._split_pair_eyes.add(camera)

        if self._split_pair_eyes == {'left', 'right'}:
            self._split_pair_color_name = None
            self._split_pair_eyes = set()
        else:
            # next() consumed the color for this draw; put it back at the
            # front so the complementary eye receives the same class.
            self.color_manager.set_next(name)

    # ------------------------------------------------------------------
    # SEL / FITS export / import
    # ------------------------------------------------------------------

    def _export_sel(self):
        sel_controller.export_sel(
            self._view, self._model,
            self._current_rois_data,
            self._current_color_names,
            self.color_manager,
        )

    def _export_fits(self):
        sel_controller.export_fits(
            self._view, self._model,
            self._current_rois_data,
            self._current_color_names,
        )

    def _export_context(self):
        sel_controller.export_context(
            self._view, self._model,
            self._current_rois_data,
            self._current_colors,
            self._current_color_names,
            self.color_manager,
            selection_data=self._selection_data,
            selection_colors=self._selection_colors,
        )

    def _load_sel(self, sel_path=None):
        self._apply_loaded_rois(sel_controller.load_sel(
            self._view, self._model,
            self._get_instrument_config(),
            self.sparc_controller,
            self._has_dual_cubes(),
            self.color_manager,
            sel_path=sel_path,
        ))

    def _load_fits(self, fits_path=None):
        self._apply_loaded_rois(sel_controller.load_fits(
            self._view, self._model,
            self._get_instrument_config(),
            self.sparc_controller,
            self._has_dual_cubes(),
            self.color_manager,
            fits_path=fits_path,
        ))

    def _apply_loaded_rois(self, outcome):
        if outcome is None:
            return
        self._split_pair_color_name = None
        self._split_pair_eyes = set()
        self._view.panel_spectral_view.show_all_spectra()
        self._current_rois_data, self._current_colors, self._current_color_names = outcome
        self._update_roi_view()
        self._view.set_export_enabled(True)

        # Open both cameras so every loaded selection region is immediately visible.
        if self._has_dual_cubes() and not self._is_split_screen:
            self._view.panel_image_editing.enter_split_screen()

    # ------------------------------------------------------------------
    # Hover preview
    # ------------------------------------------------------------------

    def _on_pixel_hover(self, x, y):
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

            nb_spectrum = full_spectrum[n_rgb:]
            nb_wls      = all_wls[n_rgb:n_rgb + len(nb_spectrum)]
            bayer_wls   = all_wls[:n_rgb]

            sort_ix = np.argsort(nb_wls)
            self._view.panel_spectral_view.plot_preview_spectrum_separate(
                nb_wls[sort_ix], nb_spectrum[sort_ix], bayer_wls, full_spectrum[:n_rgb]
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_current_images(self):
        if self._model.sparc_load_result is None:
            return
        render_images(
            self._model.sparc_load_result,
            self._view.panel_image_editing,
            self._is_split_screen,
            exposure=self._exposure,
        )

    def _on_exposure_changed(self, factor):
        self._exposure = factor
        self._render_current_images()

    def _on_paired_roi_drawing_changed(self, enabled):
        self._paired_roi_drawing = bool(enabled)
        if enabled and self._split_pair_color_name is not None:
            # Enabling paired draws completes any unfinished one-eye color cycle.
            self.color_manager.consume(self._split_pair_color_name)
            self._split_pair_color_name = None
            self._split_pair_eyes = set()
            self._refresh_swatch()
        if self._is_split_screen:
            mode = "both eyes" if enabled else "the active eye only"
            self._view.show_status_message(
                f"Split-screen draw/delete targets {mode}"
            )

    def _on_rgb_bands_changed(self, r, g, b, use_dcs, camera):
        self._render_current_images()

    # ------------------------------------------------------------------
    # Presets and split screen
    # ------------------------------------------------------------------

    def _apply_stretch_mode(self, mode: str):
        """Apply RGB or DCS to all active canvases using the current instrument's presets."""
        if self._model.sparc_load_result is None:
            return
        instrument = self._model.instrument
        presets = INSTRUMENT_PRESETS.get(instrument, INSTRUMENT_PRESETS['ZCAM'])
        cameras = (['single', 'left', 'right'] if self._is_split_screen
                   else ['single'])
        for camera in cameras:
            if camera == 'single':
                side = 'left' if instrument == 'PCAM' else 'right'
            else:
                side = camera
            bands = presets[side][mode]
            self._view.panel_image_editing.apply_preset(
                camera, bands['r'], bands['g'], bands['b'], bands['dcs']
            )

    def _on_split_screen_exit_requested(self):
        self._view.panel_image_editing.confirm_split_screen_exit()

    def _on_split_screen_toggled(self, is_split):
        self._is_split_screen = is_split

        if not is_split and self._split_pair_color_name is not None:
            # Leaving split view completes an intentional one-eye cycle.
            self.color_manager.consume(self._split_pair_color_name)
            self._split_pair_color_name = None
            self._split_pair_eyes = set()
            self._refresh_swatch()

        if self._model.sparc_load_result is not None:
            # Switching presentation modes must not synchronize ROI geometry.
            # Split-screen edits are authoritative and exports consume the
            # stored left/right rectangles exactly as they stand.
            self._render_current_images()
            self._view.panel_image_editing.set_rois(
                self._current_rois_data, self._canvas_colors(), self._current_color_names
            )
            if self._selection_data:
                self._view.panel_spectral_view.plot_roi_spectra(
                    self._selection_data, self._selection_colors
                )
            if not is_split:
                self._view.panel_image_editing.set_crop_enabled(True)
        self._view.show_status_message(
            (("Split screen: draw/delete targets both eyes"
              if self._paired_roi_drawing
              else "Split screen: draw/delete targets the active eye only")
             if is_split else "Single screen: drawing creates paired regions")
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _delete_all_rois(self):
        self._current_rois_data   = []
        self._current_colors      = []
        self._current_color_names = []
        self._selection_data      = []
        self._selection_colors    = []
        self._selection_names     = []
        self._split_pair_color_name = None
        self._split_pair_eyes       = set()
        self.color_manager.reset()
        self._update_roi_view()
        self._view.set_export_enabled(False)
        self._view.show_status_message("All ROIs deleted")

    def _get_instrument_config(self):
        load_result = self._model.sparc_load_result
        return scene_callbacks.get_instrument_config_for_scene(load_result)
