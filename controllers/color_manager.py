"""Color palette management for ROI display."""

from utils.converters import hex_to_rgb


class ColorManager:
    """Hands out colors from the merspect palette and recycles them on ROI deletion."""

    def __init__(self, instrument):
        self._palette      = []
        self._name_palette = []
        self._stack        = []
        self._next_index   = 0
        self._init_palette(instrument)

    def _init_palette(self, instrument):
        from marslab.compat import mertools
        from sparc.utils.sel_writer import _MASK_DEFAULTS, _normalize_instrument

        all_colors = list(mertools.MERSPECT_M20_COLOR_MAPPINGS.items())
        first_id   = _MASK_DEFAULTS[_normalize_instrument(instrument)]['first_id']
        available  = all_colors[max(0, first_id - 1):]

        preferred = [
            'red', 'magenta', 'cyan', 'orange', 'azure', 'purple',
            'lime', 'rust', 'green', 'blue', 'yellow', 'magenta 2+', 'magenta -3',
        ]
        name_to_item = {k.lower(): (k, v) for k, v in available}
        ordered      = [name_to_item[n] for n in preferred if n in name_to_item]
        remainder    = [(k, v) for k, v in available if k.lower() not in set(preferred)]

        for k, v in ordered + remainder:
            self._palette.append(hex_to_rgb(v))
            self._name_palette.append(k)

    def next(self):
        """Return the next (color, name) pair, recycling returned colors first."""
        if self._stack:
            return self._stack.pop()
        idx   = self._next_index % len(self._palette)
        color = self._palette[idx]
        name  = self._name_palette[idx]
        self._next_index += 1
        return color, name

    def recycle(self, color, name):
        self._stack.append((color, name))

    def reset(self):
        self._stack      = []
        self._next_index = 0