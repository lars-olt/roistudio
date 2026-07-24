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
        self._colors_by_name   = {}
        self._aliases          = {}
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
        self._aliases = {name.lower(): name for name in usable}

    def _init_pcam_palette(self):
        # MER label order, MCZ color lookup key, and ROIStudio display name.
        colors = [
            ('red',          'red-1',    'red'),
            ('light green',  'green',    'green'),
            ('light blue',   'blue',     'blue'),
            ('light cyan',   'cyan',     'cyan'),
            ('dark green',   'green-2',  'forest'),
            ('yellow',       'yellow',   'yellow'),
            ('light purple', 'magenta',  'magenta'),
            ('pink',         'red+2',    'salmon'),
            ('teal',         'cyan-2',   'teal'),
            ('goldenrod',    'orange-1', 'goldenrod'),
            ('sienna',       'orange-2', 'sienna'),
            ('dark blue',    'blue-2',   'navy'),
            ('bright red',   'red',      'scarlet'),
            ('dark red',     'red-2',    'maroon'),
            ('dark purple',  'purple',   'purple'),
            ('eraser',       None,       None),
        ]

        self._merspect_indices = {
            display: index
            for index, (_mer, _mcz, display) in enumerate(colors)
            if display
        }
        color_keys = {
            display: mcz
            for _mer, mcz, display in colors
            if display
        }
        usable = list(color_keys)

        # Handout follows the MER list.
        self._build_palette(usable, preferred=usable, color_keys=color_keys)

        # Accept MER and legacy MCZ names on import when they are unambiguous,
        # while always returning the ROIStudio display name.
        self._aliases = {display.lower(): display for display in usable}
        for mer, _mcz, display in colors:
            if display:
                self._aliases.setdefault(mer.lower(), display)
        for _mer, mcz, display in colors:
            if display:
                self._aliases.setdefault(mcz.lower(), display)

    def _build_palette(self, usable, preferred, color_keys=None):
        """Populate palette/name/preferred fields from a usable list and priority order."""
        color_keys = color_keys or {}
        self._preferred_set = set(preferred)
        ordered   = [k for k in preferred if k in set(usable)]
        remainder = [k for k in usable if k not in self._preferred_set]

        for name in ordered + remainder:
            color_key = color_keys.get(name, name)
            if color_key in MERSPECT_M20_COLOR_MAPPINGS:
                color = hex_to_rgb(MERSPECT_M20_COLOR_MAPPINGS[color_key])
                self._palette.append(color)
                self._name_palette.append(name)
                self._colors_by_name[name] = color

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
        return self._merspect_indices[self.resolve_name(name)]

    def name_for_merspect_index(self, index: int):
        """Return ROIStudio's name for a MERSpect label index."""
        return next(
            (name for name, value in self._merspect_indices.items()
             if value == index),
            None,
        )

    def resolve_name(self, name: str):
        """Resolve an ROIStudio, MER, or legacy MCZ name to ROIStudio's name."""
        if not name:
            return None
        return self._aliases.get(str(name).strip().lower())

    def color(self, name: str):
        """Return the RGB tuple for a recognized color name."""
        resolved = self.resolve_name(name)
        return self._colors_by_name.get(resolved)

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
        self._colors_by_name   = {}
        self._aliases          = {}
        self._preferred_set    = set()
        self._reserved         = set()
        self._init_palette(instrument)
