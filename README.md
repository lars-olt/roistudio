# ROIStudio

[![CI](https://github.com/lars-olt/roistudio/actions/workflows/ci.yml/badge.svg)](https://github.com/lars-olt/roistudio/actions/workflows/ci.yml)

ROIStudio is a desktop GUI for running and interacting with SPARC, an algorithm that automatically selects spectrally distinct regions of interest (ROIs) in multispectral images from Mars rovers. It supports data from the Mastcam-Z (ZCAM) instrument on the Perseverance rover and the Pancam (PCAM) instrument on the Spirit and Opportunity rovers. ROIStudio Lite provides the same scene, manual ROI, spectra, and file I/O workflow without the automatic SPARC algorithm or its machine-learning dependencies.

---

## Table of Contents

- [Installation](#installation)
- [Experimental RoMa](#experimental-roma)
- [Interface Overview](#interface-overview)
- [Loading Scenes](#loading-scenes)
- [Running SPARC](#running-sparc)
- [Working with ROIs](#working-with-rois)
- [Spectral View](#spectral-view)
- [Split Screen Mode](#split-screen-mode)
- [Exporting and Loading SEL Files](#exporting-and-loading-sel-files)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Development](#development)

---

## Installation

ROIStudio can be installed either via the packaged executable or manually from source.

### Executable

Download the latest release for your platform from the [releases page](https://github.com/lars-olt/roistudio/releases). No Python installation required - just download, unzip, and run.

Each release contains two editions built from the same source:

- **ROIStudio** includes automatic SPARC ROI generation and requires a SAM checkpoint.
- **ROIStudio Lite** supports scene loading, manual ROI editing, spectra, and SEL/FITS import and export without Torch, Segment Anything, or SPARC's clustering dependencies.

### Install the source tools

Install [Git](https://git-scm.com/downloads), then install
[uv](https://docs.astral.sh/uv/getting-started/installation/) using the command for
your platform. Skip this if `git --version` and `uv --version` already work.
uv will download Python 3.11 when it creates the environment.

**Windows (PowerShell):**

```powershell
winget install --id astral-sh.uv -e
```

**macOS (Terminal):**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Reopen your terminal after installation and check `uv --version` before continuing.

### Manual Install

For RoMa, follow [Experimental RoMa](#experimental-roma) below instead.

After installing the source tools above, create the Python 3.11 environment:

```bash
git clone https://github.com/lars-olt/roistudio.git
git clone https://github.com/lars-olt/sparc.git

cd roistudio
uv sync --python 3.11
```

**GPU acceleration (optional)** - if you have a CUDA-compatible GPU, install PyTorch with CUDA support on top of the uv environment. Find the right command for your system and CUDA version at [pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/), then run it with `--force-reinstall`:

```bash
# example for CUDA 12.1 - replace cu121 with your version
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 --force-reinstall
```

Without this step ROIStudio will run in CPU mode, which is slower for segmentation but otherwise fully functional.

Activate `.venv` from the repository directory:

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS (Terminal):**

```bash
source .venv/bin/activate
```

If PowerShell blocks activation, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` and try again.
This applies only to the current terminal.

Launch from `roistudio` with:

```bash
python main.py
```

### Setting the SAM Model Path

ROIStudio requires a SAM model checkpoint to run the SPARC pipeline. Download `sam_vit_h_4b8939.pth` from the [Segment Anything repository](https://github.com/facebookresearch/segment-anything) and place it somewhere accessible. On first launch, go to **File > Set SAM Path** and point ROIStudio to the file. This path is saved between sessions, so you only need to do this once when you first launch the app.

<img width="1601" height="924" alt="Screenshot of the Set SAM Path file dialog" src="https://github.com/user-attachments/assets/bbea956e-be95-482f-af24-409dc4b382c0" />


---

## Experimental RoMa

RoMa is an experimental alternative to homography for aligning the left and
right images. ROIStudio uses SPARC’s implementation, and paired ROIs remain inscribed
rectangles. RoMa is available from source; packaged applications exclude it.

Supported platforms are **64-bit Windows (CPU or NVIDIA CUDA)** and **Apple
Silicon macOS (CPU or MPS)**. On Apple Silicon, use a native ARM64 terminal,
without Rosetta. Intel Macs lack the required PyTorch wheels; see the
[PyTorch support notice](https://dev-discuss.pytorch.org/t/pytorch-macos-x86-builds-deprecation-starting-january-2024/1690).

For a new setup, first [install Git and uv](#install-the-source-tools), then follow
the steps below. If RoMa already works, go straight to [launching](#5-launch-with-roma).

### 1. Create and activate the environment

Clone the source and install the pipeline dependencies:

```bash
git clone https://github.com/lars-olt/roistudio.git
git clone https://github.com/lars-olt/sparc.git
cd roistudio
uv sync --python 3.11 --inexact --no-install-package torch --no-install-package torchvision
```

Keep the two repositories beside each other. ROIStudio uses `../sparc` and
installs both applications into `roistudio/.venv`; no separate SPARC environment
is needed.

For an existing source installation, close any running app, skip cloning, and
run the `uv sync` command from `roistudio` to reuse its Python 3.11 `.venv`.
`--inexact` keeps extra packages. PyTorch is installed separately in the next
step because RoMa needs a newer version than the standard environment.

Activate `.venv` from the repository directory:

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS (Terminal):**

```bash
source .venv/bin/activate
```

If PowerShell blocks activation, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` and try again.
This applies only to the current terminal.

Keep this terminal open for the remaining steps. Check which Python is active:

```bash
python -c "import sys; print(sys.executable)"
```

The path must point inside this repository’s `.venv`.

### 2. Install PyTorch

Run **one** command for your platform:

**Windows — CPU:**

```bash
uv pip install --python .venv --reinstall "numpy<2" torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
```

**Windows — NVIDIA GPU:** requires a compatible GPU and an up-to-date NVIDIA
driver. The wheel includes the CUDA runtime.

```bash
uv pip install --python .venv --reinstall "numpy<2" torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
```

**macOS — Apple Silicon:** supports both CPU and MPS.

```bash
uv pip install --python .venv --reinstall "numpy<2" torch==2.6.0 torchvision==0.21.0
```

These use the [PyTorch 2.6 builds](https://pytorch.org/get-started/previous-versions/#v260).
`--reinstall` also handles switching an existing environment between CPU and CUDA.

### 3. Install requirements-roma.txt (required)

From `roistudio`, install RoMa into the same `.venv`:

```bash
uv pip install --python .venv -r ../sparc/requirements-roma.txt
```

Wait for installation to finish, then verify the import and selected device:

```bash
python -c "from romatch import roma_outdoor; from sparc.utils.device import resolve_device; print('RoMa device:', resolve_device('auto'))"
```

### 4. Prepare the model weights

**SAM:** download `sam_vit_h_4b8939.pth` from
[Segment Anything](https://github.com/facebookresearch/segment-anything#model-checkpoints)
and keep it in a permanent location. This checkpoint is required for automatic
ROI generation. Reuse your existing file if you already have it.

**RoMa:** the `roma_outdoor.pth` and `dinov2_vitl14_pretrain.pth` weights are
required, but download automatically when RoMa first loads a scene. Allow internet
access and several gigabytes of disk space for this first run. Installing
`requirements-roma.txt` installs the software; the weight download happens later.

PyTorch caches the weights outside `.venv`, normally in
`~/.cache/torch/hub/checkpoints` (`~` is your user folder). Existing weights in
that cache are reused across environments for the same user. To see the actual
cache folder, including any `TORCH_HOME` override, run:

```bash
python -c "from pathlib import Path; import torch; print(Path(torch.hub.get_dir()) / 'checkpoints')"
```

To download and check RoMa’s weights before launching, or before going offline,
run this once while connected. It uses CPU and reuses cached files:

```bash
python -c "from romatch import roma_outdoor; roma_outdoor(device='cpu', use_custom_corr=False); print('RoMa weights ready')"
```

Wait for `RoMa weights ready`. The local-correlation warning on Windows and macOS
is expected and does not prevent setup.

### 5. Launch with RoMa

From `roistudio`, with `.venv` active:

```bash
python main.py
```

Set **File > Set SAM Path** to your SAM checkpoint. In **Settings > Experimental
Alignment**, select **RoMa**, then load or reload a scene and press **Run**.
The first scene takes longer if weights still need to download.

Device selection defaults to `auto`: CUDA, then MPS, then CPU. To choose explicitly,
launch with `python main.py --device cpu`, `--device cuda`, or `--device mps`.
An unavailable requested GPU raises an error; unsupported MPS operations can
fall back to CPU.

This environment can also run SPARC from the terminal with `python -m sparc`.
See [SPARC’s terminal guide](https://github.com/lars-olt/sparc#terminal-use).

**On later launches:** open a terminal in the repository, activate `.venv` using
the command in step 1, and run the launch command above. Dependencies and cached
weights do not need reinstalling. Run `deactivate` when finished.

If you prefer to skip activation, use `uv run --no-sync python` in place of
`python`. Always include `--no-sync`: plain `uv run` or `uv sync` can restore the
standard pins and remove RoMa or downgrade PyTorch. If that happens, repeat
steps 2 and 3.

---

## Interface Overview

ROIStudio is divided into three main areas:

**Left panel (top)** — switches between Scene Loading (thumbnail grid), Settings (application display and ROI processing options), and ROI Metadata. Toggle between them from the **Window** menu.

**Left panel (bottom)** — the Spectral View, showing reflectance spectra for all active ROIs. Hover over the canvas to preview the spectrum at the cursor position.

**Right panel** — the image canvas with toolbar. This is where you view images, run SPARC, and draw or edit ROIs.

---

## Loading Scenes

Open a folder with **File > Open Folder**. ROIStudio auto-detects the instrument (ZCAM or PCAM) from the filenames and scans for all valid pointings.

Each thumbnail shows the sol, sequence ID, and observation index. Click a thumbnail to select it, or double-click to load it. You can also drag a thumbnail onto the canvas to load it directly.

Once loaded, the scene's RGB image appears in the canvas and the band selector overlay appears at the bottom of the canvas panel. (Highlighted in yellow below.)

<img width="1602" height="923" alt="Screenshot of a loaded scene with the band selector overlay visible" src="https://github.com/user-attachments/assets/29a48204-f387-4068-9a9f-e5ddf058056d" />

### Band Selection

The floating overlay at the bottom of the canvas lets you select which bands to display as R, G, and B. Use the **Preset** dropdown to quickly switch to a named stretch, or manually choose bands from the dropdowns.

<img width="258" height="99" alt="Screenshot of the band selector overlay with the preset dropdown open" src="https://github.com/user-attachments/assets/7ddb14a5-a0ec-488a-9c26-7e91104a2c12" />

The **View** menu also provides **Set all RGB** and **Set all DCS** options to apply a stretch to all visible canvases at once.

The zoom-level indicator is always visible. Use **Window > Zoom Context** (or `Z`) to show or hide the navigator thumbnail that appears when the scaled image is larger than its panel.

---

## Running SPARC

Switch to the **Settings** panel via **Window > Settings** to access the algorithm parameters for optional tuning.

<img width="1602" height="923" alt="Screenshot of the application Settings panel" src="https://github.com/user-attachments/assets/25728c21-ae4a-4682-b329-81df95e7d61e" />

> [!Note]
> For new users, we recommend leaving these as-is for now.

### Parameters

**Segmentation**
- **Preserve Background** - keep unclassified pixels rather than masking them.
- **Points/Side** - SAM sampling density. Higher values produce finer segmentation but are slower.
- **Pred IOU** - confidence threshold for SAM mask quality.

**ROI Extraction**
- **Edge Offset** - pixels eroded from segment boundaries to avoid edge artifacts.
- **Variance** - maximum allowed spectral variance within a region.
- **Area Threshold** - minimum segment size in pixels.
- **Albedo Ratio** - brightness similarity threshold between left and right camera bands.

**Spectral Analysis**
- **Max Clusters** - maximum number of spectral clusters the GMM may find.

Press **Run** to start the SPARC pipeline. Progress is shown in the status bar at the bottom of the window.

ZCAM scenes are displayed at full sensor size. SPARC trims the detector borders only for algorithm processing (25 pixels from each side and 11 from the top and bottom). A crop drawn in the canvas further restricts that processing area. Generated ROIs are moved back into full-image coordinates for viewing, editing, spectra, and export.

> [!Tip]
> When any intensive code is running, a spinning filter wheel will appear below the upper toolbar buttons.

<img width="1602" height="923" alt="Screenshot of the canvas after SPARC has run, with colored ROI rectangles overlaid on the image" src="https://github.com/user-attachments/assets/5c788b53-92f4-4f95-93de-2852010b356e" />
After running SPARC on a scene, you should see ROIs drawn on the canvas, and corresponding spectra plotted in the spectra view panel.

---

## Working with ROIs

### Tools

| Icon | Name | Shortcut | Description |
|------|------|----------|-------------|
| <img width="46" height="38" alt="toolbar_selection" src="https://github.com/user-attachments/assets/53756e7e-03ff-4341-b457-7a8fa682981b" /> | Selection | `V` | Select, move, and resize ROIs |
| <img width="46" height="38" alt="toolbar_rectangle (1)" src="https://github.com/user-attachments/assets/a04f7413-b98f-4fc8-87b1-d0179209545c" /> | Rectangle | `R` | Draw a new ROI |

### Drawing ROIs

Select the rectangle tool (`R`) and drag on the canvas to draw a new ROI. If the rectangle is too small it will not be created and a message will appear in the status log. New regions are paired into the other eye by default in both single- and split-screen mode. Turn off **Draw/delete both eyes** under **Settings > ROI Editing** to create a split-screen ROI only in the eye where you draw it.

### Selecting and Editing ROIs

With the selection tool (`V`), click an ROI to select it. Selected ROIs show corner and side handles. Drag a handle to resize, or drag the interior of the ROI to move. In split-screen mode, moving and resizing affect only the selected eye. `Delete` or `Backspace` removes the full paired region by default; turn off **Draw/delete both eyes** to remove only the active eye's rectangle. In single-screen mode, editing a paired region keeps its existing pairing and deletion removes that region record.

<img width="212" height="173" alt="Screenshot of a selected ROI" src="https://github.com/user-attachments/assets/6e3f50cd-3c8e-4d17-b318-595ae63fe032" />

### ROI Colors

The active color swatch in the toolbar shows the color that will be assigned to the next drawn ROI. Colors advance after every draw in both-eyes mode. With **Draw/delete both eyes** disabled, the color remains active until you have drawn its complementary ROI in the other eye. Click the swatch to choose a different color—including a color already in use—or to finish an intentional single-eye selection and move on.

<img width="136" height="111" alt="Screenshot of the color palette popup with swatches visible" src="https://github.com/user-attachments/assets/d1b0a3e7-bddb-4a86-b150-0b7d46cab748" />

Color is also the selection-class identity. Multiple rectangles with the same color remain independently editable, but share one metadata record, one aggregate spectrum, and one union mask per eye when exported. This makes it easy to add another region to an existing selection: choose its used color and draw again.

To change the selection class of an existing rectangle, right-click it and choose a color. The same popup also contains spectrum visibility controls.

### ROI Labels

Toggle **View > ROI Labels** to show or hide color name labels on each ROI.

### Editing ROI Metadata Options

Edit `resources/zcam_roi_metadata.json` for Mastcam-Z or
`resources/pcam_roi_metadata.json` for Pancam, then restart ROIStudio. Both use
the same schema, with fields displayed in the order listed:

- `key` is the metadata key used in FITS headers; `label` is the editor label.
- `options` lists dropdown values. An empty list creates a free-text field.
- `hints` optionally maps stored values to display labels.
- `visible_when` maps other field keys to the values that make this field visible.
- `options_by_field` names a parent field; `options` then maps its values to
  the available choices. List parent fields before their dependent fields.

---

## Spectral View

The spectral panel plots one aggregate reflectance spectrum (R* = IOF/cos θ) per active color selection class. Hover the cursor over the canvas with the rectangle tool to preview the pixel spectrum as a faint white line.

### View Settings

In the application **Settings** panel, the **View Settings** section controls:

- **Y-Axis Min/Max** - reflectance axis range.
- **Merge camera spectra** - average stereo bands into one spectrum, or plot left and right cameras separately.
- **Line Width** - thickness of spectrum lines.

The **ROI Editing** section controls:

- **Draw/delete both eyes** - when enabled (the default), drawing in either
  split-screen canvas also creates the mapped rectangle in the other
  eye, and deleting removes the paired region from both eyes. Disable it to draw
  or delete only in the active eye.

---

## Split Screen Mode

Click the split screen button at the bottom of the toolbar to view left and right camera images side by side.

| Icon | Description |
|------|-------------|
| <img width="46" height="38" alt="toolbar_single_screen (1)" src="https://github.com/user-attachments/assets/3891f9be-69fc-43fe-a342-bffa5c24817f" /> | In single screen mode - click to switch to split-screen. |
| <img width="46" height="38" alt="toolbar_split_screen (1)" src="https://github.com/user-attachments/assets/685388b5-4a1d-4e42-8a26-650b52c983ab" /> | In split-screen mode - click to switch to single-screen.

<img width="1602" height="923" alt="Screenshot of split screen mode with left and right images and ROIs on both sides" src="https://github.com/user-attachments/assets/66d00f65-8c3c-44cc-8047-dc8b98d9b8f5" />

In split-screen mode, drawing creates a paired region in both eyes by default, and deleting either rectangle removes that paired region from both eyes. Disable **Settings > ROI Editing > Draw/delete both eyes** to draw or delete only in the eye under the cursor. Moving and resizing remain local to the active eye, and single-eye selections are marked in the ROI Metadata panel. Use **View > Sync Views** to lock location, pan, and zoom between the two canvases.

Switching between single and split screen only changes the view; it never maps, resets, creates, or deletes stored rectangles. Turn off **Draw/delete both eyes** when the corresponding position does not exist in the other eye.

---

## Exporting and Loading SEL Files

ROIStudio exports ROIs as `.sel` files compatible with MERSpect. Left-only and right-only regions are stored independently, so a file may contain a selection in just one eye. Regions in the same color class share the same MERSpect label and form one union mask per eye.

- **Export** - **File > Export sel** (or `Ctrl+S`) saves the current ROIs to a `.sel` file. ROI colors are encoded as MERSpect label indices so they round-trip correctly.
- **Load** - **File > Load sel** imports ROIs from an existing `.sel` file into the current scene.

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `V` | Selection tool |
| `R` | Rectangle tool |
| `G` | Set all canvases to RGB |
| `C` | Set all canvases to DCS (Color) |
| `L` | Toggle ROI labels |
| `M` | Toggle merge spectra |
| `F` | Fit canvas to panel |
| `S` | Toggle sync views |
| `Z` | Toggle zoom context navigator |
| `1` | Show Scene Loading |
| `2` | Show Settings |
| `3` | Show ROI Metadata |
| `Escape` | Deselect ROI |
| `Delete` / `Backspace` | Delete selected ROI |
| `Ctrl+S` | Export SEL |
| `Ctrl++` / `Ctrl+-` | Increase / decrease UI scale |
| `Ctrl+Scroll` | Zoom canvas |
| `ScrollWheel+Drag` | Pan canvas |

> [!Note]
> Trackpad users can pinch to zoom, and pan around a canvas with two fingers.

ROIStudio remembers the GUI scale, window layout, active upper-left panel,
collapsed parameter sections, ROI-label visibility, and spectral display
preferences between sessions.

### Command-line UI overrides

With `.venv` active, launch ROIStudio from a terminal to override saved UI
settings. Explicit overrides become the new saved
state when the application exits.

```bash
python main.py --ui-scale 1.2 --window-size 1600 900 --left-panel-ratio 0.35 --upper-left-panel settings --spectral-y-min 0.0 --spectral-y-max 1.0 --spectral-line-width 1.5 --no-merge-spectra
```

Available UI options:

| Option | Value |
|--------|-------|
| `--ui-scale` | GUI scale from `0.5` to `3.0` |
| `--window-size` | Width and height in pixels |
| `--window-position` | X and Y screen coordinates |
| `--maximized` / `--no-maximized` | Maximized window state |
| `--left-panel-ratio` | Left-panel fraction from `0.05` to `0.95` |
| `--upper-panel-ratio` | Upper-left-panel fraction from `0.05` to `0.95` |
| `--upper-left-panel` | `scene-loading`, `settings`, or `roi-metadata` |
| `--view-settings-section` | `expanded` or `collapsed` |
| `--segmentation-section` | `expanded` or `collapsed` |
| `--roi-extraction-section` | `expanded` or `collapsed` |
| `--spectral-analysis-section` | `expanded` or `collapsed` |
| `--roi-labels` / `--no-roi-labels` | ROI-label visibility |
| `--spectral-y-min` | Spectral Y-axis minimum |
| `--spectral-y-max` | Spectral Y-axis maximum |
| `--spectral-line-width` | Spectral line width from `0.5` to `3.0` |
| `--merge-spectra` / `--no-merge-spectra` | Merge-camera-spectra state |

Run `python main.py --help` for the complete launch syntax.

---

## Development

Tests run headlessly and do not require a SAM checkpoint or real rover data:

```bash
uv run --no-sync python -m unittest discover -s tests -p "test_*.py"
```

Pull requests and pushes to `main` run the suite on Windows and Apple Silicon.
Version tags trigger the packaged Full and Lite builds, executable smoke tests,
Lite dependency audit, and GitHub release.
