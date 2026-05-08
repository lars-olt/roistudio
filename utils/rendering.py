"""Image rendering utilities - band stretching and pixmap generation."""

import numpy as np
from marslab.imgops.imgutils import enhance_color
from utils.converters import numpy_to_pixmap


def bands_to_pixmap(r_arr, g_arr, b_arr, use_dcs=False):
    """Stretch three band arrays to a uint8 RGB QPixmap.

    DCS off: enhance_color, matching the default pipeline image.
    DCS on: decorrelation stretch (Gillespie et al. 1986) with per-channel
    0.5-99.5 percentile clip.
    """
    if use_dcs:
        return _dcs_pixmap(r_arr, g_arr, b_arr)

    rgb    = np.stack([r_arr, g_arr, b_arr], axis=-1).astype(float)
    result = enhance_color(np.ma.masked_invalid(rgb), bounds=(0, 1), stretch=0.1)
    return numpy_to_pixmap(
        np.ascontiguousarray(np.ma.filled(result, 0) * 255, dtype=np.uint8)
    )


def make_pixmap(r_band, g_band, b_band, base_bands, use_dcs=False):
    """Return a QPixmap for the given band names, or None if any band is missing."""
    if not all(b in base_bands for b in (r_band, g_band, b_band)):
        return None
    return bands_to_pixmap(base_bands[r_band], base_bands[g_band], base_bands[b_band], use_dcs)


def render_images(load_result, panel, is_split_screen):
    """Push the current band selection as pixmaps to the canvas.

    Called on scene load, band change, and split screen toggle.
    """
    base_bands = load_result.get('base_bands', {})

    if is_split_screen:
        r_r, g_r, b_r, dcs_r = panel.get_selected_bands('right')
        r_l, g_l, b_l, dcs_l = panel.get_selected_bands('left')

        right_pixmap = make_pixmap(r_r, g_r, b_r, base_bands, dcs_r) if r_r and g_r and b_r else None
        left_pixmap  = make_pixmap(r_l, g_l, b_l, base_bands, dcs_l) if r_l and g_l and b_l else None

        right_pixmap = right_pixmap or numpy_to_pixmap(load_result.get('right_rgb_img', load_result['rgb_img']))
        left_pixmap  = left_pixmap  or numpy_to_pixmap(load_result.get('left_rgb_img',  load_result['rgb_img']))
        panel.canvas_container.set_camera_images(left_pixmap, right_pixmap)
    else:
        r, g, b, dcs = panel.get_selected_bands('single')
        pixmap = make_pixmap(r, g, b, base_bands, dcs) if r and g and b else None
        panel.set_image(pixmap or numpy_to_pixmap(load_result['rgb_img']))


def _dcs_pixmap(r_arr, g_arr, b_arr):
    """Decorrelation stretch - isolates spectral variation by rotating into eigenspace."""
    H, W    = r_arr.shape
    invalid = ~np.isfinite(r_arr) | ~np.isfinite(g_arr) | ~np.isfinite(b_arr)

    r = np.where(invalid, 0.0, r_arr).astype(np.float32)
    g = np.where(invalid, 0.0, g_arr).astype(np.float32)
    b = np.where(invalid, 0.0, b_arr).astype(np.float32)

    vecs  = np.stack([r, g, b], axis=-1).reshape(-1, 3)
    valid = vecs[~invalid.ravel()]
    if valid.shape[0] < 4:
        return numpy_to_pixmap(np.zeros((H, W, 3), dtype=np.uint8))

    cov        = np.cov(valid.T).astype(np.float32)
    eigvals, V = np.linalg.eig(cov)
    T          = (V @ np.diag(1.0 / np.sqrt(np.abs(eigvals))) @ V.T).astype(np.float32)
    means      = valid.mean(axis=0)
    dcs        = ((vecs - means) @ T + means + (means - means @ T)).reshape(H, W, 3)

    result   = np.zeros((H, W, 3), dtype=np.float32)
    valid_2d = ~invalid
    for c in range(3):
        ch     = dcs[:, :, c]
        v      = ch[valid_2d]
        if v.size == 0:
            continue
        lo, hi = np.percentile(v, [0.5, 99.5])
        result[:, :, c] = np.clip((ch - lo) / (hi - lo) if hi > lo else ch, 0.0, 1.0)

    result[invalid] = 0.0
    return numpy_to_pixmap(np.ascontiguousarray(result * 255, dtype=np.uint8))