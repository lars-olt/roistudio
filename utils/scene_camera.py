"""Select the camera shown in single view from the scene's available bands."""


def available_cameras(load_result):
    if 'left_band_keys' in load_result or 'right_band_keys' in load_result:
        return {eye for eye in ('left', 'right') if load_result.get(f'{eye}_band_keys')}
    # Older callers without band metadata retain their instrument's default.
    return {'left', 'right'}


def display_camera(load_result):
    instrument = str(load_result.get('instrument', 'ZCAM')).strip().upper()
    preferred = 'left' if instrument == 'PCAM' else 'right'
    available = available_cameras(load_result)
    other = 'right' if preferred == 'left' else 'left'
    return other if preferred not in available and other in available else preferred
