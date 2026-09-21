"""Summary slide rendering - a one-page PDF summarizing an observation's ROIs.

The slide is a 2x2 grid: two annotated eye images, the spectra plot, and a
table of the sPDL's per-ROI metadata.

The caller picks the three panels and their captions. Pancam has left eye DCS
and the right in RGB, Mastcam-Z has left RGB and right DCS, and both have
a spectra plot and metadata table.

The page is sized to the panels. Cells are a fixed width and each row is as tall 
as its own images need to eliminate whitespace. Images are never cropped or
enlarged past native size. A scene can have one ROI per palette colour, and the
table's type is sized so fifteen fit a cell; anything beyond that spills onto a
second page rather than being truncated.
"""

import os

import matplotlib.image as mpimg
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

# The first three cells are images; the fourth is always the ROI table.
_PANEL_CELLS   = 3
_TABLE_CAPTION = "ROI metadata"

_CELL_PX    = 1039
_DPI        = 100
_MARGIN_PX  = 8
_GAP_PX     = 8
_TITLE_PX   = 52
_CAPTION_PX = 30

_BG          = 'white'
_TITLE_C     = '#1a1a1a'
_SUB_C       = '#555555'
_CAPTION_C   = '#444444'
_BODY_C      = '#222222'
_MUTED_C     = '#999999'
_RULE_C      = '#dddddd'
_ROW_RULE_C  = '#f0f0f0'
_SWATCH_EC   = '#666666'
_TITLE_FS       = 30
_SUB_FS         = 17
_CAPTION_FS     = 17
_PLACEHOLDER_FS = 24

# Row geometry for the metadata table, in pixels within its cell.
_TABLE_HEAD_PX = 46
_ROWS_PER_CELL = 15
_ROW_STRETCH   = 2.0
# Body point size as a fraction of row height in pixels.
_BODY_FS_RATIO = 0.36
_BODY_FS_MIN   = 11
_GUTTER_CHARS  = 2
_SWATCH_PX     = 26
_SWATCH_GAP_PX = 8
# The swatch and its gap come out of the ROI column's text budget, so the
# column has to be widened by roughly their width or long names ellipsize.
_SWATCH_CHARS  = 4
_UNKNOWN_COLOR = (0.50, 0.50, 0.50)
_CHAR_W_RATIO  = 0.6

_DISTANCE_KEY     = 'DISTANCE'
_DISTANCE_ABBREV  = {'nearfield': 'near', 'midfield': 'mid', 'farfield': 'far'}
_HEADER_OVERRIDES = {_DISTANCE_KEY: 'Dist'}

_SUB_SEPARATOR = " | "
_ELLIPSIS      = "..."


def _fitted_height(size):
    """How tall a (width, height) image lands in a cell"""
    if not size:
        return None
    w, h = size
    if not w or not h:
        return None
    return h * min(1.0, _CELL_PX / w)


class _Page:
    """Geometry for one slide, in top-left-origin pixels."""

    def __init__(self, panel_sizes=()):
        sizes = list(panel_sizes)[:_PANEL_CELLS]
        sizes += [None] * (_PANEL_CELLS - len(sizes))
        top    = [h for h in (_fitted_height(s) for s in sizes[:2]) if h]
        bottom = [h for h in (_fitted_height(s) for s in sizes[2:]) if h]
        self.rows = (max(top, default=_CELL_PX), max(bottom + [_CELL_PX]))
        self.width  = _MARGIN_PX * 2 + _CELL_PX * 2 + _GAP_PX
        self.height = (_MARGIN_PX * 2 + _TITLE_PX + _GAP_PX
                        + sum(_CAPTION_PX + h for h in self.rows))

    def rect(self, x, y, w, h):
        """Convert a pixel box to matplotlib's bottom-left figure fractions."""
        return [x / self.width, 1.0 - (y + h) / self.height,
                w / self.width, h / self.height]

    def text(self, fig, x, y, s, **kw):
        """Place text using top-left-origin pixel coordinates."""
        return fig.text(x / self.width, 1.0 - y / self.height, s, **kw)

    def cell(self, index):
        """(x, caption_y, height) for cell `index`, 0-3 in reading order.

        The cell itself starts _CAPTION_PX below caption_y."""
        row, col = divmod(index, 2)
        x = _MARGIN_PX + col * (_CELL_PX + _GAP_PX)
        y = _MARGIN_PX + _TITLE_PX + sum(
            _CAPTION_PX + self.rows[r] + _GAP_PX for r in range(row))
        return x, y, self.rows[row]

    def figure(self):
        fig = Figure(figsize=(self.width / _DPI, self.height / _DPI),
                    dpi=_DPI, facecolor=_BG)
        FigureCanvasAgg(fig)
        return fig


def _cell_axes(page, fig, x, y, w, h):
    """A blank axes covering a cell, with a 0-1 coordinate space to draw into."""
    ax = fig.add_axes(page.rect(x, y, w, h))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_axis_off()
    return ax


def _draw_image(page, fig, img, x, y, cell_h):
    """Place an image at native size, centred in its cell."""
    img_h, img_w = img.shape[0], img.shape[1]
    scale = min(1.0, _CELL_PX / img_w, cell_h / img_h)
    w, h = img_w * scale, img_h * scale
    ax = fig.add_axes(page.rect(x + (_CELL_PX - w) / 2, y + (cell_h - h) / 2, w, h))
    ax.imshow(img, interpolation='none' if scale == 1.0 else 'antialiased')
    ax.set_axis_off()


def _draw_placeholder(page, fig, x, y, w, h, message):
    ax = _cell_axes(page, fig, x, y, w, h)
    ax.text(0.5, 0.5, message, ha='center', va='center',
            fontsize=_PLACEHOLDER_FS, color=_MUTED_C)
    ax.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor=_RULE_C, linewidth=0.8))


def _display_value(key, raw):
    """A field's value as it should read in the table."""
    value = str(raw or '').strip()
    if key == _DISTANCE_KEY:
        return _DISTANCE_ABBREV.get(value.lower(), value)
    return value


def _header_label(key, label):
    """A column's heading. Overridden where the panel's own label is wider than
    the values under it and would set the column width on its own."""
    return str(_HEADER_OVERRIDES.get(key, label) or key)


def _roi_color(roi):
    """An ROI's swatch colour, as a 0-1 RGB triple."""
    color = roi.get('color')
    if not color:
        return _UNKNOWN_COLOR
    return tuple(color)[:3]


def _column_chars(columns, rois):
    """Character width each column needs: its heading, or its longest value."""
    def longest(key):
        return max((len(_display_value(key, r.get(key))) for r in rois), default=0)

    name_col = _SWATCH_CHARS + max(
        len("ROI"), max((len(str(r.get('name', ''))) for r in rois), default=0))
    return [name_col] + [max(len(_header_label(key, label)), longest(key))
                        for key, label in columns]


def _column_layout(chars, width_px):
    """Split a cell's width into columns proportional to the text each holds"""
    weights = [c + _GUTTER_CHARS for c in chars]
    total = sum(weights) or 1.0
    xs, cursor = [], 0.0
    for w in weights:
        xs.append(cursor)
        cursor += width_px * w / total
    return xs, [width_px * w / total for w in weights]


def _fitted_body_fs(chars, row_px, width_px):
    """The largest allowable size.

    Below _BODY_FS_MIN the width constraint is abandoned rather than
    shrinking further, and _ellipsize trims what still doesn't fit."""
    by_row = row_px * _BODY_FS_RATIO
    needed = sum(c + _GUTTER_CHARS for c in chars) or 1
    usable = max(1.0, width_px - _SWATCH_PX - _SWATCH_GAP_PX)
    by_width = usable / (needed * _CHAR_W_RATIO * (_DPI / 72.0))
    return max(_BODY_FS_MIN, min(by_row, by_width))


def _ellipsize(text, width_px, fontsize):
    """Trim to what fits a column.

    fontsize is in points and width_px in pixels, so the point size is converted
    at the page's _DPI first."""
    char_px = fontsize * (_DPI / 72.0) * _CHAR_W_RATIO
    max_chars = max(4, int(width_px / char_px))
    if len(text) <= max_chars:
        return text
    return text[:max(1, max_chars - len(_ELLIPSIS))] + _ELLIPSIS


def _draw_roi_table(page, fig, x, y, rois, columns, sub_fields, w, h, start=0):
    """Draw as many ROI rows as fit, returning the index of the first that didn't."""
    ax = _cell_axes(page, fig, x, y, w, h)
    ax.add_patch(Rectangle((0, 0), 1, 1, fill=False, edgecolor=_RULE_C, linewidth=0.8))

    if not rois:
        ax.text(0.5, 0.5, "No ROIs recorded for this scene",
                ha='center', va='center', fontsize=_PLACEHOLDER_FS, color=_MUTED_C)
        return len(rois)

    remaining = len(rois) - start
    avail = h - _TABLE_HEAD_PX
    # Base height is whatever fits _ROWS_PER_CELL, and the type is sized to it
    base_row_px = avail / _ROWS_PER_CELL
    row_px = max(base_row_px, min(base_row_px * _ROW_STRETCH, avail / max(1, remaining)))
    fits = max(1, int(avail / row_px + 1e-9))
    end = min(len(rois), start + fits)

    shown = rois[start:end]
    chars = _column_chars(columns, shown)
    xs, widths = _column_layout(chars, w)
    body_fs = _fitted_body_fs(chars, base_row_px, w)
    head_fs = body_fs
    sub_fs = body_fs * 0.78
    indent = xs[0] + _SWATCH_PX + _SWATCH_GAP_PX

    def tx(px):      # pixel offset within the cell -> axes fraction
        return px / w

    def ty(px):
        return 1.0 - px / h

    for i, (key, label) in enumerate(columns):
        ax.text(tx(xs[i + 1]), ty(_TABLE_HEAD_PX * 0.55), _header_label(key, label),
                fontsize=head_fs, color=_CAPTION_C, ha='left', va='center')
    ax.text(tx(xs[0]), ty(_TABLE_HEAD_PX * 0.55), "ROI",
            fontsize=head_fs, color=_CAPTION_C, ha='left', va='center')
    ax.plot([0, 1], [ty(_TABLE_HEAD_PX)] * 2, color=_RULE_C, linewidth=0.8)

    for n, roi in enumerate(shown):
        top = _TABLE_HEAD_PX + n * row_px
        mid = ty(top + row_px * 0.34)

        ax.add_patch(Rectangle(
            (tx(xs[0]), mid - (_SWATCH_PX / h) / 2), _SWATCH_PX / w, _SWATCH_PX / h,
            facecolor=_roi_color(roi), edgecolor=_SWATCH_EC, linewidth=0.5,
        ))
        ax.text(tx(indent), mid,
                _ellipsize(str(roi.get('name', '')),
                            widths[0] - _SWATCH_PX - _SWATCH_GAP_PX, body_fs),
                fontsize=body_fs, color=_BODY_C, ha='left', va='center')

        for i, (key, _label) in enumerate(columns):
            value = _display_value(key, roi.get(key))
            if not value:
                continue
            ax.text(tx(xs[i + 1]), mid, _ellipsize(value, widths[i + 1], body_fs),
                    fontsize=body_fs, color=_BODY_C, ha='left', va='center')

        # The sub-line fields share one line under the row.
        extra = [v for v in (_display_value(k, roi.get(k)) for k, _ in sub_fields) if v]
        if extra:
            ax.text(tx(indent), ty(top + row_px * 0.74),
                    _ellipsize(_SUB_SEPARATOR.join(extra), w - indent - _GUTTER_CHARS, sub_fs),
                    fontsize=sub_fs, color=_SUB_C, ha='left', va='center', style='italic')

        if n:
            ax.plot([0, 1], [ty(top)] * 2, color=_ROW_RULE_C, linewidth=0.5)

    return end


def _overflow_page(page, title, rois, columns, sub_fields, start):
    """A full-width continuation table for scenes with more ROIs than the 2x2
    cell holds. Same page size as the first, so the PDF stays uniform."""
    fig = page.figure()
    page.text(fig, _MARGIN_PX, _MARGIN_PX + _TITLE_PX * 0.42,
                f"{title} ROI metadata (continued)",
                fontsize=_TITLE_FS - 4, color=_TITLE_C, ha='left', va='center')
    width  = page.width - _MARGIN_PX * 2
    height = page.height - _MARGIN_PX * 2 - _TITLE_PX
    _draw_roi_table(page, fig, _MARGIN_PX, _MARGIN_PX + _TITLE_PX, rois,
                    columns, sub_fields, width, height, start=start)
    return fig


def _load_panels(panels):
    """Decode the panel images so the page can be sized to them.

    Returns [(array or None, caption)]. A path that isn't there yields None and
    renders as a placeholder."""
    return [(mpimg.imread(path) if path and os.path.isfile(path) else None, caption)
            for path, caption in panels]


def _write_slide(figures, dest):
    """Save to a temp name in the destination directory, then replace the real
    file. Prevents a half-written slide landing in a shared directory."""
    os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
    fmt = os.path.splitext(dest)[1].lstrip('.').lower() or 'pdf'
    tmp = f"{dest}.{os.getpid()}.tmp"
    try:
        if fmt == 'pdf':
            with PdfPages(tmp) as pdf:
                for fig in figures:
                    pdf.savefig(fig, facecolor=fig.get_facecolor())
        else:
            figures[0].savefig(tmp, format=fmt, facecolor=figures[0].get_facecolor())
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def build_slide(dest, title, subtitle, panels, rois, columns, sub_fields):
    """Render a summary slide to `dest` and return that path."""
    cells = list(panels[:_PANEL_CELLS])
    cells += [(None, "")] * (_PANEL_CELLS - len(cells))
    loaded = _load_panels(cells)
    page = _Page([(img.shape[1], img.shape[0]) if img is not None else None
                    for img, _caption in loaded])

    fig = page.figure()
    # Title and subtitle share one line with name left and the scene's identifiers
    # aligned right.
    title_y = _MARGIN_PX + _TITLE_PX * 0.55
    page.text(fig, _MARGIN_PX, title_y, str(title),
                fontsize=_TITLE_FS, color=_TITLE_C, ha='left', va='center')
    if subtitle:
        page.text(fig, page.width - _MARGIN_PX, title_y, str(subtitle),
                    fontsize=_SUB_FS, color=_SUB_C, ha='right', va='center')

    overflow_from = None
    for i, (img, caption) in enumerate(loaded + [(None, _TABLE_CAPTION)]):
        x, y, cell_h = page.cell(i)
        page.text(fig, x + 4, y + _CAPTION_PX * 0.65, caption,
                    fontsize=_CAPTION_FS, color=_CAPTION_C, ha='left', va='center')
        cell_y = y + _CAPTION_PX

        if i == _PANEL_CELLS:
            drawn = _draw_roi_table(page, fig, x, cell_y, rois,
                                    columns, sub_fields, _CELL_PX, cell_h)
            if drawn < len(rois):
                overflow_from = drawn
        elif img is not None:
            _draw_image(page, fig, img, x, cell_y, cell_h)
        else:
            _draw_placeholder(page, fig, x, cell_y, _CELL_PX, cell_h,
                                f"{caption}\nnot available")

    figures = [fig]
    if overflow_from is not None:
        figures.append(_overflow_page(page, title, rois, columns, sub_fields, overflow_from))

    _write_slide(figures, dest)
    return dest
