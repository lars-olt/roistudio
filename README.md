# ROIStudio

ROIStudio is a desktop GUI for running and interacting with SPARC, an algorithm that automatically selects spectrally distinct regions of interest (ROIs) in multispectral images from Mars rovers. It supports data from the Mastcam-Z (ZCAM) instrument on the Perseverance rover and the Pancam (PCAM) instrument on the Spirit and Opportunity rovers.

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

Saved UI settings remain the defaults, but any of them can be overridden when
ROIStudio is launched from a terminal. Explicit overrides become the new saved
state when the application exits.

```bash
uv run python main.py --ui-scale 1.2 --window-size 1600 900 --left-panel-ratio 0.35 --upper-left-panel settings --spectral-y-min 0.0 --spectral-y-max 1.0 --spectral-line-width 1.5 --no-merge-spectra
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

Run `uv run python main.py --help` for the complete launch syntax.

---

## Table of Contents

- [Installation](#installation)
- [Interface Overview](#interface-overview)
- [Loading Scenes](#loading-scenes)
- [Running SPARC](#running-sparc)
- [Working with ROIs](#working-with-rois)
- [Spectral View](#spectral-view)
- [Split Screen Mode](#split-screen-mode)
- [Exporting and Loading SEL Files](#exporting-and-loading-sel-files)

---

## Installation

ROIStudio can be installed either via the packaged executable or manually from source.

### Executable

Download the latest release for your platform from the [releases page](https://github.com/lars-olt/roistudio/releases). No Python installation required - just download, unzip, and run.

### Manual Install

Requires Python 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/lars-olt/roistudio.git
git clone https://github.com/lars-olt/sparc.git

cd roistudio
uv venv
uv sync
```

**GPU acceleration (optional)** - if you have a CUDA-compatible GPU, install PyTorch with CUDA support on top of the uv environment. Find the right command for your system and CUDA version at [pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/), then run it with `--force-reinstall`:

```bash
# example for CUDA 12.1 - replace cu121 with your version
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 --force-reinstall
```

Without this step ROIStudio will run in CPU mode, which is slower for segmentation but otherwise fully functional.

### Setting the SAM Model Path

ROIStudio requires a SAM model checkpoint to run the SPARC pipeline. Download `sam_vit_h_4b8939.pth` from the [Segment Anything repository](https://github.com/facebookresearch/segment-anything) and place it somewhere accessible. On first launch, go to **File > Set SAM Path** and point ROIStudio to the file. This path is saved between sessions, so you only need to do this once when you first launch the app.

<img width="1601" height="924" alt="Screenshot of the Set SAM Path file dialog" src="https://github.com/user-attachments/assets/bbea956e-be95-482f-af24-409dc4b382c0" />


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

Select the rectangle tool (`R`) and drag on the canvas to draw a new ROI. If the rectangle is too small it will not be created and a message will appear in the status log.

### Selecting and Editing ROIs

With the selection tool (`V`), click an ROI to select it. Selected ROIs show corner and side handles. Drag a handle to resize, or drag the interior of the ROI to move. Press `Delete` or `Backspace` to remove the selected ROI.

<img width="212" height="173" alt="Screenshot of a selected ROI" src="https://github.com/user-attachments/assets/6e3f50cd-3c8e-4d17-b318-595ae63fe032" />

### ROI Colors

The active color swatch in the toolbar shows the color that will be assigned to the next drawn ROI. Click it to open the color palette and choose a different color.

<img width="136" height="111" alt="Screenshot of the color palette popup with swatches visible" src="https://github.com/user-attachments/assets/d1b0a3e7-bddb-4a86-b150-0b7d46cab748" />

To change the color of an existing ROI, right-click it to open the palette.

### ROI Labels

Toggle **View > ROI Labels** to show or hide color name labels on each ROI.

---

## Spectral View

The spectral panel plots reflectance (R* = IOF/cos θ) against wavelength for all active ROIs, each drawn in its assigned color. Hover the cursor over the canvas with the rectangle tool to preview the pixel spectrum as a faint white line.

### View Settings

In the application **Settings** panel, the **View Settings** section controls:

- **Y-Axis Min/Max** - reflectance axis range.
- **Merge camera spectra** - average stereo bands into one spectrum, or plot left and right cameras separately.
- **Line Width** - thickness of spectrum lines.

---

## Split Screen Mode

Click the split screen button at the bottom of the toolbar to view left and right camera images side by side.

| Icon | Description |
|------|-------------|
| <img width="46" height="38" alt="toolbar_single_screen (1)" src="https://github.com/user-attachments/assets/3891f9be-69fc-43fe-a342-bffa5c24817f" /> | In single screen mode - click to switch to split-screen. |
| <img width="46" height="38" alt="toolbar_split_screen (1)" src="https://github.com/user-attachments/assets/685388b5-4a1d-4e42-8a26-650b52c983ab" /> | In split-screen mode - click to switch to single-screen.

<img width="1602" height="923" alt="Screenshot of split screen mode with left and right images and ROIs on both sides" src="https://github.com/user-attachments/assets/66d00f65-8c3c-44cc-8047-dc8b98d9b8f5" />

In split screen mode, ROIs are shown on both cameras simultaneously. Drawing or editing an ROI on one side updates both. Use **View > Sync Views** to lock location, pan, and zoom between the two canvases.

> [!Caution]
> When you return to single screen mode, ROIs that were moved or resized in split screen will prompt a confirmation before redrawing.

---

## Exporting and Loading SEL Files

ROIStudio exports ROIs as `.sel` files compatible with MERSpect.

- **Export** - **File > Export sel** (or `Ctrl+S`) saves the current ROIs to a `.sel` file. ROI colors are encoded as MERSpect label indices so they round-trip correctly.
- **Load** - **File > Load sel** imports ROIs from an existing `.sel` file into the current scene.
