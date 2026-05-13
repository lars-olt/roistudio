# ROIStudio

ROIStudio is a desktop GUI for running and interacting with SPARC, an algorithm that automatically selects spectrally distinct regions of interest (ROIs) in multispectral images from Mars rovers. It supports data from the Mastcam-Z (ZCAM) instrument on the Perseverance rover and the Pancam (PCAM) instrument on the Spirit and Opportunity rovers.

---

## Table of Contents

- [Installation](#installation)
- [Getting Started](#getting-started)
- [Interface Overview](#interface-overview)
- [Loading Scenes](#loading-scenes)
- [Running SPARC](#running-sparc)
- [Working with ROIs](#working-with-rois)
- [Spectral View](#spectral-view)
- [Split Screen Mode](#split-screen-mode)
- [Exporting and Loading SEL Files](#exporting-and-loading-sel-files)
- [Keyboard Shortcuts](#keyboard-shortcuts)

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

## Getting Started

1. Activate the uv environment: `.venv\Scripts\activate`
2. Launch ROIStudio: `python main.py`
3. Go to **File > Open Folder** and select a folder containing IOF image files.
4. ROIStudio will scan the folder and display thumbnails of all detected scenes.
5. Double-click a thumbnail to load a scene.
6. Press **Run** to execute the SPARC pipeline on the loaded scene.

<img width="1602" height="923" alt="Screenshot of the scene thumbnail grid with several scenes visible" src="https://github.com/user-attachments/assets/b4a1e60f-695d-423a-8e06-70b959ba51d8" />


---

## Interface Overview

ROIStudio is divided into three main areas:

**Left panel (top)** — switches between the Scene Loading view (thumbnail grid) and the ROI Processing view (algorithm parameters). Toggle between them via **Window > Scene Loading** and **Window > ROI Processing**.

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

The **View** menu also provides **Set all RGB** and **Set all DCS** options to apply a stretch to all visible canvases at once. (More on this later.)

---

## Running SPARC

Switch to the **ROI Processing** panel via **Window > ROI Processing** to access the algorithm parameters.

<img width="1602" height="923" alt="Screenshot of the ROI Processing parameter panel" src="https://github.com/user-attachments/assets/25728c21-ae4a-4682-b329-81df95e7d61e" />



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
- **Contamination** - expected fraction of outlier spectra.
- **Max Clusters** - maximum number of spectral clusters the GMM may find.

Press **Run** to start the pipeline. Progress is shown in the status bar at the bottom of the window. SPARC runs in a background thread and the interface remains responsive.

<img width="1602" height="923" alt="Screenshot of the canvas after SPARC has run, with colored ROI rectangles overlaid on the image" src="https://github.com/user-attachments/assets/5c788b53-92f4-4f95-93de-2852010b356e" />

---

## Working with ROIs

### Tools

| Tool | Shortcut | Description |
|------|----------|-------------|
| Selection | `V` | Select, move, and resize ROIs |
| Rectangle | `R` | Draw a new ROI |

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

In the **ROI Processing** panel, the **View Settings** section controls:

- **Y-Axis Min/Max** - reflectance axis range.
- **Merge camera spectra** - average stereo bands into one spectrum, or plot left and right cameras separately.
- **Line Width** - thickness of spectrum lines.

---

## Split Screen Mode

Click the split screen button at the bottom of the toolbar to view left and right camera images side by side.

<img width="1602" height="923" alt="Screenshot of split screen mode with left and right images and ROIs on both sides" src="https://github.com/user-attachments/assets/66d00f65-8c3c-44cc-8047-dc8b98d9b8f5" />

In split screen mode, ROIs are shown on both cameras simultaneously. Drawing or editing an ROI on one side updates both. Use **View > Sync Views** (or `S`) to lock location, pan, and zoom between the two canvases.

Note: when you return to single screen mode, ROIs that were moved or resized in split screen will prompt a confirmation before redrawing.

---

## Exporting and Loading SEL Files

ROIStudio exports ROIs as `.sel` files compatible with MERSpect.

- **Export** - **File > Export sel** (or `Ctrl+S`) saves the current ROIs to a `.sel` file. ROI colors are encoded as MERSpect label indices so they round-trip correctly.
- **Load** - **File > Load sel** imports ROIs from an existing `.sel` file into the current scene.

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `V` | Selection tool |
| `R` | Rectangle tool |
| `F` | Fit canvas to panel |
| `S` | Toggle sync views |
| `Escape` | Deselect ROI |
| `Delete` / `Backspace` | Delete selected ROI |
| `Ctrl+S` | Export SEL |
| `Ctrl++` / `Ctrl+-` | Increase / decrease UI scale |
| `Ctrl+Scroll` | Zoom canvas |

Note: trackpad users can pinch to zoom, and pan around a canvas with two fingers.
