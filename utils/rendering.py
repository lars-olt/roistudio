"""Image rendering utilities - band stretching and pixmap generation."""

import numpy as np
from marslab.imgops.imgutils import enhance_color
from utils.converters import numpy_to_pixmap

# Cache exposure-independent color stretches by canvas slot.
_rgb_stretch_cache = {}


def bands_to_pixmap(r_arr, g_arr, b_arr, use_dcs=False, exposure=1.0,
                    cache_slot=None, cache_key=None):
    """Render three bands using color enhancement or decorrelation stretch.

    Exposure applies only to color enhancement. 'cache_slot' and 'cache_key'
    reuse its exposure-independent intermediate result.
    """
    # Strip masks so downstream NumPy calls (percentile, isfinite) operate on plain arrays.
    r_arr = np.ma.filled(r_arr, np.nan) if np.ma.is_masked(r_arr) else np.asarray(r_arr)
    g_arr = np.ma.filled(g_arr, np.nan) if np.ma.is_masked(g_arr) else np.asarray(g_arr)
    b_arr = np.ma.filled(b_arr, np.nan) if np.ma.is_masked(b_arr) else np.asarray(b_arr)

    if use_dcs:
        return _dcs_pixmap(r_arr, g_arr, b_arr)

    stretched = None
    if cache_slot is not None:
        hit = _rgb_stretch_cache.get(cache_slot)
        if hit is not None and hit[0] == cache_key:
            stretched = hit[1]

    if stretched is None:
        rgb       = np.stack([r_arr, g_arr, b_arr], axis=-1).astype(float)
        result    = enhance_color(np.ma.masked_invalid(rgb), bounds=(0, 1), stretch=0.1)
        stretched = np.ma.filled(result, 0).astype(np.float32)
        if cache_slot is not None:
            _rgb_stretch_cache[cache_slot] = (cache_key, stretched)

    return numpy_to_pixmap(
        np.ascontiguousarray(np.clip(stretched * (exposure * 255), 0, 255), dtype=np.uint8)
    )


def make_pixmap(r_band, g_band, b_band, base_bands, use_dcs=False, exposure=1.0,
                cache_slot=None, cache_key=None):
    """Return a QPixmap for the given band names, or None if any band is missing."""
    if not all(b in base_bands for b in (r_band, g_band, b_band)):
        return None
    return bands_to_pixmap(base_bands[r_band], base_bands[g_band], base_bands[b_band],
                           use_dcs, exposure, cache_slot, cache_key)


def render_images(load_result, panel, is_split_screen, exposure=1.0):
    """Render the selected bands into the active canvas or canvases."""
    base_bands = load_result.get('base_bands', {})
    scene_id   = load_result.get('id')

    if is_split_screen:
        r_r, g_r, b_r, dcs_r = panel.get_selected_bands('right')
        r_l, g_l, b_l, dcs_l = panel.get_selected_bands('left')

        right_pixmap = (make_pixmap(r_r, g_r, b_r, base_bands, dcs_r, exposure,
                                    cache_slot='right', cache_key=(scene_id, r_r, g_r, b_r))
                        if r_r and g_r and b_r else None)
        left_pixmap  = (make_pixmap(r_l, g_l, b_l, base_bands, dcs_l, exposure,
                                    cache_slot='left', cache_key=(scene_id, r_l, g_l, b_l))
                        if r_l and g_l and b_l else None)

        right_pixmap = right_pixmap or numpy_to_pixmap(load_result.get('right_rgb_img', load_result['rgb_img']))
        left_pixmap  = left_pixmap  or numpy_to_pixmap(load_result.get('left_rgb_img',  load_result['rgb_img']))
        panel.canvas_container.set_camera_images(left_pixmap, right_pixmap)
    else:
        r, g, b, dcs = panel.get_selected_bands('single')
        pixmap = (make_pixmap(r, g, b, base_bands, dcs, exposure,
                              cache_slot='single', cache_key=(scene_id, r, g, b))
                  if r and g and b else None)
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
