"""Scene scan and load callback handlers."""


def on_scene_found(scene_id, pixmap, filename, view):
    view.add_scene_thumbnail(scene_id, pixmap, filename)


def on_scan_complete(total_scenes, view):
    view.stop_loading()
    view.show_status_message(f"Scan complete. Found {total_scenes} scene(s).")


def on_scan_error(error_msg, view):
    view.stop_loading()
    view.show_status_message(f"Scan error: {error_msg}")


def on_scene_load_complete(load_result, scene_id, model, view):
    """Update model and view after a scene has finished loading."""
    model.sparc_load_result = load_result

    view.set_export_enabled(False)
    view.action_load_sel.setEnabled(True)
    view.select_scene(scene_id)
    view.enable_presets(True)

    if 'rgb_img' not in load_result:
        view.stop_loading()
        view.show_status_message("Error: no RGB image in load result")
        return

    if 'homography_matrix' in load_result:
        view.panel_image_editing.canvas_container.set_homography_matrix(
            load_result['homography_matrix']
        )

    _set_band_names(load_result, view)
    view.set_instrument_presets(load_result.get('instrument', 'ZCAM'))
    view.panel_image_editing.set_rois([], [], [])
    view.panel_spectral_view.clear_roi_spectra()
    view.panel_spectral_view.clear_plot()
    view.stop_loading()
    view.show_status_message(f"Scene loaded: {load_result['id']}")


def on_scene_load_error(error_msg, view):
    view.stop_loading()
    view.show_status_message(f"Error loading scene: {error_msg}")
    view.enable_presets(False)


def _set_band_names(load_result, view):
    base_bands = load_result.get('base_bands', {})
    band_names = list(base_bands.keys())
    if not band_names:
        return

    instrument  = load_result.get('instrument', 'ZCAM')
    right_bands = [b for b in band_names if b.startswith('R')] or band_names
    left_bands  = [b for b in band_names if b.startswith('L')] or band_names

    if instrument == 'ZCAM':
        r_r, g_r, b_r = 'R0R', 'R0G', 'R0B'
        r_l, g_l, b_l = 'L0R', 'L0G', 'L0B'
    else:
        r_r, g_r, b_r = 'R2', 'R1', 'R1'
        r_l, g_l, b_l = 'L2', 'L5', 'L6'

    view.panel_image_editing.set_band_names(
        right_bands, left_bands,
        r_r, g_r, b_r,
        r_l, g_l, b_l,
    )