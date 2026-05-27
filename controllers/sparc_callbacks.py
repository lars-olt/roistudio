"""SPARC pipeline trigger and result handling."""

import traceback
from sparc.core.constants import get_instrument_config


def get_instrument_config_for_scene(load_result):
    """Build an instrument config, patching in the actual scene wavelengths."""
    instrument = load_result.get('instrument', 'ZCAM') if load_result else 'ZCAM'
    cfg = get_instrument_config(instrument)
    if load_result and hasattr(load_result.get('bandset'), '_sparc_wavelengths'):
        cfg['wavelengths'] = load_result['bandset']._sparc_wavelengths
    return cfg


def run_algorithm(model, view, scene_controller, sparc_controller, current_scene_id, sam_path, params, crop_rect=None):
    if model.sparc_load_result is None:
        view.show_status_message("No scene loaded. Please load a scene first.")
        return
    if not sam_path:
        view.show_status_message("SAM model path not set. Use File > Set SAM Path.")
        return

    scene_info = scene_controller.get_scene_info(current_scene_id)
    if not scene_info:
        view.show_status_message("Error: scene info not found.")
        return

    folder_path, seq_id, obs_ix, instrument = scene_info

    load_result = model.sparc_load_result
    if crop_rect is not None:
        load_result = _apply_crop(load_result, crop_rect)
        view.show_status_message("Starting SPARC pipeline (cropped frame)...")
    else:
        view.show_status_message("Starting SPARC pipeline...")

    sparc_controller.start_sparc(
        sam_path, folder_path, seq_id, obs_ix, instrument,
        params      = params,
        load_result = load_result,
    )


def _apply_crop(load_result: dict, crop_rect: tuple) -> dict:
    """
    Return a shallow-copied load_result with all cubes and the rgb_img
    cropped to crop_rect, and the homography recomputed for the new frame.
    """
    import copy
    import cv2
    import numpy as np
    from sparc.data.loading import compute_homography

    x, y, w, h = (int(v) for v in crop_rect)
    result = dict(load_result)

    def _crop_cube(cube):
        return cube[:, y:y+h, x:x+w] if cube is not None else None

    result['cube']              = _crop_cube(load_result['cube'])
    result['left_cube']         = _crop_cube(load_result['left_cube'])
    result['right_cube']        = _crop_cube(load_result['right_cube'])
    result['left_cube_aligned'] = _crop_cube(load_result['left_cube_aligned'])
    result['rgb_img']           = load_result['rgb_img'][y:y+h, x:x+w]
    result['left_rgb_img']      = load_result['left_rgb_img'][y:y+h, x:x+w]
    result['right_rgb_img']     = load_result['right_rgb_img'][y:y+h, x:x+w]
    result['homography_mask']   = load_result['homography_mask'][y:y+h, x:x+w]

    # crop base_bands too - these are used by masking when pixmaps are applied
    result['base_bands'] = {
        k: v[y:y+h, x:x+w] for k, v in load_result['base_bands'].items()
    }

    # recompute homography on the cropped shared bands
    from sparc.core.constants import SHARED_BANDS
    instrument = load_result.get('instrument', 'ZCAM')
    if instrument == 'ZCAM':
        l_key, r_key = SHARED_BANDS['L'], SHARED_BANDS['R']
    else:
        l_key, r_key = 'L7', 'R1'

    l_band = result['base_bands'].get(l_key)
    r_band = result['base_bands'].get(r_key)
    if l_band is not None and r_band is not None:
        try:
            H = compute_homography(
                np.where(np.isfinite(l_band), l_band, 0.0),
                np.where(np.isfinite(r_band), r_band, 0.0),
            )
            result['homography_matrix'] = H
        except Exception:
            pass  # keep original homography if recompute fails

    return result


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

    # shift ROI coords from cropped space back to full-frame canvas coords
    crop_rect = view.panel_image_editing.get_crop_rect()
    if crop_rect is not None:
        cx, cy = crop_rect[0], crop_rect[1]
        for roi in rois_data:
            for key in ('roi', 'right_rect', 'left_rect'):
                if key in roi and roi[key]:
                    x, y, w, h = roi[key]
                    roi[key] = (x + cx, y + cy, w, h)

    if _has_dual_cubes(load_result):
        for i, roi in enumerate(rois_data):
            spec_data = sparc_controller.update_roi_spectrum_dual(
                load_result, roi['left_rect'], roi['right_rect'], instrument_config
            )
            rois_data[i] = {**roi, **spec_data}

    colors, names = [], []
    for _ in rois_data:
        color, name = color_manager.next()
        colors.append(color)
        names.append(name)

    view.stop_loading()
    view.show_status_message(f"SPARC complete: {len(result.final_rois)} ROIs found")

    return rois_data, colors, names


def on_sparc_error(error_msg, view):
    view.stop_loading()
    view.show_status_message(f"Error running SPARC: {error_msg}")
    traceback.print_exc()


def _has_dual_cubes(load_result):
    return (load_result is not None
            and 'left_cube'          in load_result
            and 'right_cube'         in load_result
            and 'merged_band_recipe' in load_result)