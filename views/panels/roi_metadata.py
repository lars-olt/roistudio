"""Per-ROI metadata assignment panel.

Fields are declared in METADATA_FIELDS - key, label, options, and an optional
visibility predicate on the other values. The cards render whatever the schema
says, so adding or gating a category is a schema edit, not a UI change. Values
live on each roi_data dict under 'metadata' and are written into FITS headers
verbatim on export.
"""

from dataclasses import dataclass
from functools import partial
from typing import Callable, Optional, Tuple, Dict

from PyQt5.QtCore import Qt, QEvent, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QLineEdit, QScrollArea, QSizePolicy)

from colors import Colors
from utils.scale import Scale, scaled, scaled_font


@dataclass(frozen=True)
class MetadataField:
    key:          str                        # FITS header keyword (max 8 chars)
    label:        str                        # shown next to the editor
    options:      Tuple[str, ...] = ()       # allowed values; empty means free text
    hints:        Optional[Dict[str, str]] = None       # value -> display label overrides
    visible_when: Optional[Callable[[dict], bool]] = None


def _is_rock(m):  return m.get('FEATURE') == 'Rock'
def _is_soil(m):  return m.get('FEATURE') == 'Soil'
def _is_other(m): return m.get('FEATURE') == 'Other'
def _is_nearfield_soil(m): return _is_soil(m) and m.get('DISTANCE') == 'Nearfield'


# Pancam starting categories. Distance is best effort - actual distance can be
# used to filter in Multidex. DESCRIPT is free text for identifiers the fixed
# categories don't cover (e.g. "scree slope", "candidate meteorite").
METADATA_FIELDS = (
    MetadataField('DISTANCE', 'Distance', ('Nearfield', 'Midfield', 'Farfield'),
                  hints={'Nearfield': 'Nearfield (< 10 m)',
                         'Midfield':  'Midfield (10 m - 50 m)',
                         'Farfield':  'Farfield (> 50 m)'}),
    MetadataField('FEATURE', 'Feature', ('Rock', 'Soil', 'Other', 'Hardware')),
    MetadataField('FLOAT', 'Float', ('Float', 'In-Place', 'Unclear'),
                  visible_when=_is_rock),
    MetadataField('ROCKSURF', 'Rock surface', (
        'Bright natural surface', 'Dark natural surface', 'Thick dust',
        'LIBS-cleared surface', 'gDRT-cleared surface', 'Abraded surface',
        'Coating (not dust)', 'Clast/Inclusion', 'Tailings', 'Broken/scuffed',
    ), visible_when=_is_rock),
    MetadataField('GRAINSZ', 'Grain size', ('Fine', 'Coarse', 'Mixed'),
                  hints={'Fine':   'Fine (grains not resolvable)',
                         'Coarse': 'Coarse (grains resolvable)'},
                  visible_when=_is_nearfield_soil),
    MetadataField('SOILLOC', 'Soil location', (
        'Undisturbed regolith', 'On rock', 'Wheel track compressed',
        'Wheel track disturbed', 'Disturbed surface (not wheel track)',
        'Bedform', 'On hardware',
    ), visible_when=_is_soil),
    MetadataField('FEATTYPE', 'Feature type', ('Blueberry', 'Vein'),
                  visible_when=_is_other),
    MetadataField('DESCRIPT', 'Description'),
)

_UNSET = ''  # combo userData for the blank option


class _MetadataCard(QFrame):
    """One ROI's metadata editor - colored left strip, accent border when active."""

    activated = pyqtSignal(int)
    changed   = pyqtSignal(int, dict)

    def __init__(self, index, color, name, metadata, parent=None):
        super().__init__(parent)
        self.index     = index
        self._color    = color
        self._name     = name
        self._metadata = dict(metadata)
        self._active   = False
        self._editors  = {}   # field key -> editor widget
        self._rows     = {}   # field key -> row container widget

        self.setObjectName('card')
        self._build_ui()
        self._sync_visibility()
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

        for field in METADATA_FIELDS:
            row      = QWidget()
            row_lay  = QHBoxLayout()
            row_lay.setContentsMargins(0, 0, 0, 0)
            row.setLayout(row_lay)

            label = QLabel(field.label)
            row_lay.addWidget(label)
            row._label = label

            if field.options:
                editor = QComboBox()
                editor.addItem('-', _UNSET)
                hints = field.hints or {}
                for value in field.options:
                    editor.addItem(hints.get(value, value), value)
                current = self._metadata.get(field.key)
                if current is not None:
                    ix = editor.findData(current)
                    if ix >= 0:
                        editor.setCurrentIndex(ix)
                self._mark_current(editor)
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
        self._drop_hidden_values()
        self._sync_visibility()
        self.changed.emit(self.index, dict(self._metadata))

    def _drop_hidden_values(self):
        """Clear values of fields the current selections have hidden."""
        for field in METADATA_FIELDS:
            if field.visible_when is None or field.visible_when(self._metadata):
                continue
            if field.key not in self._metadata:
                continue
            self._metadata.pop(field.key)
            editor = self._editors[field.key]
            editor.blockSignals(True)
            if isinstance(editor, QComboBox):
                editor.setCurrentIndex(0)
                self._mark_current(editor)
            else:
                editor.clear()
            editor.blockSignals(False)

    def _sync_visibility(self):
        for field in METADATA_FIELDS:
            visible = field.visible_when is None or field.visible_when(self._metadata)
            self._rows[field.key].setVisible(visible)

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
        # Focusing any field claims the card, so editing and canvas highlight
        # always agree on which ROI is being described.
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

    def set_rois(self, rois_data, colors, names):
        """Rebuild the card list from current ROIs, preserving the active card by name."""
        active_name = (self._cards[self._active_index]._name
                       if self._cards and self._active_index < len(self._cards) else None)

        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._empty_label:
                w.deleteLater()

        self._cards = []
        for i, (roi, color, name) in enumerate(zip(rois_data, colors, names)):
            card = _MetadataCard(i, color, name, roi.get('metadata', {}))
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