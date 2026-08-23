"""SEL file export and import."""

import traceback
import importlib
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from asdf_settings import rapidlooks
from PyQt5.QtWidgets import QFileDialog
from sparc.data.loading import create_rgb_stretch, dcs_rgb, observation_metadata
from sparc.visualization.plotting import plot_spectra_with_error
from sparc.utils.sel_writer import (
    export_sel as _write_sel,
    read_sel,
    filenames_from_load_result,
)
from presets import INSTRUMENT_PRESETS
from roi_groups import group_roi_regions

_EXPORT_DPI = 150
_ROI_LABEL_FONT_SIZE = 8
_ROI_LABEL_PADDING = 0.2
_sel_writer_module = importlib.import_module('sparc.utils.sel_writer')
_EMPTY_RECT = (0, 0, 0, 0)


def _rect_or_empty(roi_data, key):
    rect = roi_data.get(key)
    return tuple(rect) if rect is not None else _EMPTY_RECT


def _rect_or_none(rect):
    values = tuple(int(v) for v in rect)
    return values if values[2] > 0 and values[3] > 0 else None


def _shift_present_rois(rois, col_delta, row_delta):
    """Shift only painted ROI rows, leaving missing-eye placeholders empty."""
    shifted = np.asarray(rois, dtype=np.int32).copy()
    if shifted.size == 0:
        return shifted.reshape(0, 4)
    present = (shifted[:, 2] > 0) & (shifted[:, 3] > 0)
    shifted[present, 0] += int(col_delta)
    shifted[present, 1] += int(row_delta)
    return shifted


def _read_sel_aligned(sel_path, instrument):
    """Read both SEL eye masks and align rectangles by their label IDs.

    The public SPARC reader historically compacted each eye independently,
    which loses the pairing when an ROI is absent from the middle of one eye's
    mask.  Newer/private mask helpers expose the IDs needed for exact alignment;
    the public reader remains a compatibility fallback.
    """
    required = ('_read_template', '_rois_from_block', '_normalize_instrument',
                '_MASK_DEFAULTS', '_LSEL_IDX', '_RSEL_IDX')
    if not all(hasattr(_sel_writer_module, name) for name in required):
        return read_sel(sel_path, instrument)

    inst_key = _sel_writer_module._normalize_instrument(instrument)
    background = _sel_writer_module._MASK_DEFAULTS[inst_key]['background']
    blocks = _sel_writer_module._read_template(Path(sel_path))
    right_rois, right_ids = _sel_writer_module._rois_from_block(
        blocks[_sel_writer_module._RSEL_IDX].decompressed, background
    )
    left_rois, left_ids = _sel_writer_module._rois_from_block(
        blocks[_sel_writer_module._LSEL_IDX].decompressed, background
    )

    label_ids = sorted(set(right_ids) | set(left_ids))
    right_by_id = dict(zip(right_ids, right_rois))
    left_by_id = dict(zip(left_ids, left_rois))
    right = np.array(
        [right_by_id.get(label, _EMPTY_RECT) for label in label_ids],
        dtype=np.int32,
    ).reshape(-1, 4)
    left = np.array(
        [left_by_id.get(label, _EMPTY_RECT) for label in label_ids],
        dtype=np.int32,
    ).reshape(-1, 4)
    return right, left, label_ids


def _rect_components_from_block(block, background):
    """Return every connected rectangle and label from one SEL eye mask."""
    payload = block.decompressed
    if not payload:
        return []
    try:
        W, H, header_size = _sel_writer_module._parse_mask_header(payload)
    except (TypeError, ValueError, IndexError):
        return []
    mask = np.frombuffer(
        payload[header_size:header_size + H * W], dtype=np.uint8
    ).reshape(H, W)
    components = []
    for label_id in sorted(int(v) for v in np.unique(mask) if v != background):
        for x, mask_y, w, h in _component_rects(mask == label_id):
            components.append(((x, H - mask_y - h, w, h), label_id))
    return components


def _read_sel_regions(sel_path, instrument):
    """Read independently editable regions while preserving color classes."""
    required = ('_read_template', '_parse_mask_header', '_normalize_instrument',
                '_MASK_DEFAULTS', '_LSEL_IDX', '_RSEL_IDX')
    if not all(hasattr(_sel_writer_module, name) for name in required):
        return _read_sel_aligned(sel_path, instrument)

    inst_key = _sel_writer_module._normalize_instrument(instrument)
    background = _sel_writer_module._MASK_DEFAULTS[inst_key]['background']
    blocks = _sel_writer_module._read_template(Path(sel_path))
    right_components = _rect_components_from_block(
        blocks[_sel_writer_module._RSEL_IDX], background
    )
    left_components = _rect_components_from_block(
        blocks[_sel_writer_module._LSEL_IDX], background
    )

    rows = [
        (rect, _EMPTY_RECT, label_id)
        for rect, label_id in right_components
    ] + [
        (_EMPTY_RECT, rect, label_id)
        for rect, label_id in left_components
    ]
    rows.sort(key=lambda row: (row[2], row[0] == _EMPTY_RECT, row[0], row[1]))
    right = np.array([row[0] for row in rows], dtype=np.int32).reshape(-1, 4)
    left = np.array([row[1] for row in rows], dtype=np.int32).reshape(-1, 4)
    return right, left, [row[2] for row in rows]


def _empty_spectrum_data():
    return {
        'spectrum': [], 'std': [], 'wavelengths': [],
        'bayer_spectrum': [], 'bayer_std': [], 'bayer_wavelengths': [],
        'left_spectrum': [], 'left_std': [], 'left_wavelengths': [],
        'right_spectrum': [], 'right_std': [], 'right_wavelengths': [],
    }


def _spectrum_for_eyes(sparc_controller, load_result, left_rect, right_rect,
                       instrument_config, has_dual_cubes):
    if has_dual_cubes:
        return sparc_controller.update_roi_spectrum_dual(
            load_result, left_rect, right_rect, instrument_config
        )
    instrument = load_result.get('instrument', 'ZCAM').strip().upper()
    rect = left_rect if instrument == 'PCAM' else right_rect
    if rect is None:
        return _empty_spectrum_data()
    data = dict(sparc_controller.update_roi_spectrum(
        load_result['cube'], rect, instrument_config
    ))
    for key in ('roi', 'left_rect', 'right_rect'):
        data.pop(key, None)
    return data


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
        right_rois = np.array(
            [_rect_or_empty(r, 'right_rect') for r in rois_data], dtype=np.int32
        )
        left_rois = np.array(
            [_rect_or_empty(r, 'left_rect') for r in rois_data], dtype=np.int32
        )

        col_off, row_off, full_H, full_W = _sensor_offsets(load_result, instrument)
        if col_off or row_off:
            right_rois = _shift_present_rois(right_rois, col_off, row_off)
            left_rois  = _shift_present_rois(left_rois, col_off, row_off)

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
        right_rois, left_rois, label_ids = _read_sel_regions(sel_path, instrument)

        col_off, row_off, _, _ = _sensor_offsets(load_result, instrument)
        if col_off or row_off:
            right_rois = _shift_present_rois(right_rois, -col_off, -row_off)
            left_rois  = _shift_present_rois(left_rois, -col_off, -row_off)

        rois_data, colors, color_names = [], [], []
        label_colors = {}

        for i, (right_rect, left_rect) in enumerate(zip(right_rois, left_rois)):
            right_rect = _rect_or_none(right_rect)
            left_rect  = _rect_or_none(left_rect)
            if right_rect is None and left_rect is None:
                continue

            spec_data = _spectrum_for_eyes(
                sparc_controller, load_result, left_rect, right_rect,
                instrument_config, has_dual_cubes,
            )

            label = label_ids[i] if i < len(label_ids) else None
            name  = color_manager.name_for_merspect_index(label)
            if name:
                color = color_manager.color(name)
            elif label in label_colors:
                color, name = label_colors[label]
            else:
                color, name = color_manager.next()
                label_colors[label] = (color, name)

            canvas_rect = left_rect if instrument == 'PCAM' else right_rect
            rois_data.append({
                'roi':         canvas_rect,
                'right_rect':  right_rect,
                'left_rect':   left_rect,
                'mineral':     'Loaded ROI',
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
    """Load ROI rectangles and schema-defined metadata from an ROIStudio FITS file."""
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

        # name -> {eye: (mask, metadata)}; ROIINDEX preserves class order.
        masks       = {}
        mask_order  = {}
        frame_shape = None
        with astropy_fits.open(fits_path) as hdul:
            for hdu in hdul:
                hdr = hdu.header
                if 'NAME' not in hdr or 'EYE' not in hdr or hdu.data is None:
                    continue
                frame_shape = hdu.data.shape
                name = str(hdr['NAME']).strip().lower()
                eye  = str(hdr['EYE']).strip().lower()
                try:
                    order = int(hdr.get('ROIINDEX', len(mask_order)))
                except (TypeError, ValueError):
                    order = len(mask_order)
                mask_order.setdefault(name, order)
                eye_masks = masks.setdefault(name, {})
                incoming_mask = np.asarray(hdu.data) != 0
                incoming_metadata = {
                    f.key: str(hdr[f.key]) for f in fields if f.key in hdr
                }
                if eye in eye_masks:
                    existing_mask, existing_metadata = eye_masks[eye]
                    eye_masks[eye] = (
                        np.asarray(existing_mask, dtype=bool) | incoming_mask,
                        existing_metadata or incoming_metadata,
                    )
                else:
                    eye_masks[eye] = (incoming_mask, incoming_metadata)

        if not masks:
            view.show_status_message(f"No ROI masks found in {fits_path}")
            return None

        scene_shape = load_result['rgb_img'].shape[:2]
        if frame_shape is not None and tuple(frame_shape) != tuple(scene_shape):
            view.show_status_message(
                f"FITS masks are {frame_shape[1]}x{frame_shape[0]} but the scene is "
                f"{scene_shape[1]}x{scene_shape[0]} - ROIs may not line up."
            )

        rois_data, colors, color_names = [], [], []

        for lname, eyes in sorted(masks.items(), key=lambda item: mask_order[item[0]]):
            right_mask, right_meta = eyes.get('right', (None, {}))
            left_mask,  left_meta  = eyes.get('left',  (None, {}))
            metadata = right_meta or left_meta

            name = color_manager.resolve_name(lname)
            if name:
                color = color_manager.color(name)
            else:
                color, name = color_manager.next()

            # A class mask may contain several disconnected rectangles. Keep
            # each component independently editable and use the shared color
            # name to restore its selection-class identity. Do not guess eye
            # pairings: that could create exactly the cross-eye edit side
            # effects that single-eye regions are intended to avoid.
            regions = [
                (None, rect) for rect in _mask_rects(right_mask)
            ] + [
                (rect, None) for rect in _mask_rects(left_mask)
            ]
            for left_rect, right_rect in regions:
                spec_data = _spectrum_for_eyes(
                    sparc_controller, load_result, left_rect, right_rect,
                    instrument_config, has_dual_cubes,
                )
                canvas_rect = left_rect if instrument == 'PCAM' else right_rect
                roi = {
                    'roi':         canvas_rect,
                    'right_rect':  right_rect,
                    'left_rect':   left_rect,
                    'mineral':     'Loaded ROI',
                    **spec_data,
                }
                if metadata:
                    roi['metadata'] = dict(metadata)
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


def _mask_rects(mask):
    """Bounding rectangles for all connected nonzero regions in a mask."""
    if mask is None:
        return []
    return _component_rects(np.asarray(mask) != 0)


def _component_rects(mask):
    """Return 4-connected component bounds using row runs and union-find.

    Keeping this small routine local avoids making SEL/FITS loading depend on
    SciPy merely to recover the rectangles stored in a class mask.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or not mask.any():
        return []

    parents = []
    bounds = []  # inclusive x0/y0/x1/y1 per horizontal run

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first, second):
        a, b = find(first), find(second)
        if a != b:
            parents[b] = a

    previous = []  # (x0, x1, run index)
    for y, row in enumerate(mask):
        transitions = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        starts = np.flatnonzero(transitions == 1)
        stops = np.flatnonzero(transitions == -1)
        current = []
        previous_start = 0
        for x0, x1_exclusive in zip(starts, stops):
            x1 = int(x1_exclusive - 1)
            x0 = int(x0)
            index = len(parents)
            parents.append(index)
            bounds.append([x0, y, x1, y])
            current.append((x0, x1, index))

            while (previous_start < len(previous)
                   and previous[previous_start][1] < x0):
                previous_start += 1
            cursor = previous_start
            while cursor < len(previous) and previous[cursor][0] <= x1:
                union(index, previous[cursor][2])
                cursor += 1
        previous = current

    merged = {}
    for index, (x0, y0, x1, y1) in enumerate(bounds):
        root = find(index)
        if root not in merged:
            merged[root] = [x0, y0, x1, y1]
        else:
            box = merged[root]
            box[0] = min(box[0], x0)
            box[1] = min(box[1], y0)
            box[2] = max(box[2], x1)
            box[3] = max(box[3], y1)

    return sorted(
        ((x0, y0, x1 - x0 + 1, y1 - y0 + 1)
         for x0, y0, x1, y1 in merged.values()),
        key=lambda rect: (rect[1], rect[0]),
    )


def export_context(view, model, rois_data, colors, color_names, color_manager,
                   selection_data=None, selection_colors=None):
    """Export a context folder with ROI data, annotated images, and spectra."""
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
        eye_annotations = {}
        for eye in ('right', 'left'):
            key = f'{eye}_rect'
            items = [
                (roi[key], mpl_colors[i], color_names[i])
                for i, roi in enumerate(rois_data)
                if roi.get(key) is not None
            ]
            eye_annotations[eye] = items

        export_sel(view, model, rois_data, color_names, color_manager,
                   output_path=str(output_path / f"{scene_id}.sel"))

        export_fits(view, model, rois_data, color_names,
                    output_path=str(output_path / f"{scene_id}.fits"))

        for camera, mode, label in (
            ('right', 'RGB', 'right_rgb'),
            ('left',  'RGB', 'left_rgb'),
            ('right', 'DCS', 'right_dcs'),
            ('left',  'DCS', 'left_dcs'),
        ):
            annotations = eye_annotations[camera]
            rects       = [item[0] for item in annotations]
            eye_colors  = [item[1] for item in annotations]
            eye_names   = [item[2] for item in annotations]
            bands = presets[camera][mode]
            arr   = _render_bands(bands['r'], bands['g'], bands['b'], base_bands, dcs=bands['dcs'])
            if arr is not None:
                _save_annotated(arr, rects, eye_colors, output_path / f"{scene_id}_{label}.png")
                if mode == 'RGB':
                    _save_annotated(
                        arr,
                        rects,
                        eye_colors,
                        output_path / f"{scene_id}_{label}_with_roi_names.png",
                        roi_names=eye_names,
                    )

        spectrum_rows = selection_data if selection_data is not None else rois_data
        spectrum_rgb = selection_colors if selection_colors is not None else colors
        spectrum_colors = [tuple(c / 255.0 for c in color) for color in spectrum_rgb]
        valid_rows = [
            (row, spectrum_colors[i])
            for i, row in enumerate(spectrum_rows)
            if len(row.get('spectrum', [])) > 0 and i < len(spectrum_colors)
        ]
        if valid_rows:
            spectra = np.array([row['spectrum'] for row, _ in valid_rows])
            stds = np.array([row['std'] for row, _ in valid_rows])
            wls = valid_rows[0][0]['wavelengths']
            fig = plot_spectra_with_error(
                spectra, stds, wavelengths=wls,
                colors=[color for _, color in valid_rows], show=False,
            )
            fig.savefig(
                output_path / f"{scene_id}_spectra.png",
                bbox_inches='tight', dpi=_EXPORT_DPI,
            )
            plt.close(fig)

        view.show_status_message(f"Context exported to {output_path}")

    except Exception as e:
        view.show_status_message(f"Context export failed: {e}")
        traceback.print_exc()


def export_fits(view, model, rois_data, color_names, output_path=None):
    """Export one union-mask FITS HDU per selection class and present eye."""
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

        instrument = load_result.get('instrument', 'ZCAM').strip().upper()
        is_zcam = instrument == 'ZCAM'
        H, W  = load_result['rgb_img'].shape[:2]
        hdus  = []
        first = True
        scene_metadata = {} if is_zcam else observation_metadata(load_result)

        groups = group_roi_regions(
            rois_data, [(255, 255, 255)] * len(rois_data), color_names
        )
        for eye in ('left', 'right'):
            rect_key = 'left_rect' if eye == 'left' else 'right_rect'
            for class_index, group in enumerate(groups):
                rects = [
                    roi_data[rect_key]
                    for roi_data in group['regions']
                    if roi_data.get(rect_key) is not None
                ]
                if not rects:
                    continue
                mask = np.zeros((H, W), dtype=np.uint8)
                for rect in rects:
                    x, y, w, h = (int(v) for v in rect)
                    x0, x1 = max(0, x), min(W, x + w)
                    y0, y1 = max(0, y), min(H, y + h)
                    if x1 > x0 and y1 > y0:
                        mask[y0:y1, x0:x1] = 1

                hdr             = astropy_fits.Header()
                hdr['NAME']     = group['name'].lower()
                hdr['EYE']      = eye
                hdr['SOURCEFN'] = 'ROIStudio'
                hdr['EXTNAME']  = f"{group['name'].upper()} {eye.upper()}"
                hdr['IMAGEREF'] = scene_id

                # Mastcam-Z follows the compact legacy MERSpect/ASDF mask
                # header. Preserve ROIStudio's existing richer metadata for
                # other instruments, including Pancam.
                if not is_zcam:
                    hdr['ROIINDEX'] = class_index
                    for key, value in group['metadata'].items():
                        hdr[key] = value

                if first:
                    for key, value in scene_metadata.items():
                        hdr[key] = value
                    hdus.append(astropy_fits.PrimaryHDU(data=mask, header=hdr))
                    first = False
                else:
                    hdus.append(astropy_fits.ImageHDU(data=mask, header=hdr))

        astropy_fits.HDUList(hdus).writeto(output_path, overwrite=True)
        view.show_status_message(
            f"Exported {len(groups)} selection class(es) to {output_path}"
        )

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


def _save_annotated(arr, rects, mpl_colors, filepath, roi_names=None):
    """Save an RGB array with colored ROI rectangles and optional names overlaid."""
    fig, ax = plt.subplots(figsize=(12, 9), dpi=_EXPORT_DPI)
    fig.patch.set_facecolor('black')
    ax.set_facecolor('black')
    ax.imshow(arr)
    ax.axis('off')
    for i, (x, y, w, h) in enumerate(rects):
        color = mpl_colors[i % len(mpl_colors)]
        ax.add_patch(mpatches.Rectangle(
            (x, y), w, h,
            linewidth=1.5,
            edgecolor=color,
            facecolor='none',
        ))
        if roi_names is not None and i < len(roi_names):
            padding_points = _ROI_LABEL_FONT_SIZE * _ROI_LABEL_PADDING
            ax.annotate(
                str(roi_names[i]),
                xy=(x, y),
                xytext=(padding_points, padding_points),
                textcoords='offset points',
                color=color,
                fontfamily='Arial',
                fontsize=_ROI_LABEL_FONT_SIZE,
                fontweight='normal',
                horizontalalignment='left',
                verticalalignment='bottom',
                clip_on=False,
                annotation_clip=False,
                bbox={
                    'boxstyle': f'square,pad={_ROI_LABEL_PADDING}',
                    'facecolor': (20 / 255, 20 / 255, 20 / 255),
                    'edgecolor': 'none',
                    'alpha': 200 / 255,
                },
            )
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
