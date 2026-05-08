"""ROI create, update, and delete handling."""

import cv2
import numpy as np
from sparc.utils.geometry import right_rect_to_left_inscribed


def on_roi_created(rect, camera, load_result, instrument_config, sparc_controller, has_dual_cubes):
    """Build a new roi_data dict from a freshly drawn rectangle."""
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

    return {
        'roi':        right_rect,
        'right_rect': right_rect,
        'left_rect':  left_rect,
        'mineral':    'Manual ROI',
        **spec_data,
    }


def on_roi_changed(roi_index, new_rect, camera, existing_roi_data,
                   load_result, instrument_config, sparc_controller, has_dual_cubes):
    """Recompute spectra after a rectangle has been moved or resized."""
    roi_data = existing_roi_data[roi_index]

    if has_dual_cubes:
        if camera == 'right':
            right_rect = tuple(new_rect)
            left_rect  = roi_data.get('left_rect', roi_data['roi'])
        elif camera == 'left':
            left_rect  = tuple(new_rect)
            right_rect = roi_data['right_rect']
        else:
            right_rect = tuple(new_rect)
            left_rect  = _apply_rect_delta(
                roi_data.get('left_rect', roi_data['roi']),
                roi_data['roi'], new_rect,
            )
        spec_data = sparc_controller.update_roi_spectrum_dual(
            load_result, left_rect, right_rect, instrument_config
        )
    else:
        right_rect = left_rect = tuple(new_rect)
        spec_data  = sparc_controller.update_roi_spectrum(
            load_result['cube'], new_rect, instrument_config
        )

    return {
        **roi_data,
        'roi':        right_rect,
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


def _apply_rect_delta(left_rect, old_right_rect, new_right_rect):
    """Propagate a move/resize delta from the right rect to the left rect."""
    ox, oy, ow, oh = old_right_rect
    nx, ny, nw, nh = new_right_rect
    lx, ly, lw, lh = left_rect
    return (
        lx + nx - ox,
        ly + ny - oy,
        lw * (nw / ow if ow > 0 else 1.0),
        lh * (nh / oh if oh > 0 else 1.0),
    )