"""ROIStudio Lite entry point used by development and PyInstaller."""

from editions import LITE
from main import run


if __name__ == "__main__":
    run(LITE)

