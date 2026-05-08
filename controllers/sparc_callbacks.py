"""SPARC pipeline trigger and result handling."""

import numpy as np
from sparc.core.constants import get_instrument_config


def get_instrument_config_for_scene(load_result):
    """Build an instrument config, patching in the actual scene wavelengths."""
    instrument = load_result.get('instrument', 'ZCAM') if load_result else 'ZCAM'
    cfg = get_instrument_config(instrument)
    if load_result and hasattr(load_result.get('bandset'), '_sparc_wavelengths'):
        cfg['wavelengths'] = load_result['bandset']._sparc_wavelengths
    return cfg


def run_algorithm(model, view, scene_controller, sparc_controller, current_scene_id, sam_path, params):
    if model.sparc_load_result is None:
        view.show_status_message("No scene loaded. Please load a scene first.")
        return
    if not sam_path:
        view.show_status_message("SAM model path not set. Use File - Set SAM Path.")
        return

    scene_info = scene_controller.get_scene_info(current_scene_id)
    if not scene_info:
        view.show_status_message("Error: scene info not found.")
        return

    folder_path, seq_id, obs_ix, instrument = scene_info
    view.show_status_message("Starting SPARC pipeline...")
    sparc_controller.start_sparc(
        sam_path, folder_path, seq_id, obs_ix, instrument,
        params      = params,
        load_result = model.sparc_load_result,
    )


def on_sparc_complete(result, model, view, sparc_controller, color_manager):
    """Unpack a SparcResult and push ROIs and spectra to the view."""
    if result.final_rois is None or len(result.final_rois) == 0:
        view.show_status_message("SPARC found no ROIs")
        view.stop_loading()
        return None

    instrument_config = get_instrument_config(result.instrument)
    instrument_config['wavelengths'] = result.wavelengths

    rois_data   = sparc_controller.extract_roi_data(result, instrument_config)
    load_result = model.sparc_load_result

    has_dual = _has_dual_cubes(load_result)
    if has_dual:
        for i, roi in enumerate(rois_data):
            spec_data = sparc_controller.update_roi_spectrum_dual(
                load_result, roi['left_rect'], roi['right_rect'], instrument_config
            )
            rois_data[i] = {**roi, **spec_data}

    color_manager.reset()
    colors = []
    names  = []
    for _ in rois_data:
        color, name = color_manager.next()
        colors.append(color)
        names.append(name)

    view.panel_image_editing.set_rois(rois_data, colors, names)
    view.panel_spectral_view.plot_roi_spectra(rois_data, colors)
    view.action_export_sel.setEnabled(True)
    view.stop_loading()
    view.show_status_message(f"SPARC complete: {len(result.final_rois)} ROIs found")

    return rois_data, colors, names


def on_sparc_error(error_msg, view):
    view.stop_loading()
    view.show_status_message(f"Error running SPARC: {error_msg}")
    import traceback; traceback.print_exc()


def _has_dual_cubes(load_result):
    return (load_result is not None
            and 'left_cube' in load_result
            and 'right_cube' in load_result
            and 'merged_band_recipe' in load_result)