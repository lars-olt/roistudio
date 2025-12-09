"""
centralized color palette for ROIStudio.
inspired by Adobe Premiere Pro.
"""

class Colors:
    """
    color constants for the application theme.
    """
    # main colors
    APP_BACKGROUND = "#161616"          # darkest - main window background
    PANEL_BACKGROUND = "#232323"        # panel backgrounds
    PANEL_ACCENT = "#313131"            # panel borders, splitters
    SUBTLE_PANEL_ACCENT = "#262626"     # subtle dividers
    DEFAULT_FEATURE = "#1D1D1D"         # default UI elements
    ACCENT = "#0985D0"                  # orange accent for selection/hover
    
    # text colors
    TEXT_PRIMARY = "#CCCCCC"            # main text
    TEXT_SECONDARY = "#999999"          # secondary text
    TEXT_DISABLED = "#666666"           # disabled text
    
    # derived colors
    ACCENT_HOVER = "#0AA0FC"            # lighter accent for hover
    ACCENT_PRESSED = "#076EAD"          # darker accent for pressed