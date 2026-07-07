"""Named color/band presets, keyed by instrument.

The single source of truth for band presets - the View menu, the stretch bar
overlays, and context export all read from here. Each entry: camera side,
preset label, R/G/B band names, DCS flag.
"""

INSTRUMENT_PRESETS = {
    'ZCAM': {
        'right': {
            'RGB': {'r': 'R0R', 'g': 'R0G', 'b': 'R0B', 'dcs': False},
            'DCS': {'r': 'R6',  'g': 'R3',  'b': 'R1',  'dcs': True},
        },
        'left': {
            'RGB': {'r': 'L0R', 'g': 'L0G', 'b': 'L0B', 'dcs': False},
            'DCS': {'r': 'L2',  'g': 'L5',  'b': 'L6',  'dcs': True},
        },
    },
    'PCAM': {
        'right': {
            'RGB': {'r': 'R2', 'g': 'R1', 'b': 'R1', 'dcs': False},
            'DCS': {'r': 'R7', 'g': 'R5', 'b': 'R3', 'dcs': True},
        },
        'left': {
            'RGB': {'r': 'L2', 'g': 'L5', 'b': 'L7', 'dcs': False},
            'DCS': {'r': 'L2', 'g': 'L5', 'b': 'L7', 'dcs': True},
        },
    },
}