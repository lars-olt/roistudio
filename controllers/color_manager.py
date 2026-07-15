"""Color palette management for ROI display."""

from collections import deque

from marslab.compat.mertools import MERSPECT_M20_COLOR_MAPPINGS
from utils.converters import hex_to_rgb


class ColorManager:
    """Allocate and recycle colors from the MERSpect palette."""

    def __init__(self, instrument):
        self._palette          = []
        self._name_palette     = []
        self._merspect_indices = {}
        self._preferred_set    = set()
        self._reserved         = set()
        self._deque            = deque()
        self._init_palette(instrument)

    def _init_palette(self, instrument):
        if instrument == 'PCAM':
            self._init_pcam_palette()
        else:
            self._init_zcam_palette()
        self._rebuild_deque()

    def _init_zcam_palette(self):
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

        # Eraser is not a valid ROI color.
        usable = [k for k in merspect_order if k != 'eraser']

        preferred = [
            'red', 'magenta', 'cyan', 'orange', 'azure', 'purple',
            'lime', 'rust', 'green', 'blue', 'yellow', 'magenta+2', 'magenta-3',
        ]
        self._build_palette(usable, preferred)

    def _init_pcam_palette(self):
        # MERSpect's Pancam palette. Each MER color maps to its closest MCZ
        # equivalent for the RGB lookup. Label index is the MER list position
        # so .sel files round-trip with legacy MERSpect.
        mer_to_mcz = [
            ('red',          'red-1'),
            ('light green',  'green'),
            ('light blue',   'blue'),
            ('light cyan',   'cyan'),
            ('dark green',   'green-2'),
            ('yellow',       'yellow'),
            ('light purple', 'magenta'),
            ('pink',         'red+2'),
            ('teal',         'cyan-2'),
            ('goldenrod',    'orange-1'),
            ('sienna',       'orange-2'),
            ('dark blue',    'blue-2'),
            ('bright red',   'red'),
            ('dark red',     'red-2'),
            ('dark purple',  'purple'),
            ('eraser',       None),
        ]

        # Index by MER list position; palette is keyed on the MCZ name so RGB
        # lookup and SEL import (which read MERSPECT_M20_COLOR_MAPPINGS) work.
        self._merspect_indices = {mcz: i for i, (_mer, mcz) in enumerate(mer_to_mcz) if mcz}

        usable = [mcz for _mer, mcz in mer_to_mcz if mcz]
        # Handout follows the MER list from top to bottom.
        self._build_palette(usable, preferred=usable)

    def _build_palette(self, usable, preferred):
        """Populate palette/name/preferred fields from a usable list and priority order."""
        self._preferred_set = set(preferred)
        ordered   = [k for k in preferred if k in set(usable)]
        remainder = [k for k in usable if k not in self._preferred_set]

        for k in ordered + remainder:
            if k in MERSPECT_M20_COLOR_MAPPINGS:
                self._palette.append(hex_to_rgb(MERSPECT_M20_COLOR_MAPPINGS[k]))
                self._name_palette.append(k)

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
        """Reserve color names so they are not returned by :meth:`next`."""
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
        """Place a specific color at the front of the allocation queue."""
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
        """Return an unqueued color, prioritizing preferred colors."""
        if name in self._deque_names():
            return
        if name in self._preferred_set:
            self._deque.appendleft((color, name))
        else:
            self._deque.append((color, name))

    def consume(self, name: str):
        """Remove a directly assigned color from the allocation queue."""
        self._deque = deque(e for e in self._deque if e[1] != name)

    def reset(self):
        self._reserved = set()
        self._rebuild_deque()

    def set_instrument(self, instrument):
        """Rebuild the palette for a new instrument. Clears all reserved state."""
        self._palette          = []
        self._name_palette     = []
        self._merspect_indices = {}
        self._preferred_set    = set()
        self._reserved         = set()
        self._init_palette(instrument)
