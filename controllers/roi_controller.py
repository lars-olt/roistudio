"""ROI create, update, and delete handling."""

import cv2
import numpy as np
from sparc.utils.geometry import right_rect_to_left_inscribed


def on_roi_created(rect, camera, load_result, instrument_config, sparc_controller, has_dual_cubes):
    """Build a new roi_data dict from a freshly drawn rectangle."""
    instrument = load_result.get('instrument', 'ZCAM')

    # single screen draws in the displayed camera - left for PCAM, right for ZCAM
    if camera == 'single':
        camera = 'left' if instrument == 'PCAM' else 'right'

    if has_dual_cubes:
        homography = load_result.get('homography_matrix')
        if camera == 'left':
            left_rect  = tuple(rect)
            right_rect = _left_rect_to_right(left_rect, homography) or left_rect
        else:
            right_rect = tuple(rect)
            left_rect  = (right_rect_to_left_inscribed(right_rect, homography)
                          if homography is not None else right_rect) or right_rect
        spec_data = sparc_controller.update_roi_spectrum_dual(
            load_result, left_rect, right_rect, instrument_config
        )
    else:
        right_rect = left_rect = tuple(rect)
        spec_data  = sparc_controller.update_roi_spectrum(
            load_result['cube'], rect, instrument_config
        )

    canvas_rect = left_rect if instrument == 'PCAM' else right_rect

    return {
        'roi':        canvas_rect,
        'right_rect': right_rect,
        'left_rect':  left_rect,
        'mineral':    'Manual ROI',
        **spec_data,
    }


def on_roi_changed(roi_index, new_rect, camera, existing_roi_data,
                   load_result, instrument_config, sparc_controller, has_dual_cubes):
    """Recompute spectra after a rectangle has been moved or resized."""
    roi_data   = existing_roi_data[roi_index]
    instrument = load_result.get('instrument', 'ZCAM')
    homography = load_result.get('homography_matrix') if has_dual_cubes else None

    # single screen edits the displayed camera - left for PCAM, right for ZCAM.
    # The opposite camera's rect is derived from the edit via the homography.
    if camera == 'single':
        if instrument == 'PCAM':
            left_rect  = tuple(new_rect)
            right_rect = _left_rect_to_right(left_rect, homography) or roi_data['right_rect']
        else:
            right_rect = tuple(new_rect)
            left_rect  = (right_rect_to_left_inscribed(right_rect, homography)
                          if homography is not None else right_rect) or roi_data.get('left_rect', right_rect)
    # split screen edits one camera directly - the other side keeps its stored rect.
    elif camera == 'left':
        left_rect  = tuple(new_rect)
        right_rect = roi_data['right_rect']
    else:
        right_rect = tuple(new_rect)
        left_rect  = roi_data.get('left_rect', roi_data['roi'])

    if has_dual_cubes:
        spec_data = sparc_controller.update_roi_spectrum_dual(
            load_result, left_rect, right_rect, instrument_config
        )
    else:
        spec_data = sparc_controller.update_roi_spectrum(
            load_result['cube'], new_rect, instrument_config
        )

    canvas_rect = left_rect if instrument == 'PCAM' else right_rect

    return {
        **roi_data,
        'roi':        canvas_rect,
        'right_rect': right_rect,
        'left_rect':  left_rect,
        **spec_data,
    }


def sync_left_rois(rois_data, homography):
    """Recompute left_rect for every ROI from its right_rect via the homography.

    Called when leaving split screen so both sides are back in sync.
    """
    for roi in rois_data:
        right_rect   = roi['right_rect']
        left_rect    = (right_rect_to_left_inscribed(right_rect, homography)
                        if homography is not None else right_rect) or right_rect
        roi['left_rect'] = left_rect


def _left_rect_to_right(left_rect, homography_matrix):
    if homography_matrix is None:
        return left_rect
    x, y, w, h = left_rect
    corners = np.array([[x, y], [x+w, y], [x+w, y+h], [x, y+h]], dtype=np.float32)
    rc = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), homography_matrix).reshape(-1, 2)
    rx, ry = float(rc[:, 0].min()), float(rc[:, 1].min())
    return (rx, ry, float(rc[:, 0].max()) - rx, float(rc[:, 1].max()) - ry)