"""SPARC pipeline trigger and result handling."""

import numpy as np
from asdf_settings import rapidlooks
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
    try:
        algorithm_rect = _algorithm_crop_rect(load_result, crop_rect)
    except ValueError as e:
        view.show_status_message(str(e))
        return
    load_result = _apply_crop(load_result, algorithm_rect)

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
            with np.load(str(npz_path)) as cached:
                presegmented = _crop_presegmented(
                    cached['segments'], model.sparc_load_result, algorithm_rect,
                )
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


def _algorithm_crop_rect(load_result, crop_rect=None):
    """Intersect the user's full-image crop with ZCAM's algorithm-only margins."""
    height, width = load_result['rgb_img'].shape[:2]
    x, y, end_x, end_y = 0, 0, width, height
    if (load_result.get('instrument') in {'ZCAM', 'MCZ'}
            and load_result.get('sensor_crop') == (0, 0, 0, 0)):
        left, right, top, bottom = map(int, rapidlooks.CROP_SETTINGS['crop'])
        x, y, end_x, end_y = left, top, width - right, height - bottom
    if crop_rect is not None:
        cx, cy, cw, ch = map(int, crop_rect)
        x, y = max(x, cx), max(y, cy)
        end_x, end_y = min(end_x, cx + cw), min(end_y, cy + ch)
    if end_x <= x or end_y <= y:
        raise ValueError('The selected crop contains no pixels inside the algorithm margins.')
    return x, y, end_x - x, end_y - y


def _crop_presegmented(segments, load_result, crop_rect):
    """Accept caches in either full-image or historical SPARC-trimmed space."""
    shape = load_result['rgb_img'].shape[:2]
    origin_x, origin_y = 0, 0
    if segments.shape != shape:
        edge_x, edge_y, width, height = _algorithm_crop_rect(load_result)
        if segments.shape != (height, width):
            raise ValueError('Cached segments do not match the scene dimensions')
        origin_x, origin_y = edge_x, edge_y
    x, y, width, height = crop_rect
    x, y = x - origin_x, y - origin_y
    return segments[y:y+height, x:x+width].copy()


def _apply_crop(load_result: dict, crop_rect: tuple) -> dict:
    """Copy the algorithm region and translate its homography; retain its origin."""

    x, y, w, h = (int(v) for v in crop_rect)
    result = dict(load_result)

    def _crop_cube(cube):
        if cube is None:
            return None
        return cube[:, y:y+h, x:x+w].copy() if cube.ndim == 3 else cube.copy()

    for key in ('cube', 'left_cube', 'right_cube', 'left_cube_aligned'):
        result[key] = _crop_cube(load_result.get(key))
    for key in ('rgb_img', 'left_rgb_img', 'right_rgb_img', 'homography_mask'):
        array = load_result.get(key)
        result[key] = array[y:y+h, x:x+w].copy() if array is not None else None
    result['roi_origin'] = (x, y)
    left, right, top, bottom = load_result.get('sensor_crop', (0, 0, 0, 0))
    full_h, full_w = load_result['rgb_img'].shape[:2]
    result['sensor_crop'] = (left + x, right + full_w - x - w,
                             top + y, bottom + full_h - y - h)

    # crop base_bands too - these are used by masking when pixmaps are applied
    result['base_bands'] = {
        k: v[y:y+h, x:x+w].copy() for k, v in load_result['base_bands'].items()
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

    # Use the crop captured by this run, even if the UI crop has since changed.
    run_load_result = result._load_result or {}
    cx, cy = run_load_result.get('roi_origin', (0, 0))
    for roi in rois_data:
        for key in ('roi', 'right_rect', 'left_rect'):
            if roi.get(key) is not None:
                x, y, w, h = roi[key]
                if w > 0 and h > 0:
                    roi[key] = (x + cx, y + cy, w, h)
        mask = np.zeros(load_result['rgb_img'].shape[:2], dtype=bool)
        if roi.get('roi') is not None:
            x, y, w, h = roi['roi']
            mask[y:y+h, x:x+w] = True
        roi['mask'] = mask

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
