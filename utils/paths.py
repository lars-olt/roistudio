"""
Path resolution utilities for frozen (PyInstaller) and development environments.
Imported by any module that needs to resolve asset or config paths.
Must not import from any other ROIStudio module to avoid circular imports.
"""

import sys
import os


def _resource_path(relative_path: str) -> str:
    """
    Resolve path to a bundled resource.

    In development: returns the path relative to the project root.
    When frozen by PyInstaller: returns the path relative to sys._MEIPASS
    (the temp folder where PyInstaller unpacks the bundle).
    """
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


def _get_config_path() -> str:
    """
    Resolve the writable config.yml path.

    config.yml needs to be read/write (the user sets the SAM path via the UI).
    sys._MEIPASS is read-only in a frozen bundle, so we store a writable copy
    in the user's app-data directory and seed it from the bundled default on
    first launch.
    """
    if not getattr(sys, "frozen", False):
        # Development: config.yml sits at the project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(project_root, "config.yml")

    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        app_data = os.path.expanduser("~/Library/Application Support")

    config_dir = os.path.join(app_data, "ROIStudio")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "config.yml")

    if not os.path.exists(config_path):
        bundled = os.path.join(sys._MEIPASS, "config.yml")
        if os.path.exists(bundled):
            import shutil
            shutil.copy2(bundled, config_path)

    return config_path