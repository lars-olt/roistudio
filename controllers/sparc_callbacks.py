"""SPARC pipeline trigger and result handling."""

import numpy as np
from sparc.core.constants import get_instrument_config


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

    use_dcs = params.get('segment', {}).get('use_dcs', False)
    if use_dcs:
        from sparc.data.loading import make_dcs_rgb
        load_result = dict(load_result)
        load_result['rgb_img'] = make_dcs_rgb(load_result)

    # check for a pre-segmented NPZ file matching the current DCS setting
    from pathlib import Path
    scene_id = model.sparc_load_result.get('id', '')
    suffix   = '_dcs' if use_dcs else ''
    npz_path = Path(folder_path) / f"{scene_id}{suffix}.npz"

    presegmented = None
    if npz_path.exists():
        try:
            presegmented = np.load(str(npz_path))['segments']
            if crop_rect is not None:
                x, y, w, h  = (int(v) for v in crop_rect)
                presegmented = presegmented[y:y+h, x:x+w]
            dcs_label = '(DCS, pre-segmented)' if use_dcs else '(pre-segmented)'
            view.show_status_message(f"Starting SPARC pipeline {dcs_label}...")
        except Exception as e:
            presegmented = None
            view.show_status_message(f"Warning: could not load {npz_path.name}: {e}")

    if presegmented is None:
        dcs_label = ' (DCS)' if use_dcs else ''
        view.show_status_message(f"Starting SPARC pipeline{dcs_label}...")

    sparc_controller.start_sparc(
        sam_path, folder_path, seq_id, obs_ix, instrument,
        params       = params,
        load_result  = load_result,
        presegmented = presegmented,
    )


def _apply_crop(load_result: dict, crop_rect: tuple) -> dict:
    """Crop scene arrays and translate the homography into the cropped frame."""
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

    # derive the crop-adjusted homography from the original via coordinate translation.
    # if H maps right→left in full-frame coords, then in crop coords:
    #   H_crop = T_inv @ H @ T
    # where T shifts from crop coords back to full-frame coords.
    orig_H = load_result.get('homography_matrix')
    if orig_H is not None:
        T     = np.array([[1, 0, x], [0, 1, y], [0, 0, 1]], dtype=np.float64)
        T_inv = np.array([[1, 0, -x], [0, 1, -y], [0, 0, 1]], dtype=np.float64)
        result['homography_matrix'] = T_inv @ orig_H @ T

    return result


def on_sparc_complete(result, model, view, algorithm_controller,
                      spectrum_controller, color_manager):
    """Unpack a SparcResult and push ROIs and spectra to the view."""
    if result.final_rois is None or len(result.final_rois) == 0:
        view.show_status_message("SPARC found no ROIs")
        view.stop_loading()
        return None

    instrument_config = get_instrument_config(result.instrument)
    instrument_config['wavelengths'] = result.wavelengths

    rois_data   = algorithm_controller.extract_roi_data(result, instrument_config)
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
            spec_data = spectrum_controller.update_roi_spectrum_dual(
                load_result, roi['left_rect'], roi['right_rect'], instrument_config
            )
            rois_data[i] = {**roi, **spec_data}

    if result.instrument == 'PCAM':
        for roi in rois_data:
            roi['roi'] = roi['left_rect']

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


def _has_dual_cubes(load_result):
    return (load_result is not None
            and 'left_cube'          in load_result
            and 'right_cube'         in load_result
            and 'merged_band_recipe' in load_result)
