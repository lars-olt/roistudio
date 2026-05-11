"""SEL file export and import."""

import numpy as np
from PyQt5.QtWidgets import QFileDialog


def export_sel(view, model, rois_data, color_names, color_manager):
    if not rois_data:
        view.show_status_message("No ROIs to export.")
        return

    load_result = model.sparc_load_result
    if load_result is None:
        view.show_status_message("No scene loaded - cannot export SEL.")
        return

    scene_id   = load_result.get('id', 'scene')
    output_path, _ = QFileDialog.getSaveFileName(
        view, "Export SEL File", f"{scene_id}.sel", "SEL Files (*.sel);;All Files (*)"
    )
    if not output_path:
        return

    try:
        from sparc.utils.sel_writer import export_sel as _write_sel, filenames_from_load_result

        instrument = load_result.get('instrument', 'ZCAM').strip().upper()
        n_rois     = len(rois_data)
        right_rois = np.array([r['right_rect']                    for r in rois_data], dtype=np.int32)
        left_rois  = np.array([r.get('left_rect', r['right_rect']) for r in rois_data], dtype=np.int32)

        col_off, row_off, full_H, full_W = _sensor_offsets(load_result, instrument)

        if col_off or row_off:
            right_rois = right_rois.copy(); right_rois[:, 0] += col_off; right_rois[:, 1] += row_off
            left_rois  = left_rois.copy();  left_rois[:, 0]  += col_off; left_rois[:, 1]  += row_off

        # Use each color's MERSpect index as the label so ROI colors round-trip
        # correctly when the .sel file is opened in MERSpect.
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
        import traceback; traceback.print_exc()


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
        from sparc.utils.sel_writer import read_sel

        instrument              = load_result.get('instrument', 'ZCAM').strip().upper()
        right_rois, left_rois, label_ids = read_sel(path, instrument)

        col_off, row_off, _, _ = _sensor_offsets(load_result, instrument)
        if col_off or row_off:
            right_rois = right_rois.copy(); right_rois[:, 0] -= col_off; right_rois[:, 1] -= row_off
            left_rois  = left_rois.copy();  left_rois[:, 0]  -= col_off; left_rois[:, 1]  -= row_off

        # Map MERSpect label indices back to color names, falling back to
        # sequential palette assignment for any unrecognised label.
        index_to_name = {v: k for k, v in color_manager._merspect_indices.items()}

        rois_data   = []
        colors      = []
        color_names = []

        for i, (right_rect, left_rect) in enumerate(zip(right_rois, left_rois)):
            right_rect = tuple(int(v) for v in right_rect)
            left_rect  = tuple(int(v) for v in left_rect)

            if has_dual_cubes:
                spec_data = sparc_controller.update_roi_spectrum_dual(
                    load_result, left_rect, right_rect, instrument_config
                )
            else:
                spec_data = sparc_controller.update_roi_spectrum(
                    load_result['cube'], right_rect, instrument_config
                )

            label    = label_ids[i] if i < len(label_ids) else None
            name     = index_to_name.get(label)
            if name and name in color_manager._merspect_indices:
                from utils.converters import hex_to_rgb
                from marslab.compat.mertools import MERSPECT_M20_COLOR_MAPPINGS
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
        import traceback; traceback.print_exc()
        return None


def _sensor_offsets(load_result, instrument):
    """Return (col_off, row_off, full_H, full_W) for converting between cropped and sensor coords."""
    if instrument in {'ZCAM', 'MCZ'}:
        from asdf_settings import rapidlooks
        crop     = rapidlooks.CROP_SETTINGS["crop"]
        col_off  = int(crop[0])
        row_off  = int(crop[2])
        raw_band = next(iter(load_result["base_bands"].values()))
        ch, cw   = raw_band.shape
        return col_off, row_off, ch + crop[2] + crop[3], cw + crop[0] + crop[1]

    h, w = load_result['rgb_img'].shape[:2]
    return 0, 0, h, w