"""SEL file export and import."""

import traceback
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from asdf_settings import rapidlooks
from marslab.imgops.imgutils import enhance_color
from marslab.compat.mertools import MERSPECT_M20_COLOR_MAPPINGS
from PyQt5.QtWidgets import QFileDialog
from sparc.visualization.plotting import plot_spectra_with_error
from sparc.utils.sel_writer import (
    export_sel as _write_sel,
    read_sel,
    filenames_from_load_result,
)
from utils.converters import hex_to_rgb

# RGB and DCS band triplets per instrument and camera side.
# Mirrors INSTRUMENT_PRESETS in view.py - kept here to avoid a circular import.
_EXPORT_BAND_SETS = {
    'ZCAM': {
        'right': {'RGB': ('R0R', 'R0G', 'R0B'), 'DCS': ('R6',  'R3',  'R1')},
        'left':  {'RGB': ('L0R', 'L0G', 'L0B'), 'DCS': ('L2',  'L5',  'L6')},
    },
    'PCAM': {
        'right': {'RGB': ('R7', 'R5', 'R3'), 'DCS': ('R7', 'R5', 'R3')},
        'left':  {'RGB': ('L4', 'L5', 'L6'), 'DCS': ('L4', 'L5', 'L6')},
    },
}


def export_sel(view, model, rois_data, color_names, color_manager, output_path=None):
    if not rois_data:
        view.show_status_message("No ROIs to export.")
        return

    load_result = model.sparc_load_result
    if load_result is None:
        view.show_status_message("No scene loaded - cannot export SEL.")
        return

    scene_id = load_result.get('id', 'scene')
    if output_path is None:
        output_path, _ = QFileDialog.getSaveFileName(
            view, "Export SEL File", f"{scene_id}.sel", "SEL Files (*.sel);;All Files (*)"
        )
    if not output_path:
        return

    try:
        instrument = load_result.get('instrument', 'ZCAM').strip().upper()
        n_rois     = len(rois_data)
        right_rois = np.array([r['right_rect']                     for r in rois_data], dtype=np.int32)
        left_rois  = np.array([r.get('left_rect', r['right_rect']) for r in rois_data], dtype=np.int32)

        col_off, row_off, full_H, full_W = _sensor_offsets(load_result, instrument)
        if col_off or row_off:
            right_rois = right_rois.copy(); right_rois[:, 0] += col_off; right_rois[:, 1] += row_off
            left_rois  = left_rois.copy();  left_rois[:, 0]  += col_off; left_rois[:, 1]  += row_off

        # Use each ROI's MERSpect color index so colors round-trip correctly in MERSpect.
        label_ids = [color_manager.merspect_index(name) for name in color_names]

        left_names, right_names = filenames_from_load_result(load_result, n_rois)
        _write_sel(
            output_path     = output_path,
            final_rois      = right_rois,
            final_left_rois = left_rois,
            image_shape     = (full_H, full_W),
            left_filenames  = left_names,
            right_filenames = right_names,
            instrument      = instrument,
            label_ids       = label_ids,
        )
        view.show_status_message(f"Exported {n_rois} ROI(s) to {output_path}")

    except Exception as e:
        view.show_status_message(f"Export failed: {e}")
        traceback.print_exc()


def load_sel(view, model, instrument_config, sparc_controller, has_dual_cubes, color_manager):
    """Load ROIs from a .sel file into the current scene."""
    load_result = model.sparc_load_result
    if load_result is None:
        view.show_status_message("No scene loaded - cannot load SEL.")
        return None

    path, _ = QFileDialog.getOpenFileName(
        view, "Load SEL File", "", "SEL Files (*.sel);;All Files (*)"
    )
    if not path:
        return None

    try:
        instrument               = load_result.get('instrument', 'ZCAM').strip().upper()
        right_rois, left_rois, label_ids = read_sel(path, instrument)

        col_off, row_off, _, _ = _sensor_offsets(load_result, instrument)
        if col_off or row_off:
            right_rois = right_rois.copy(); right_rois[:, 0] -= col_off; right_rois[:, 1] -= row_off
            left_rois  = left_rois.copy();  left_rois[:, 0]  -= col_off; left_rois[:, 1]  -= row_off

        index_to_name = {v: k for k, v in color_manager._merspect_indices.items()}

        rois_data, colors, color_names = [], [], []

        for i, (right_rect, left_rect) in enumerate(zip(right_rois, left_rois)):
            right_rect = tuple(int(v) for v in right_rect)
            left_rect  = tuple(int(v) for v in left_rect)

            spec_data = (
                sparc_controller.update_roi_spectrum_dual(
                    load_result, left_rect, right_rect, instrument_config
                ) if has_dual_cubes else
                sparc_controller.update_roi_spectrum(
                    load_result['cube'], right_rect, instrument_config
                )
            )

            label = label_ids[i] if i < len(label_ids) else None
            name  = index_to_name.get(label)
            if name and name in color_manager._merspect_indices:
                color = hex_to_rgb(MERSPECT_M20_COLOR_MAPPINGS[name])
            else:
                color, name = color_manager.next()

            rois_data.append({
                'roi':        right_rect,
                'right_rect': right_rect,
                'left_rect':  left_rect,
                'mineral':    'Loaded ROI',
                **spec_data,
            })
            colors.append(color)
            color_names.append(name)

        color_manager.reset()
        color_manager.reserve(color_names)
        view.show_status_message(f"Loaded {len(rois_data)} ROI(s) from {path}")
        return rois_data, colors, color_names

    except Exception as e:
        view.show_status_message(f"Load SEL failed: {e}")
        traceback.print_exc()
        return None


def export_context(view, model, rois_data, colors, color_names, color_manager):
    """Export a context folder: SEL file + four annotated images + spectra plot."""
    if not rois_data:
        view.show_status_message("No ROIs to export.")
        return

    load_result = model.sparc_load_result
    if load_result is None:
        view.show_status_message("No scene loaded - cannot export context.")
        return

    scene_id   = load_result.get('id', 'scene')
    output_dir, _ = QFileDialog.getSaveFileName(
        view, "Export Context Folder", scene_id, ""
    )
    if not output_dir:
        return

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        instrument  = load_result.get('instrument', 'ZCAM').strip().upper()
        base_bands  = load_result.get('base_bands', {})
        band_sets   = _EXPORT_BAND_SETS.get(instrument, _EXPORT_BAND_SETS['ZCAM'])
        mpl_colors  = [tuple(c / 255.0 for c in color) for color in colors]
        right_rects = [r['roi']       for r in rois_data]
        left_rects  = [r['left_rect'] for r in rois_data]

        export_sel(view, model, rois_data, color_names, color_manager,
                   output_path=str(output_path / f"{scene_id}.sel"))

        for camera, mode, rects, label in (
            ('right', 'RGB', right_rects, 'right_rgb'),
            ('left',  'RGB', left_rects,  'left_rgb'),
            ('right', 'DCS', right_rects, 'right_dcs'),
            ('left',  'DCS', left_rects,  'left_dcs'),
        ):
            arr = _render_bands(*band_sets[camera][mode], base_bands, dcs=(mode == 'DCS'))
            if arr is not None:
                _save_annotated(arr, rects, mpl_colors, output_path / f"{scene_id}_{label}.png")

        spectra = np.array([r['spectrum'] for r in rois_data])
        stds    = np.array([r['std']      for r in rois_data])
        wls     = rois_data[0]['wavelengths']

        fig = plot_spectra_with_error(spectra, stds, wavelengths=wls, colors=mpl_colors, show=False)
        fig.savefig(output_path / f"{scene_id}_spectra.png", bbox_inches='tight', dpi=150)
        plt.close(fig)

        view.show_status_message(f"Context exported to {output_path}")

    except Exception as e:
        view.show_status_message(f"Context export failed: {e}")
        traceback.print_exc()


def _render_bands(r_name, g_name, b_name, base_bands, dcs):
    """Render three named bands to a uint8 (H, W, 3) numpy array."""
    if not all(k in base_bands for k in (r_name, g_name, b_name)):
        return None

    def clean(name):
        arr = base_bands[name].astype(np.float32)
        return np.where(np.isfinite(arr), arr, np.nan)

    r, g, b = clean(r_name), clean(g_name), clean(b_name)

    if not dcs:
        rgb    = np.stack([r, g, b], axis=-1)
        result = enhance_color(np.ma.masked_invalid(rgb), bounds=(0, 1), stretch=0.1)
        return (np.ma.filled(result, 0) * 255).astype(np.uint8)

    # Decorrelation stretch - eigenspace rotation per Gillespie et al. 1986.
    H, W    = r.shape
    invalid = ~np.isfinite(r) | ~np.isfinite(g) | ~np.isfinite(b)
    r = np.where(invalid, 0.0, r).astype(np.float32)
    g = np.where(invalid, 0.0, g).astype(np.float32)
    b = np.where(invalid, 0.0, b).astype(np.float32)

    vecs  = np.stack([r, g, b], axis=-1).reshape(-1, 3)
    valid = vecs[~invalid.ravel()]
    if valid.shape[0] < 4:
        return np.zeros((H, W, 3), dtype=np.uint8)

    cov        = np.cov(valid.T).astype(np.float32)
    eigvals, V = np.linalg.eig(cov)
    T          = (V @ np.diag(1.0 / np.sqrt(np.abs(eigvals))) @ V.T).astype(np.float32)
    means      = valid.mean(axis=0)
    dcs_arr    = ((vecs - means) @ T + means + (means - means @ T)).reshape(H, W, 3)

    result   = np.zeros((H, W, 3), dtype=np.float32)
    valid_2d = ~invalid
    for c in range(3):
        ch     = dcs_arr[:, :, c]
        v      = ch[valid_2d]
        if v.size == 0:
            continue
        lo, hi = np.percentile(v, [0.5, 99.5])
        result[:, :, c] = np.clip((ch - lo) / (hi - lo) if hi > lo else ch, 0.0, 1.0)
    result[invalid] = 0.0
    return (result * 255).astype(np.uint8)


def _save_annotated(arr, rects, mpl_colors, filepath):
    """Save a uint8 RGB array with colored ROI rectangles overlaid."""
    fig, ax = plt.subplots(figsize=(12, 9), dpi=150)
    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')
    ax.imshow(arr)
    ax.axis('off')
    for i, (x, y, w, h) in enumerate(rects):
        ax.add_patch(mpatches.Rectangle(
            (x, y), w, h,
            linewidth=1.5,
            edgecolor=mpl_colors[i % len(mpl_colors)],
            facecolor='none',
        ))
    fig.savefig(filepath, bbox_inches='tight', pad_inches=0, dpi=150)
    plt.close(fig)


def _sensor_offsets(load_result, instrument):
    """Return (col_off, row_off, full_H, full_W) for converting between cropped and sensor coords."""
    if instrument in {'ZCAM', 'MCZ'}:
        crop    = rapidlooks.CROP_SETTINGS["crop"]
        col_off = int(crop[0])
        row_off = int(crop[2])
        raw_band = next(iter(load_result["base_bands"].values()))
        ch, cw   = raw_band.shape
        return col_off, row_off, ch + crop[2] + crop[3], cw + crop[0] + crop[1]

    h, w = load_result['rgb_img'].shape[:2]
    return 0, 0, h, w