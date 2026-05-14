"""Color palette management for ROI display."""

from collections import deque

from marslab.compat.mertools import MERSPECT_M20_COLOR_MAPPINGS
from utils.converters import hex_to_rgb


class ColorManager:
    """Hands out colors from the MERSpect palette using a priority-ordered deque.

    The deque is built with preferred colors first, remainder after. On recycle,
    a color is only re-added if not already present - preferred colors go to the
    front, others to the back.
    """

    def __init__(self, instrument):
        self._palette          = []
        self._name_palette     = []
        self._merspect_indices = {}
        self._preferred_set    = set()
        self._reserved         = set()
        self._deque            = deque()
        self._init_palette(instrument)

    def _init_palette(self, instrument):
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
        self._preferred_set = set(preferred)
        ordered   = [k for k in preferred if k in set(usable)]
        remainder = [k for k in usable if k not in self._preferred_set]

        for k in ordered + remainder:
            if k in MERSPECT_M20_COLOR_MAPPINGS:
                self._palette.append(hex_to_rgb(MERSPECT_M20_COLOR_MAPPINGS[k]))
                self._name_palette.append(k)

        self._rebuild_deque()

    def _rebuild_deque(self):
        """Rebuild the deque in priority order, skipping reserved names."""
        self._deque = deque(
            (color, name)
            for color, name in zip(self._palette, self._name_palette)
            if name not in self._reserved
        )

    def _deque_names(self):
        return {name for _, name in self._deque}

    def merspect_index(self, name: str) -> int:
        """Return the MERSpect label index for a color name."""
        return self._merspect_indices[name]

    def reserve(self, names: list):
        """Mark a set of color names as in-use so next() skips over them."""
        self._reserved = set(names)
        self._rebuild_deque()

    def next(self):
        """Pop and return the next (color, name) pair from the front of the deque."""
        if self._deque:
            return self._deque.popleft()
        # All colors exhausted - wrap around with the full palette.
        self._rebuild_deque()
        return self._deque.popleft() if self._deque else (self._palette[0], self._name_palette[0])

    def peek(self):
        """Return the next (color, name) pair without consuming it."""
        if self._deque:
            return self._deque[0]
        return self._palette[0], self._name_palette[0]

    def set_next(self, name: str):
        """Force a specific color to be returned by the next next() call."""
        if name not in self._name_palette:
            return
        idx   = self._name_palette.index(name)
        entry = (self._palette[idx], name)
        # Remove existing entry if present, then push to front.
        self._deque = deque(e for e in self._deque if e[1] != name)
        self._deque.appendleft(entry)

    def full_palette(self):
        """Return the complete (color, name) palette list."""
        return list(zip(self._palette, self._name_palette))

    def recycle(self, color, name):
        """Return a color to the deque if not already present.

        Preferred colors go to the front, others to the back.
        """
        if name in self._deque_names():
            return
        if name in self._preferred_set:
            self._deque.appendleft((color, name))
        else:
            self._deque.append((color, name))

    def consume(self, name: str):
        """Remove a specific color from the deque - used when assigning it directly."""
        self._deque = deque(e for e in self._deque if e[1] != name)

    def reset(self):
        self._reserved = set()
        self._rebuild_deque()