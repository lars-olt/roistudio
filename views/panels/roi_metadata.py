"""Per-ROI metadata assignment panel.

Fields are declared per instrument in MCZ_METADATA_FIELDS and
PCAM_METADATA_FIELDS - key, label, options, and an optional visibility
predicate on the other values. Options can be a callable on the metadata for
lists that depend on another field, like the Pancam feature subtype.
"""

import json
import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable, Optional, Tuple, Dict

from PyQt5.QtCore import Qt, QEvent, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QLineEdit, QScrollArea, QSizePolicy)

from colors import Colors
from utils.paths import _resource_path
from utils.scale import Scale, scaled, scaled_font


@dataclass(frozen=True)
class MetadataField:
    key:          str                        # FITS header keyword; astropy writes keys over 8 chars as HIERARCH cards
    label:        str                        # shown next to the editor
    options:      object = ()                # tuple of values, or a callable(metadata) -> tuple; empty means free text
    hints:        Optional[Dict[str, str]] = None       # value -> display label overrides
    visible_when: Optional[Callable[[dict], bool]] = None

    def options_for(self, metadata: dict) -> Tuple[str, ...]:
        return self.options(metadata) if callable(self.options) else self.options


def _is_rock(m): return m.get('FEATURE') == 'rock'
def _is_soil(m): return m.get('FEATURE') == 'soil'


_SOIL_SUBTYPES = (
    'undisturbed regolith', 'on rock', 'wheel track compressed',
    'wheel track disturbed', 'disturbed surface (not wheel track)',
    'bedform crest/slope', 'on hardware',
)

_ZCAM_SUBTYPES = {
    'rock': (
        'bright natural surface', 'dark natural surface', 'thick dust',
        'LIBS-cleared surface', 'gDRT-cleared surface', 'abraded surface',
        'coating (not dust)', 'clast/inclusion', 'tailings',
        'broken/scuffed surface',
    ),
    'soil': _SOIL_SUBTYPES,
}

_ZCAM_FORMATIONS = (
    'Maaz', 'Seitah', 'delta', 'margin unit', 'Neretva Vallis',
    'Crater Rim', 'Lac de Charmes',
)

# Only these formations have named members.
_ZCAM_MEMBERS = {
    'Maaz':   ('Chal', 'Nataani', 'Rochette', 'Artuby', 'Roubion'),
    'Seitah': ('Content', 'Bastide', 'Issole'),
}

_DISTANCE = MetadataField('DISTANCE', 'Distance', ('nearfield', 'midfield', 'farfield'),
                          hints={'nearfield': 'nearfield (< 10 m)',
                                 'midfield':  'midfield (10 m - 50 m)',
                                 'farfield':  'farfield (> 50 m)'})
_DESCRIPTION = MetadataField('DESCRIPTION', 'Description')


# Field keys, values, and gating mirror the marslab metadata settings - values
# are written to FITS headers verbatim.
MCZ_METADATA_FIELDS = (
    MetadataField('FEATURE', 'Feature', ('rock', 'soil', 'pebble', 'hardware', 'landscape')),
    MetadataField('FEATURE_SUBTYPE', 'Feature subtype',
                  lambda m: _ZCAM_SUBTYPES.get(m.get('FEATURE'), ()),
                  visible_when=lambda m: m.get('FEATURE') in _ZCAM_SUBTYPES),
    MetadataField('FLOAT', 'Float', ('float', 'in-place', 'unclear'), visible_when=_is_rock),
    MetadataField('FORMATION', 'Formation', _ZCAM_FORMATIONS, visible_when=_is_rock),
    MetadataField('GRAIN_SIZE', 'Grain size',
                  ('fine (grains not resolvable)', 'coarse (grains resolvable)', 'mixed'),
                  visible_when=_is_soil),
    MetadataField('MEMBER', 'Member',
                  lambda m: _ZCAM_MEMBERS.get(m.get('FORMATION'), ()),
                  visible_when=lambda m: _is_rock(m) and m.get('FORMATION') in _ZCAM_MEMBERS),
    _DISTANCE,
    _DESCRIPTION,
)


# Pancam metadata is defined in resources/pcam_roi_metadata.json.
_PCAM_SCHEMA_FILE = 'resources\pcam_roi_metadata.json'


def _condition(spec):
    """Convert a visible_when mapping into a predicate on the metadata dict.

    Every listed field must hold one of its listed values, e.g.
    {"FEATURE": ["rock"]}. A bare string value is accepted as a single option.
    """
    if not spec:
        return None
    checks = {key: tuple(vals) if isinstance(vals, list) else (vals,)
              for key, vals in spec.items()}
    return lambda m: all(m.get(key) in vals for key, vals in checks.items())


def _pcam_fields_from_json(path):
    """Build the Pancam schema from the editable JSON definition.

    Raises ValueError with a message precise enough to act on from GitHub's
    editor - the file is maintained by scientists, so a typo has to produce
    something better than a traceback.
    """
    spec   = json.loads(Path(path).read_text())
    fields = []
    seen   = set()
    referenced = set()

    for entry in spec.get('fields', []):
        missing = [k for k in ('key', 'label') if k not in entry]
        if missing:
            raise ValueError(f"field entry {entry!r} is missing {missing}")
        key = entry['key']
        if key in seen:
            raise ValueError(f"duplicate field key {key!r}")
        seen.add(key)
        referenced.update(entry.get('visible_when', {}))

        visible_when = _condition(entry.get('visible_when'))
        hints        = entry.get('hints')
        options      = entry.get('options', [])
        by           = entry.get('options_by_field')

        if by:
            if not isinstance(options, dict):
                raise ValueError(f"{key}: options_by_field requires options to be a map")
            referenced.add(by)
            choices = {value: tuple(opts) for value, opts in options.items()}

            def options_fn(m, by=by, choices=choices):
                return choices.get(m.get(by), ())

            def gated(m, by=by, choices=choices, also=visible_when):
                return m.get(by) in choices and (also is None or also(m))

            fields.append(MetadataField(key, entry['label'], options_fn, hints, gated))
        else:
            fields.append(MetadataField(key, entry['label'], tuple(options), hints, visible_when))

    unknown = referenced - seen
    if unknown:
        raise ValueError(f"visible_when/options_by_field reference undefined fields: {sorted(unknown)}")
    if not fields:
        raise ValueError("no fields defined")
    return tuple(fields)


def _load_pcam_fields():
    try:
        return _pcam_fields_from_json(_resource_path(_PCAM_SCHEMA_FILE))
    except Exception as e:
        print(f"roi_metadata: could not load {_PCAM_SCHEMA_FILE} - {e}", file=sys.stderr)
        return ()


PCAM_METADATA_FIELDS = _load_pcam_fields()


_INSTRUMENT_METADATA_FIELDS = {
    'ZCAM': MCZ_METADATA_FIELDS,
    'MCZ':  MCZ_METADATA_FIELDS,
    'PCAM': PCAM_METADATA_FIELDS,
}


def metadata_fields(instrument: str) -> Tuple[MetadataField, ...]:
    """Field schema for an instrument, defaulting to MCZ."""
    return _INSTRUMENT_METADATA_FIELDS.get(str(instrument).strip().upper(),
                                           MCZ_METADATA_FIELDS)


_UNSET = ''  # combo userData for the blank option


class _NoWheelComboBox(QComboBox):
    """Combo that ignores the scroll wheel, so scrolling the card list can't
    silently change a metadata value."""

    def wheelEvent(self, event):
        event.ignore()


class _MetadataCard(QFrame):
    """One ROI's metadata editor - colored left strip, accent border when active."""

    activated = pyqtSignal(int)
    changed   = pyqtSignal(int, dict)

    def __init__(self, index, color, name, metadata, schema, parent=None):
        super().__init__(parent)
        self.index     = index
        self._color    = color
        self._name     = name
        self._metadata = dict(metadata)
        self._schema   = schema
        self._active   = False
        self._editors  = {}   # field key -> editor widget
        self._rows     = {}   # field key -> row container widget

        self.setObjectName('card')
        self._build_ui()
        self._sync_schema()
        self._apply_scale()

    def _build_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self._strip = QWidget()
        layout.addWidget(self._strip)

        self._fields = QWidget()
        self._fields_layout = QVBoxLayout()
        self._fields.setLayout(self._fields_layout)
        layout.addWidget(self._fields, stretch=1)

        self._title = QLabel(self._name)
        self._fields_layout.addWidget(self._title)

        for field in self._schema:
            row      = QWidget()
            row_lay  = QHBoxLayout()
            row_lay.setContentsMargins(0, 0, 0, 0)
            row.setLayout(row_lay)

            label = QLabel(field.label)
            row_lay.addWidget(label)
            row._label = label

            if field.options:
                editor = _NoWheelComboBox()
                self._populate_combo(editor, field)
                editor.currentIndexChanged.connect(partial(self._on_combo_changed, field.key))
            else:
                editor = QLineEdit()
                editor.setText(self._metadata.get(field.key, ''))
                editor.textChanged.connect(partial(self._on_text_changed, field.key))

            editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            editor.installEventFilter(self)
            row_lay.addWidget(editor, stretch=1)

            self._editors[field.key] = editor
            self._rows[field.key]    = row
            self._fields_layout.addWidget(row)

    def _populate_combo(self, editor, field):
        """Fill a combo from the field's current options, keeping a valid stored value."""
        editor.blockSignals(True)
        editor.clear()
        editor.addItem('-', _UNSET)
        hints = field.hints or {}
        for value in field.options_for(self._metadata):
            editor.addItem(hints.get(value, value), value)
        current = self._metadata.get(field.key)
        if current is not None:
            ix = editor.findData(current)
            if ix >= 0:
                editor.setCurrentIndex(ix)
        self._mark_current(editor)
        editor.blockSignals(False)

    # ------------------------------------------------------------------
    # Field changes
    # ------------------------------------------------------------------

    def _on_combo_changed(self, key, _index):
        combo = self._editors[key]
        self._mark_current(combo)
        self._store(key, combo.currentData())

    @staticmethod
    def _mark_current(combo):
        """Show the set value in the accent color in the dropdown, matching the menus."""
        accent = QBrush(QColor(Colors.ACCENT))
        for i in range(combo.count()):
            is_current = i == combo.currentIndex() and combo.itemData(i) != _UNSET
            combo.setItemData(i, accent if is_current else None, Qt.ForegroundRole)

    def _on_text_changed(self, key, text):
        self._store(key, text.strip())

    def _store(self, key, value):
        if value:
            self._metadata[key] = value
        else:
            self._metadata.pop(key, None)
        self._sync_schema()
        self.changed.emit(self.index, dict(self._metadata))

    def _sync_schema(self):
        """Reconcile editors with the current values.

        Hides gated rows and drops their values, and refreshes option lists
        that depend on other fields, dropping any value the new list no
        longer contains.
        """
        for field in self._schema:
            editor  = self._editors[field.key]
            visible = field.visible_when is None or field.visible_when(self._metadata)
            self._rows[field.key].setVisible(visible)

            if not visible:
                if field.key in self._metadata:
                    self._metadata.pop(field.key)
                    self._reset_editor(editor)
                continue

            if callable(field.options) and isinstance(editor, QComboBox):
                options = field.options_for(self._metadata)
                if options != self._combo_options(editor):
                    if self._metadata.get(field.key) not in options:
                        self._metadata.pop(field.key, None)
                    self._populate_combo(editor, field)

    def _reset_editor(self, editor):
        editor.blockSignals(True)
        if isinstance(editor, QComboBox):
            editor.setCurrentIndex(0)
            self._mark_current(editor)
        else:
            editor.clear()
        editor.blockSignals(False)

    @staticmethod
    def _combo_options(editor):
        return tuple(editor.itemData(i) for i in range(1, editor.count()))

    # ------------------------------------------------------------------
    # Active state
    # ------------------------------------------------------------------

    def set_active(self, active: bool):
        self._active = active
        self._apply_scale()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._active:
            self.activated.emit(self.index)
        super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        # Focusing a field activates its card, keeping the canvas highlight
        # on the ROI being edited.
        if event.type() == QEvent.FocusIn and not self._active:
            self.activated.emit(self.index)
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _apply_scale(self):
        r      = scaled(4)
        border = Colors.ACCENT if self._active else Colors.DEFAULT_FEATURE
        self.setStyleSheet(f"""
            QFrame#card {{
                background-color: {Colors.PANEL_ACCENT};
                border: 1px solid {border};
                border-radius: {r}px;
            }}
        """)
        self._strip.setFixedWidth(scaled(6))
        self._strip.setStyleSheet(f"""
            background-color: rgb({self._color[0]}, {self._color[1]}, {self._color[2]});
            border-top-left-radius: {r}px;
            border-bottom-left-radius: {r}px;
        """)
        self._fields_layout.setContentsMargins(scaled(10), scaled(8), scaled(10), scaled(8))
        self._fields_layout.setSpacing(scaled(4))
        self._title.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {scaled_font(9)}pt; font-weight: bold;"
        )
        for row in self._rows.values():
            row.layout().setSpacing(scaled(6))
            row._label.setFixedWidth(scaled(90))
            row._label.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; font-size: {scaled_font(9)}pt;"
            )


class ROIMetadataPanel(QWidget):
    """Scrollable list of metadata cards, one per ROI, keyed by ROI color."""

    metadata_changed = pyqtSignal(int, dict)   # roi index, full metadata dict
    roi_activated    = pyqtSignal(int)         # index of the ROI being described

    def __init__(self):
        super().__init__()
        self._cards        = []
        self._active_index = 0
        self._build_ui()
        self._apply_scale()
        Scale.changed.connect(self._apply_scale)

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self._scroll)

        self._list           = QWidget()
        self._list_layout    = QVBoxLayout()
        self._list.setLayout(self._list_layout)
        self._scroll.setWidget(self._list)

        self._empty_label = QLabel("No ROIs yet - run SPARC, draw, or load ROIs to assign metadata.")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._list_layout.addWidget(self._empty_label)
        self._list_layout.addStretch()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_rois(self, rois_data, colors, names, instrument='ZCAM'):
        """Rebuild the card list from current ROIs, preserving the active card by name."""
        active_name = (self._cards[self._active_index]._name
                       if self._cards and self._active_index < len(self._cards) else None)
        schema = metadata_fields(instrument)

        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._empty_label:
                w.deleteLater()

        self._cards = []
        for i, (roi, color, name) in enumerate(zip(rois_data, colors, names)):
            card = _MetadataCard(i, color, name, roi.get('metadata', {}), schema)
            card.activated.connect(self._on_card_activated)
            card.changed.connect(self.metadata_changed.emit)
            self._cards.append(card)
            self._list_layout.addWidget(card)

        self._list_layout.addWidget(self._empty_label)
        self._empty_label.setVisible(not self._cards)
        self._list_layout.addStretch()

        if self._cards:
            restored = next((i for i, c in enumerate(self._cards) if c._name == active_name), 0)
            self._on_card_activated(restored)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_card_activated(self, index):
        self._active_index = index
        for card in self._cards:
            card.set_active(card.index == index)
        self.roi_activated.emit(index)

    def _apply_scale(self):
        self._list_layout.setContentsMargins(scaled(8), scaled(8), scaled(8), scaled(8))
        self._list_layout.setSpacing(scaled(6))
        self._empty_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {scaled_font(9)}pt;"
        )
        fs = scaled_font(9)
        self.setStyleSheet(f"""
            QScrollArea {{ background-color: {Colors.PANEL_BACKGROUND}; }}
            QWidget     {{ background-color: {Colors.PANEL_BACKGROUND}; }}
            QScrollBar:vertical {{
                background-color: {Colors.DEFAULT_FEATURE};
                width: {scaled(12)}px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {Colors.SUBTLE_PANEL_ACCENT};
                min-height: {scaled(20)}px;
                border-radius: {scaled(6)}px; margin: {scaled(2)}px;
            }}
            QScrollBar::handle:vertical:hover {{ background-color: {Colors.PANEL_ACCENT}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QComboBox, QLineEdit {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.DEFAULT_FEATURE};
                border-radius: {scaled(3)}px;
                padding: {scaled(2)}px {scaled(6)}px;
                font-size: {fs}pt;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.PANEL_BACKGROUND};
                color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT};
                font-size: {fs}pt;
            }}
        """)
        for card in self._cards:
            card._apply_scale()