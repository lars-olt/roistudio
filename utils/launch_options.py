"""Command-line overrides for persisted user-interface settings."""

import argparse


def _bounded_float(minimum, maximum):
    def parse(value):
        number = float(value)
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(
                f"must be between {minimum} and {maximum}"
            )
        return number
    return parse


def _positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _upper_left_panel(value):
    """Accept the former panel name while normalizing it to Settings."""
    if value == 'roi-processing':
        return 'settings'
    if value in ('scene-loading', 'settings', 'roi-metadata'):
        return value
    raise argparse.ArgumentTypeError(
        "must be one of: scene-loading, settings, roi-metadata"
    )


def add_ui_arguments(parser):
    group = parser.add_argument_group(
        'UI overrides',
        'Override saved UI state for this launch.',
    )
    group.add_argument(
        '--ui-scale',
        type=_bounded_float(0.5, 3.0),
        help='GUI scale multiplier used by Ctrl+/- (0.5 to 3.0)',
    )
    group.add_argument(
        '--window-size',
        nargs=2,
        type=_positive_int,
        metavar=('WIDTH', 'HEIGHT'),
        help='window size in pixels',
    )
    group.add_argument(
        '--window-position',
        nargs=2,
        type=int,
        metavar=('X', 'Y'),
        help='window position in screen coordinates',
    )
    group.add_argument(
        '--maximized',
        action=argparse.BooleanOptionalAction,
        default=None,
        help='start with the window maximized',
    )
    group.add_argument(
        '--left-panel-ratio',
        type=_bounded_float(0.05, 0.95),
        help='fraction of the window occupied by the left panel',
    )
    group.add_argument(
        '--upper-panel-ratio',
        type=_bounded_float(0.05, 0.95),
        help='fraction of the left column occupied by its upper panel',
    )
    group.add_argument(
        '--upper-left-panel',
        type=_upper_left_panel,
        metavar='{scene-loading,settings,roi-metadata}',
        help='panel shown in the upper-left area',
    )
    for key, label in (
        ('view-settings', 'View Settings'),
        ('segmentation', 'Segmentation'),
        ('roi-extraction', 'ROI Extraction'),
        ('spectral-analysis', 'Spectral Analysis'),
    ):
        group.add_argument(
            f'--{key}-section',
            choices=('expanded', 'collapsed'),
            help=f'start the {label} section expanded or collapsed',
        )
    group.add_argument(
        '--roi-labels',
        action=argparse.BooleanOptionalAction,
        default=None,
        help='show ROI labels',
    )
    group.add_argument(
        '--spectral-y-min',
        type=_bounded_float(-0.1, 1.0),
        help='spectral plot Y-axis minimum (-0.1 to 1.0)',
    )
    group.add_argument(
        '--spectral-y-max',
        type=_bounded_float(0.0, 5.0),
        help='spectral plot Y-axis maximum (0.0 to 5.0)',
    )
    group.add_argument(
        '--spectral-line-width',
        type=_bounded_float(0.5, 3.0),
        help='spectral plot line width (0.5 to 3.0)',
    )
    group.add_argument(
        '--merge-spectra',
        action=argparse.BooleanOptionalAction,
        default=None,
        help='merge left and right camera spectra',
    )


def apply_scale_override(args):
    if args.ui_scale is not None:
        from .scale import Scale
        Scale.set_scale(args.ui_scale)


def apply_view_overrides(args, view):
    """Apply only explicitly provided values, after persisted state is restored."""
    if args.window_size is not None:
        view.resize(*args.window_size)
    if args.window_position is not None:
        view.move(*args.window_position)
    if args.maximized is not None:
        from PyQt5.QtCore import Qt
        state = view.windowState() & ~Qt.WindowMinimized
        if args.maximized:
            state |= Qt.WindowMaximized
        else:
            state &= ~Qt.WindowMaximized
        view.setWindowState(state)

    view.set_panel_ratios(
        left=args.left_panel_ratio,
        upper=args.upper_panel_ratio,
    )
    if args.upper_left_panel is not None:
        view.set_mode(args.upper_left_panel.replace('-', '_'))
    if args.roi_labels is not None:
        view.set_roi_labels_visible(args.roi_labels)

    section_states = {}
    for key in (
        'view_settings',
        'segmentation',
        'roi_extraction',
        'spectral_analysis',
    ):
        state = getattr(args, f'{key}_section')
        if state is not None:
            section_states[key] = state == 'expanded'
    view.panel_settings.apply_section_states(section_states)
    view.panel_settings.apply_display_preferences(
        y_min=args.spectral_y_min,
        y_max=args.spectral_y_max,
        line_width=args.spectral_line_width,
        merge_spectra=args.merge_spectra,
    )
