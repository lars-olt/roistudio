# roistudio.spec
# Parameterized PyInstaller spec for ROIStudio and ROIStudio Lite.
#
# Run from the ROIStudio project root with your .venv active:
#   ROISTUDIO_EDITION=full pyinstaller roistudio.spec --clean
#   ROISTUDIO_EDITION=lite pyinstaller roistudio.spec --clean
#
# Do not use --onefile: the full edition's torch DLLs make startup very slow.

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(".")
EDITION = os.environ.get("ROISTUDIO_EDITION", "full").strip().lower()
if EDITION not in {"full", "lite"}:
    raise ValueError("ROISTUDIO_EDITION must be 'full' or 'lite'")

IS_FULL = EDITION == "full"
PRODUCT_NAME = "ROIStudio" if IS_FULL else "ROIStudio Lite"
ENTRY_POINT = "main.py" if IS_FULL else "main_lite.py"
BUNDLE_IDENTIFIER = (
    "com.marslab.roistudio" if IS_FULL else "com.marslab.roistudio.lite"
)

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------

common_hidden_imports = [
    # --- PyQt5 ---
    "PyQt5",
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    "PyQt5.sip",

    # --- Matplotlib Qt backend ---
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_qt5",

    # --- Scientific stack ---
    "numpy",
    "scipy",
    "scipy.ndimage",
    "scipy.fft",
    "scipy.spatial",
    "skimage",
    "cv2",
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

    # --- Lightweight SPARC services used by both editions ---
    "sparc",
    "sparc.core",
    "sparc.core.constants",
    "sparc.data",
    "sparc.data.loading",
    "sparc.utils",
    "sparc.utils.geometry",
    "sparc.utils.pancam_helpers",
    "sparc.utils.sel_writer",
    "sparc.visualization",
    "sparc.visualization.plotting",
]

algorithm_hidden_imports = [
    "controllers.algorithm_controller",
    "controllers.sparc_callbacks",
    "workers.sparc_runner",

    # --- Torch / SAM ---
    "torch",
    "torch.nn",
    "torch.nn.functional",
    "torch.cuda",
    "torch.jit",
    "torch.utils",
    "torch.utils.data",
    "torch._C",
    "torchvision",
    "segment_anything",
    "segment_anything.modeling",
    "segment_anything.utils",

    # --- Algorithm scientific stack ---
    "sklearn",
    "sklearn.cluster",
    "sklearn.mixture",
    "sklearn.preprocessing",
    "kneed",
    "psutil",
    # --- SPARC algorithm package ---
    "sparc.core.functional",
    "sparc.core.config",
    "sparc.core.pipeline",
    "sparc.core.state",
    "sparc.core.result",
    "sparc.core.backends",
    "sparc.core.logging_utils",
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
    "sparc.utils.array_ops",
    "sparc.utils.io",
    "sparc.utils.threading",
]

hidden_imports = common_hidden_imports + (
    algorithm_hidden_imports if IS_FULL else []
)

# Collect all submodules of packages that use plugin/registry patterns
if IS_FULL:
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

# ROIStudio assets - graphics/ is collected recursively, picking up logo/ too
datas += [
    ("graphics", "graphics"),
    ("resources", "resources"),
]
if IS_FULL:
    datas.append(("config.yml", "."))

# SPARC package data - blank .sel templates required by sel_writer at runtime
datas += collect_data_files("sparc")

# Package data files
data_packages = ["matplotlib", "cv2"]
if IS_FULL:
    data_packages += ["PyQt5", "sklearn"]
for pkg in data_packages:
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

lite_excludes = [
    "torch",
    "torchvision",
    "segment_anything",
    "sklearn",
    "kneed",
    "psutil",
    "controllers.algorithm_controller",
    "controllers.sparc_callbacks",
    "workers.sparc_runner",
    "sparc.core.functional",
    "sparc.core.config",
    "sparc.core.pipeline",
    "sparc.core.sparc",
    "sparc.core.state",
    "sparc.core.result",
    "sparc.core.backends",
    "sparc.core.logging_utils",
    "sparc.preprocessing",
    "sparc.roi",
    "sparc.segmentation",
    "sparc.spectral",
    "sparc.utils.array_ops",
    "sparc.utils.threading",
]

a = Analysis(
    [ENTRY_POINT],
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
    ] + ([] if IS_FULL else lite_excludes),
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=PRODUCT_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,    # set True to see tracebacks during debugging
    icon="graphics/logo/logo.ico" if sys.platform == "win32" else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=PRODUCT_NAME,
)

# macOS .app bundle
if sys.platform == "darwin":
    deployment_target = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "12.0")
    app = BUNDLE(
        coll,
        name=f"{PRODUCT_NAME}.app",
        bundle_identifier=BUNDLE_IDENTIFIER,
        icon="graphics/logo/logo.icns",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleName": PRODUCT_NAME,
            "LSMinimumSystemVersion": deployment_target,
        },
    )
