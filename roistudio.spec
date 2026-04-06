# roistudio.spec
# PyInstaller spec for ROIStudio + SPARC
#
# Run from the ROIStudio project root with your .venv active:
#   pyinstaller roistudio.spec --clean
#
# OUTPUT: dist/ROIStudio/ (one-folder bundle)
# Do NOT use --onefile - torch DLLs make startup unbearably slow.

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(".")

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------

hidden_imports = [
    # --- PyQt5 ---
    "PyQt5",
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    "PyQt5.sip",

    # --- Matplotlib Qt backend ---
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_qt5",

    # --- Torch ---
    "torch",
    "torch.nn",
    "torch.nn.functional",
    "torch.cuda",
    "torch.jit",
    "torch.utils",
    "torch.utils.data",
    "torch._C",

    # --- SAM ---
    "segment_anything",
    "segment_anything.modeling",
    "segment_anything.utils",

    # --- Scientific stack ---
    "numpy",
    "scipy",
    "scipy.ndimage",
    "scipy.fft",
    "scipy.spatial",
    "cv2",
    "sklearn",
    "sklearn.cluster",
    "sklearn.mixture",
    "sklearn.preprocessing",
    "kneed",
    "psutil",

    # --- Mars-lab stack ---
    "marslab",
    "marslab.compat",
    "marslab.compat.mertools",
    "marslab.compat.xcam",
    "marslab.imgops",
    "marslab.imgops.imgutils",
    "marslab.imgops.masking",
    "marslab.bandset",
    "marslab.bandset.pancam",
    "rapid",
    "rapid.helpers",
    "asdf_settings",
    "asdf_settings.metadata",
    "asdf_settings.rapidlooks",
    "pdr",

    # --- Data / IO ---
    "pandas",
    "yaml",

    # --- ROIStudio utils ---
    "utils.paths",

    # --- SPARC package ---
    "sparc",
    "sparc.core",
    "sparc.core.functional",
    "sparc.core.config",
    "sparc.core.pipeline",
    "sparc.core.state",
    "sparc.core.result",
    "sparc.core.backends",
    "sparc.core.constants",
    "sparc.core.logging_utils",
    "sparc.data",
    "sparc.data.loading",
    "sparc.preprocessing",
    "sparc.preprocessing.calibration",
    "sparc.preprocessing.masking",
    "sparc.roi",
    "sparc.roi.extraction",
    "sparc.roi.filtering",
    "sparc.segmentation",
    "sparc.segmentation.sam_segmentation",
    "sparc.spectral",
    "sparc.spectral.analysis",
    "sparc.spectral.metrics",
    "sparc.utils",
    "sparc.utils.array_ops",
    "sparc.utils.geometry",
    "sparc.utils.io",
    "sparc.utils.pancam_helpers",
    "sparc.utils.sel_writer",
    "sparc.utils.threading",
    "sparc.visualization",
    "sparc.visualization.plotting",
]

# Collect all submodules of packages that use plugin/registry patterns
hidden_imports += collect_submodules("torch")
hidden_imports += collect_submodules("segment_anything")
hidden_imports += collect_submodules("sklearn")
hidden_imports += collect_submodules("scipy")
hidden_imports += collect_submodules("marslab")
hidden_imports += collect_submodules("rapid")
hidden_imports += collect_submodules("asdf_settings")

# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------

datas = []

# ROIStudio assets
datas += [
    ("graphics", "graphics"),
    ("config.yml", "."),
]

# SPARC package data - blank .sel templates required by sel_writer at runtime
datas += collect_data_files("sparc")

# Package data files
for pkg in ("matplotlib", "PyQt5", "cv2", "sklearn"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

for pkg in ("marslab", "rapid", "asdf_settings"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "jupyter",
        "notebook",
        "ipykernel",
        "pytest",
        "sphinx",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ROIStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,        # UPX corrupts torch DLLs
    console=False,    # Set True to see traceback during debugging
    icon=None,        # Add graphics/icon.ico when available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ROIStudio",
)

# macOS .app bundle
if sys.platform == "darwin":
    # MACOSX_DEPLOYMENT_TARGET is set by the CI workflow per-platform.
    # Locally it defaults to whatever the build machine supports.
    deployment_target = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "12.0")
    app = BUNDLE(
        coll,
        name="ROIStudio.app",
        bundle_identifier="com.marslab.roistudio",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleName": "ROIStudio",
            "LSMinimumSystemVersion": deployment_target,
        },
    )
