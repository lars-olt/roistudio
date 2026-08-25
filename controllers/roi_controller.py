"""ROI create, update, and delete handling."""

import cv2
import numpy as np
from sparc.utils.geometry import right_rect_to_left_inscribed

from utils.converters import snap_rect


def _image_bounds(load_result):
    """(W, H) of the scene frame, for clamping derived rects."""
    H, W = load_result['rgb_img'].shape[:2]
    return (W, H)


def _derive_left(right_rect, homography, bounds):
    """Left-camera rect for a right rect, snapped to the pixel grid."""
    if homography is None:
        return right_rect
    left = right_rect_to_left_inscribed(tuple(right_rect), homography)
    if left is None:
        return right_rect
    return snap_rect(*left, bounds=bounds)


def _derive_right(left_rect, homography, bounds):
    """Right-camera rect for a left rect, snapped to the pixel grid."""
    if homography is None:
        return left_rect
    return snap_rect(*_left_rect_to_right(left_rect, homography), bounds=bounds)


def canvas_rect(roi_data, instrument):
    """Rectangle shown in single-screen mode for the instrument's primary eye."""
    key = 'left_rect' if str(instrument).strip().upper() == 'PCAM' else 'right_rect'
    return roi_data.get(key)


def spectrum_data(left_rect, right_rect, load_result, instrument_config,
                  sparc_controller, has_dual_cubes):
    if has_dual_cubes:
        return sparc_controller.update_roi_spectrum_dual(
            load_result, left_rect, right_rect, instrument_config
        )

    instrument = load_result.get('instrument', 'ZCAM').strip().upper()
    rect = left_rect if instrument == 'PCAM' else right_rect
    if rect is None:
        # A one-cube scene cannot provide a spectrum for its missing primary eye.
        return {
            'spectrum': [], 'std': [], 'wavelengths': [],
            'bayer_spectrum': [], 'bayer_std': [], 'bayer_wavelengths': [],
            'left_spectrum': [], 'left_std': [], 'left_wavelengths': [],
            'right_spectrum': [], 'right_std': [], 'right_wavelengths': [],
        }
    data = dict(sparc_controller.update_selection_spectrum(
        load_result['cube'], rect, instrument_config
    ))
    # Geometry belongs to the ROI model; the single-cube helper returns legacy
    # geometry keys that must not recreate an absent eye.
    for key in ('roi', 'left_rect', 'right_rect'):
        data.pop(key, None)
    return data


def on_roi_created(rect, camera, load_result, instrument_config,
                   sparc_controller, has_dual_cubes, paired_draw=None):
    """Build a new ROI data dictionary from a freshly drawn rectangle."""
    instrument = load_result.get('instrument', 'ZCAM').strip().upper()
    if paired_draw is None:
        paired_draw = camera == 'single'
    else:
        paired_draw = bool(paired_draw)

    # single screen draws in the displayed camera - left for PCAM, right for ZCAM
    if camera == 'single':
        paired_draw = True
        camera = 'left' if instrument == 'PCAM' else 'right'

    if has_dual_cubes:
        homography = load_result.get('homography_matrix')
        bounds     = _image_bounds(load_result)
        if paired_draw and camera == 'left':
            left_rect  = tuple(rect)
            right_rect = _derive_right(left_rect, homography, bounds)
        elif paired_draw:
            right_rect = tuple(rect)
            left_rect  = _derive_left(right_rect, homography, bounds)
        elif camera == 'left':
            left_rect, right_rect = tuple(rect), None
        else:
            left_rect, right_rect = None, tuple(rect)
        spec_data = spectrum_data(
            left_rect, right_rect, load_result, instrument_config,
            sparc_controller, has_dual_cubes,
        )
    else:
        if paired_draw:
            right_rect = left_rect = tuple(rect)
        elif camera == 'left':
            left_rect, right_rect = tuple(rect), None
        else:
            left_rect, right_rect = None, tuple(rect)
        spec_data = spectrum_data(
            left_rect, right_rect, load_result, instrument_config,
            sparc_controller, has_dual_cubes,
        )

    roi_geometry = {'left_rect': left_rect, 'right_rect': right_rect}
    displayed_rect = canvas_rect(roi_geometry, instrument)

    return {
        'roi':        displayed_rect,
        'right_rect': right_rect,
        'left_rect':  left_rect,
        'mineral':    'Manual ROI',
        **spec_data,
    }


def on_roi_changed(roi_index, new_rect, camera, existing_roi_data,
                   load_result, instrument_config, sparc_controller, has_dual_cubes):
    """Recompute spectra after a rectangle has been moved or resized."""
    roi_data   = existing_roi_data[roi_index]
    instrument = load_result.get('instrument', 'ZCAM').strip().upper()
    homography = load_result.get('homography_matrix') if has_dual_cubes else None
    bounds     = _image_bounds(load_result)

    # single screen edits the displayed camera - left for PCAM, right for ZCAM.
    # The opposite camera's rect is derived from the edit via the homography.
    if camera == 'single':
        if instrument == 'PCAM':
            left_rect  = tuple(new_rect)
            right_rect = roi_data.get('right_rect')
            if right_rect is not None and homography is not None:
                right_rect = _derive_right(left_rect, homography, bounds)
        else:
            right_rect = tuple(new_rect)
            left_rect  = roi_data.get('left_rect')
            if left_rect is not None and homography is not None:
                left_rect = _derive_left(right_rect, homography, bounds)
    # split screen edits one camera directly - the other side keeps its stored rect.
    elif camera == 'left':
        left_rect  = tuple(new_rect)
        right_rect = roi_data.get('right_rect')
    else:
        right_rect = tuple(new_rect)
        left_rect  = roi_data.get('left_rect')

    spec_data = spectrum_data(
        left_rect, right_rect, load_result, instrument_config,
        sparc_controller, has_dual_cubes,
    )

    roi_geometry = {'left_rect': left_rect, 'right_rect': right_rect}
    displayed_rect = canvas_rect(roi_geometry, instrument)

    return {
        **roi_data,
        'roi':        displayed_rect,
        'right_rect': right_rect,
        'left_rect':  left_rect,
        **spec_data,
    }


def _left_rect_to_right(left_rect, homography_matrix):
    if homography_matrix is None:
        return left_rect
    x, y, w, h = left_rect
    corners = np.array([[x, y], [x+w, y], [x+w, y+h], [x, y+h]], dtype=np.float32)
    rc = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), homography_matrix).reshape(-1, 2)
    rx, ry = float(rc[:, 0].min()), float(rc[:, 1].min())
    return (rx, ry, float(rc[:, 0].max()) - rx, float(rc[:, 1].max()) - ry)
