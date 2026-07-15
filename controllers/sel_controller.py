"""SEL file export and import."""

import traceback
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from asdf_settings import rapidlooks
from marslab.compat.mertools import MERSPECT_M20_COLOR_MAPPINGS
from PyQt5.QtWidgets import QFileDialog
from sparc.data.loading import create_rgb_stretch, dcs_rgb
from sparc.visualization.plotting import plot_spectra_with_error
from sparc.utils.sel_writer import (
    export_sel as _write_sel,
    read_sel,
    filenames_from_load_result,
)
from presets import INSTRUMENT_PRESETS
from utils.converters import hex_to_rgb

_EXPORT_DPI = 150


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


def load_sel(view, model, instrument_config, sparc_controller, has_dual_cubes, color_manager, sel_path=None):
    """Load ROIs from a .sel file into the current scene."""
    load_result = model.sparc_load_result
    if load_result is None:
        view.show_status_message("No scene loaded - cannot load SEL.")
        return None

    if sel_path is None:
        sel_path, _ = QFileDialog.getOpenFileName(
            view, "Load SEL File", "", "SEL Files (*.sel);;All Files (*)"
        )
    if not sel_path:
        return None

    try:
        instrument               = load_result.get('instrument', 'ZCAM').strip().upper()
        right_rois, left_rois, label_ids = read_sel(sel_path, instrument)

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
                    load_result['cube'],
                    left_rect if instrument == 'PCAM' else right_rect,
                    instrument_config
                )
            )

            label = label_ids[i] if i < len(label_ids) else None
            name  = index_to_name.get(label)
            if name and name in color_manager._merspect_indices:
                color = hex_to_rgb(MERSPECT_M20_COLOR_MAPPINGS[name])
            else:
                color, name = color_manager.next()

            canvas_rect = left_rect if instrument == 'PCAM' else right_rect
            rois_data.append({
                'roi':         canvas_rect,
                'right_rect':  right_rect,
                'left_rect':   left_rect,
                'mineral':     'Loaded ROI',
                'left_locked': True,   # left_rect came from the file - don't re-derive it
                **spec_data,
            })
            colors.append(color)
            color_names.append(name)

        color_manager.reset()
        color_manager.reserve(color_names)
        view.show_status_message(f"Loaded {len(rois_data)} ROI(s) from {sel_path}")
        return rois_data, colors, color_names

    except Exception as e:
        view.show_status_message(f"Load SEL failed: {e}")
        traceback.print_exc()
        return None


def load_fits(view, model, instrument_config, sparc_controller, has_dual_cubes, color_manager, fits_path=None):
    """Load ROI rectangles and schema-defined metadata from a ROIStudio FITS file."""
    load_result = model.sparc_load_result
    if load_result is None:
        view.show_status_message("No scene loaded - cannot load FITS.")
        return None

    if fits_path is None:
        fits_path, _ = QFileDialog.getOpenFileName(
            view, "Load FITS File", "", "FITS Files (*.fits);;All Files (*)"
        )
    if not fits_path:
        return None

    try:
        from astropy.io import fits as astropy_fits
        from views.panels.roi_metadata import metadata_fields

        instrument = load_result.get('instrument', 'ZCAM').strip().upper()
        fields     = metadata_fields(instrument)

        # name -> {eye: (rect, metadata)}, in first-appearance order (ROI order)
        masks       = {}
        frame_shape = None
        with astropy_fits.open(fits_path) as hdul:
            for hdu in hdul:
                hdr = hdu.header
                if 'NAME' not in hdr or 'EYE' not in hdr or hdu.data is None:
                    continue
                frame_shape = hdu.data.shape
                name = str(hdr['NAME']).strip().lower()
                eye  = str(hdr['EYE']).strip().lower()
                masks.setdefault(name, {})[eye] = (
                    _mask_rect(hdu.data),
                    {f.key: str(hdr[f.key]) for f in fields if f.key in hdr},
                )

        if not masks:
            view.show_status_message(f"No ROI masks found in {fits_path}")
            return None

        scene_shape = load_result['rgb_img'].shape[:2]
        if frame_shape is not None and tuple(frame_shape) != tuple(scene_shape):
            view.show_status_message(
                f"FITS masks are {frame_shape[1]}x{frame_shape[0]} but the scene is "
                f"{scene_shape[1]}x{scene_shape[0]} - ROIs may not line up."
            )

        name_lookup = {n.lower(): n for n in color_manager._merspect_indices}

        rois_data, colors, color_names = [], [], []

        for lname, eyes in masks.items():
            right_rect, right_meta = eyes.get('right', (None, {}))
            left_rect,  left_meta  = eyes.get('left',  (None, {}))
            right_rect = right_rect or left_rect
            left_rect  = left_rect  or right_rect
            if right_rect is None:
                continue
            metadata = right_meta or left_meta

            spec_data = (
                sparc_controller.update_roi_spectrum_dual(
                    load_result, left_rect, right_rect, instrument_config
                ) if has_dual_cubes else
                sparc_controller.update_roi_spectrum(
                    load_result['cube'],
                    left_rect if instrument == 'PCAM' else right_rect,
                    instrument_config
                )
            )

            name = name_lookup.get(lname)
            if name:
                color = hex_to_rgb(MERSPECT_M20_COLOR_MAPPINGS[name])
            else:
                color, name = color_manager.next()

            canvas_rect = left_rect if instrument == 'PCAM' else right_rect
            roi = {
                'roi':         canvas_rect,
                'right_rect':  right_rect,
                'left_rect':   left_rect,
                'mineral':     'Loaded ROI',
                'left_locked': True,   # left_rect came from the file - don't re-derive it
                **spec_data,
            }
            if metadata:
                roi['metadata'] = metadata
            rois_data.append(roi)
            colors.append(color)
            color_names.append(name)

        color_manager.reset()
        color_manager.reserve(color_names)
        view.show_status_message(f"Loaded {len(rois_data)} ROI(s) from {fits_path}")
        return rois_data, colors, color_names

    except Exception as e:
        view.show_status_message(f"Load FITS failed: {e}")
        traceback.print_exc()
        return None


def _mask_rect(mask):
    """Bounding (x, y, w, h) of the nonzero region, or None for an empty mask."""
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return None
    return (int(xs.min()), int(ys.min()),
            int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))


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
        presets     = INSTRUMENT_PRESETS.get(instrument, INSTRUMENT_PRESETS['ZCAM'])
        mpl_colors  = [tuple(c / 255.0 for c in color) for color in colors]
        right_rects = [r['right_rect']                     for r in rois_data]
        left_rects  = [r.get('left_rect', r['right_rect']) for r in rois_data]

        export_sel(view, model, rois_data, color_names, color_manager,
                   output_path=str(output_path / f"{scene_id}.sel"))

        export_fits(view, model, rois_data, color_names,
                    output_path=str(output_path / f"{scene_id}.fits"))

        for camera, mode, rects, label in (
            ('right', 'RGB', right_rects, 'right_rgb'),
            ('left',  'RGB', left_rects,  'left_rgb'),
            ('right', 'DCS', right_rects, 'right_dcs'),
            ('left',  'DCS', left_rects,  'left_dcs'),
        ):
            bands = presets[camera][mode]
            arr   = _render_bands(bands['r'], bands['g'], bands['b'], base_bands, dcs=bands['dcs'])
            if arr is not None:
                _save_annotated(arr, rects, mpl_colors, output_path / f"{scene_id}_{label}.png")

        spectra = np.array([r['spectrum'] for r in rois_data])
        stds    = np.array([r['std']      for r in rois_data])
        wls     = rois_data[0]['wavelengths']

        fig = plot_spectra_with_error(spectra, stds, wavelengths=wls, colors=mpl_colors, show=False)
        fig.savefig(output_path / f"{scene_id}_spectra.png", bbox_inches='tight', dpi=_EXPORT_DPI)
        plt.close(fig)

        view.show_status_message(f"Context exported to {output_path}")

    except Exception as e:
        view.show_status_message(f"Context export failed: {e}")
        traceback.print_exc()


def export_fits(view, model, rois_data, color_names, output_path=None):
    """Export each ROI eye as a full-frame binary-mask FITS HDU."""
    if not rois_data:
        view.show_status_message("No ROIs to export.")
        return

    load_result = model.sparc_load_result
    if load_result is None:
        view.show_status_message("No scene loaded - cannot export FITS.")
        return

    scene_id = load_result.get('id', 'scene')
    if output_path is None:
        output_path, _ = QFileDialog.getSaveFileName(
            view, "Export FITS File", f"{scene_id}.fits", "FITS Files (*.fits);;All Files (*)"
        )
    if not output_path:
        return

    try:
        from astropy.io import fits as astropy_fits

        H, W  = load_result['rgb_img'].shape[:2]
        hdus  = []
        first = True

        for eye in ('left', 'right'):
            rect_key = 'left_rect' if eye == 'left' else 'right_rect'
            for roi_data, color_name in zip(rois_data, color_names):
                mask       = np.zeros((H, W), dtype=np.uint8)
                x, y, w, h = (int(v) for v in roi_data.get(rect_key, roi_data['roi']))
                x0, x1     = max(0, x), min(W, x + w)
                y0, y1     = max(0, y), min(H, y + h)
                if x1 > x0 and y1 > y0:
                    mask[y0:y1, x0:x1] = 1

                hdr             = astropy_fits.Header()
                hdr['NAME']     = color_name.lower()
                hdr['EYE']      = eye
                hdr['SOURCEFN'] = 'ROIStudio'
                hdr['EXTNAME']  = f'{color_name.upper()} {eye.upper()}'
                hdr['IMAGEREF'] = scene_id

                for key, value in roi_data.get('metadata', {}).items():
                    hdr[key] = value

                if first:
                    hdus.append(astropy_fits.PrimaryHDU(data=mask, header=hdr))
                    first = False
                else:
                    hdus.append(astropy_fits.ImageHDU(data=mask, header=hdr))

        astropy_fits.HDUList(hdus).writeto(output_path, overwrite=True)
        view.show_status_message(f"Exported {len(rois_data)} ROI(s) to {output_path}")

    except Exception as e:
        view.show_status_message(f"FITS export failed: {e}")
        traceback.print_exc()


def _render_bands(r_name, g_name, b_name, base_bands, dcs):
    """Render three named bands to a uint8 (H, W, 3) numpy array."""
    if not all(k in base_bands for k in (r_name, g_name, b_name)):
        return None
    r, g, b = (base_bands[k].astype(np.float32) for k in (r_name, g_name, b_name))
    if dcs:
        return dcs_rgb(r, g, b)
    return create_rgb_stretch(np.stack([r, g, b]))


def _save_annotated(arr, rects, mpl_colors, filepath):
    """Save a uint8 RGB array with colored ROI rectangles overlaid."""
    fig, ax = plt.subplots(figsize=(12, 9), dpi=_EXPORT_DPI)
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
    fig.savefig(filepath, bbox_inches='tight', pad_inches=0, dpi=_EXPORT_DPI)
    plt.close(fig)


def _sensor_offsets(load_result, instrument):
    """Return (col_off, row_off, full_H, full_W) for converting between cropped and sensor coords."""
    if instrument in {'ZCAM', 'MCZ'}:
        crop     = rapidlooks.CROP_SETTINGS["crop"]
        col_off  = int(crop[0])
        row_off  = int(crop[2])
        raw_band = next(iter(load_result["base_bands"].values()))
        ch, cw   = raw_band.shape
        return col_off, row_off, ch + crop[2] + crop[3], cw + crop[0] + crop[1]

    h, w = load_result['rgb_img'].shape[:2]
    return 0, 0, h, w
