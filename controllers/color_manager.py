"""Color palette management for ROI display."""

from utils.converters import hex_to_rgb


class ColorManager:
    """Hands out colors from the merspect palette and recycles them on ROI deletion."""

    def __init__(self, instrument):
        self._palette      = []
        self._name_palette = []
        self._merspect_indices = {}
        self._stack        = []
        self._next_index   = 0
        self._reserved     = set()
        self._init_palette(instrument)

    def _init_palette(self, instrument):
        from marslab.compat.mertools import MERSPECT_M20_COLOR_MAPPINGS

        merspect_order = [
            'eraser', 'green', 'yellow', 'blue', 'red', 'magenta', 'cyan',
            'orange', 'azure', 'purple', 'lime', 'rust',
            'green+2', 'green-1', 'green-2', 'yellow-2', 'blue+2', 'blue-1',
            'blue-2', 'red+2', 'red-1', 'red-2', 'magenta+2', 'magenta+1',
            'magenta-1', 'magenta-2', 'magenta-3', 'cyan+2', 'cyan+1', 'cyan-1',
            'cyan-2', 'cyan-3', 'orange+2', 'orange+1', 'orange-1', 'orange-2',
            'orange-3', 'azure+2', 'azure+1',
        ]
        self._merspect_indices = {k: i for i, k in enumerate(merspect_order)}

        # eraser is not a valid ROI color.
        usable = [k for k in merspect_order if k != 'eraser']

        preferred = [
            'red', 'magenta', 'cyan', 'orange', 'azure', 'purple',
            'lime', 'rust', 'green', 'blue', 'yellow', 'magenta+2', 'magenta-3',
        ]
        preferred_set = set(preferred)
        ordered       = [k for k in preferred if k in set(usable)]
        remainder     = [k for k in usable    if k not in preferred_set]

        for k in ordered + remainder:
            if k in MERSPECT_M20_COLOR_MAPPINGS:
                self._palette.append(hex_to_rgb(MERSPECT_M20_COLOR_MAPPINGS[k]))
                self._name_palette.append(k)

    def merspect_index(self, name: str) -> int:
        """Return the MERSpect label index for a color name."""
        return self._merspect_indices[name]

    def reserve(self, names: list):
        """Mark a set of color names as in-use so next() skips over them."""
        self._reserved = set(names)
        self._next_index = 0

    def next(self):
        """Return the next (color, name) pair, recycling returned colors first."""
        if self._stack:
            return self._stack.pop()
        while self._next_index < len(self._palette):
            idx   = self._next_index
            name  = self._name_palette[idx]
            self._next_index += 1
            if name not in self._reserved:
                return self._palette[idx], name
        # all colors exhausted - wrap around ignoring reserved
        self._next_index = 0
        idx  = self._next_index % len(self._palette)
        self._next_index += 1
        return self._palette[idx], self._name_palette[idx]

    def peek(self):
        """Return the next (color, name) pair without consuming it."""
        if self._stack:
            return self._stack[-1]
        idx = self._next_index
        while idx < len(self._palette):
            name = self._name_palette[idx]
            if name not in self._reserved:
                return self._palette[idx], name
            idx += 1
        return self._palette[0], self._name_palette[0]

    def set_next(self, name: str):
        """Force a specific color to be returned by the next next() call."""
        if name not in self._name_palette:
            return
        idx   = self._name_palette.index(name)
        color = self._palette[idx]
        # Push onto the stack so it takes priority over the sequential index.
        self._stack.append((color, name))

    def full_palette(self):
        """Return the complete (color, name) palette list."""
        return list(zip(self._palette, self._name_palette))

    def recycle(self, color, name):
        self._stack.append((color, name))

    def reset(self):
        self._stack      = []
        self._next_index = 0
        self._reserved   = set()