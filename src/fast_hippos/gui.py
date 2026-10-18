"""Graphical user interface: a small local web app (``fast-hippos-cli gui``).

The settings form is generated from the config dataclasses, so every setting is reachable; ``FIELDS`` adds
labels, help texts, the basic/advanced split and conditions under which a field is shown. Runs are started
as a subprocess (``fast-hippos-cli run <toml>``) whose log is streamed to the page; the settings are saved next
to the output as ``fast_hippos_settings.toml``.

The server only listens on 127.0.0.1 and every API call must carry a random per-session token, so other web
pages in the browser cannot use it.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import fields, is_dataclass
from enum import StrEnum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

from . import __version__
from .config import METRICS, Criterion, Settings, _from_dict

log = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".fast_hippos"
LAST_SETTINGS = STATE_DIR / "last_settings.toml"
INSTANCE = STATE_DIR / "gui_instance.json"  # port of a running GUI, so that a second start reuses it
PREFS = STATE_DIR / "gui_prefs.json"  # interface preferences (light / dark); not in the browser: the port changes
IDLE_TIMEOUT = 15 * 60  # s without any request from a browser (and no run) after which the GUI stops
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _python() -> str:
    """The console interpreter for subprocesses (the GUI itself may run in pythonw.exe, without a console)."""
    exe = Path(sys.executable)
    console = exe.with_name("python.exe") if exe.name.lower() == "pythonw.exe" else exe
    return str(console if console.exists() else exe)
SETTINGS_NAME = "fast_hippos_settings.toml"

TCSPC = {"input.modality": ["tcspc"]}
CELLPOSE = {"segmentation.method": ["cellpose"]}
SCREEN = {"screening.enabled": [True]}
# settings that the Python version never uses (kept for settings files of the Fiji version): always greyed out
UNUSED_TILES = ("not used by the Python version: the tile layout and overlap come from the stitched image (kept for "
                "settings files of the Fiji version)")
# what the scatter plot of the dashboard can show on an axis
SCATTER_AXES = {"value_at_frame": "lifetime (or ratio) at the current frame",
                "additional_at_frame": "additional channel at the current frame",
                "mean_intensity": "mean_intensity", "area_px": "area_px", "circularity": "circularity",
                **{k: k for k in METRICS}}

# label, help, level ("basic" or "advanced"), optional: widget, choices, show (field -> allowed values).
# Settings that are not listed here are shown in the advanced tab with a generated label.
FIELDS: dict[str, dict] = {
    # ---- input
    "input.files": {"label": "Images", "widget": "files",
        "help": "Time-lapse images: .tif (ImageJ hyperstack) or .lif, or a folder of tiles exported from LAS X "
        "(stitched by the stage positions of the tiles). Several are analyzed in one run."},
    "input.output": {"label": "Output folder", "widget": "folder"},
    "input.experiment": {"label": "Experiment folder (optional)", "widget": "folder",
        "placeholder": "none — a single run", "help": "For a screen of several samples: one output folder per sample "
        "inside it, and an overview of all samples"},
    "input.sample_label": {"label": "Sample label", "wide": True, "show": {"input.experiment": {"set": True}},
        "placeholder": "e.g. the condition or library of this sample",
        "help": "Shown in the experiment overview, to tell or group the samples"},
    "input.modality": {"label": "Image type", "choices": {
        "tcspc": "Fitted TCSPC data / TauSeparation (2 lifetime components)", "fast_flim": "Fast FLIM",
        "tau_contrast": "TauContrast", "fd_flim": "Frequency-domain FLIM", "ratio": "Ratio imaging (2 channels)",
        "intensity": "Intensity only"}},
    "input.tau1": {"label": "τ₁ (ns)", "show": TCSPC, "help": "Lifetime of the first component"},
    "input.tau2": {"label": "τ₂ (ns)", "show": TCSPC, "help": "Lifetime of the second component"},
    "input.additional_channel": {"label": "Additional channel", "widget": "channel",
        "help": "Channel whose mean intensity is measured per cell, e.g. a transfection marker"},
    "input.intensity_channel": {"label": "First FLIM / ratio channel", "widget": "channel_required",
        "help": "The second component (or ratio denominator) is the next channel"},
    "input.default_frame_interval": {"label": "Frame interval if not in the file (s)"},
    "input.pixel_size": {"label": "Pixel size (µm)", "help": "Overrides the file metadata; empty = from the file"},
    "input.remove_last_frame": {"label": "Remove last frame"},
    "input.series": {"label": ".lif series (0-based)", "widget": "intlist", "help": "Comma-separated; empty = all"},
    # ---- frequency-domain FLIM
    "fdflim.reference": {"label": "Reference phase stack", "widget": "file"},
    "fdflim.background": {"label": "Background phase stack", "widget": "file"},
    "fdflim.lifetime_from": {"label": "Lifetime from", "choices": {"phase": "phase", "modulation": "modulation"}},
    "fdflim.phases": {"label": "Phase steps per stack"},
    "fdflim.frequency_mhz": {"label": "Modulation frequency (MHz)"},
    "fdflim.tau_ref": {"label": "Reference lifetime (ns)"},
    # ---- pre-processing
    "preprocess.correct_bidirectional": {"label": "Correct bidirectional scanning phase"},
    "preprocess.bidirectional_axis": {"label": "Bidirectional offset along", "choices": {
        "y": "y (fast scan axis vertical)", "x": "x (fast scan axis horizontal)"},
        "help": "Depends on the microscope, not on the experiment"},
    "preprocess.correct_drift": {"label": "Correct drift"},
    "preprocess.drift_reference": {"label": "Drift reference frame",
        "choices": {"first": "first", "last": "last", "previous": "previous"}},
    "preprocess.drift_edge_detect": {"label": "Drift: register edges"},
    "preprocess.drift_blur_sigma": {"label": "Drift: blur of the cross-correlation σ (px)", "help": "0 = no blur"},
    # ---- segmentation
    "segmentation.method": {"label": "Segmentation", "choices": {
        "cellpose": "Cellpose", "labelmap": "Existing label image", "threshold": "Threshold + watershed (no Cellpose)"}},
    "segmentation.cellpose_model": {"label": "Cellpose model", "widget": "model", "show": CELLPOSE,
        "help": "cyto3 / nuclei: Cellpose 3 · cpsam: Cellpose 4 (Cellpose-SAM) · or a custom model file"},
    "segmentation.diameter": {"label": "Cell diameter (px)", "show": {"segmentation.method": ["cellpose", "threshold"]},
        "help": "0 = automatic (Cellpose 3 models; 20 px for Threshold + watershed). Setting it is faster."},
    "segmentation.labelmap": {"label": "Label image", "widget": "file",
        "show": {"segmentation.method": ["labelmap"]}},
    "segmentation.min_cell_size": {"label": "Minimum cell size (px)"},
    "segmentation.use_gpu": {"label": "Use GPU", "show": CELLPOSE},
    "segmentation.cellpose3_python": {"label": "Cellpose 3 environment (python.exe)", "widget": "python", "show": CELLPOSE,
        "help": "Only needed when Cellpose 3 is not installed in this environment"},
    "segmentation.cellpose4_python": {"label": "Cellpose 4 environment (python.exe)", "widget": "python", "show": CELLPOSE,
        "help": "Only needed when Cellpose 4 is not installed in this environment"},
    "segmentation.cellpose_version": {"label": "Cellpose version", "show": CELLPOSE,
        "help": "Empty = 4 for cpsam, else 3"},
    "segmentation.flow_threshold": {"label": "Flow threshold", "show": CELLPOSE},
    "segmentation.cellprob_threshold": {"label": "Cell probability threshold", "show": CELLPOSE},
    "segmentation.channel": {"label": "Segmentation channel", "widget": "channel",
        "help": "Dedicated channel for segmentation; empty = intensity"},
    "segmentation.gamma": {"label": "Gamma before segmentation", "help": "e.g. 0.5 to enhance dim cells; empty = off"},
    "segmentation.start_frame": {"label": "Projection: first frame"},
    "segmentation.end_frame": {"label": "Projection: last frame"},
    "segmentation.max_circularity": {"label": "Maximum circularity", "help": "1 = no filter; lower removes round objects"},
    "segmentation.min_cell_intensity": {"label": "Minimum cell intensity"},
    "segmentation.classifier": {"label": "Nuclei classifier (.joblib)", "widget": "file",
        "help": "Refines hit positions on the nuclei (fast-hippos-cli train-classifier)"},
    "segmentation.classifier_class": {"label": "Classifier: nuclei class"},
    "segmentation.position_erosion": {"label": "Classifier: erosion (px)"},
    # ---- display
    "display.min_lifetime": {"label": "Minimum", "help": "Empty = from the data. Can be changed in the dashboard."},
    "display.max_lifetime": {"label": "Maximum", "help": "Empty = from the data"},
    "display.lut": {"label": "Lookup table", "choices": {k: k for k in
        ["turbo", "viridis", "plasma", "magma", "inferno", "cividis", "gray"]}},
    "display.smooth_traces": {"label": "Smooth traces (frames)", "help": "Temporal box radius, also used for hit detection"},
    "display.overlay_smooth_xy": {"label": "Image smoothing (px)"},
    "display.dashboard_max_size": {"label": "Dashboard overview size (px)"},
    "display.dashboard_tiles": {"label": "Full-resolution tiles for large images"},
    "display.save_png_plots": {"label": "Save PNG plots"},
    "display.save_tables": {"label": "Save per-frame trace tables"},
    "display.traces_view": {"label": "Traces", "choices": {"auto": "automatic (lines up to 300 cells, else bands)",
                                                            "lines": "lines", "bands": "bands", "density": "density"}},
    "display.scatter_x": {"label": "Scatter plot: x", "choices": SCATTER_AXES},
    "display.scatter_log_x": {"label": "Scatter plot: log x"},
    "display.scatter_y": {"label": "Scatter plot: y", "choices": SCATTER_AXES},
    "display.scatter_log_y": {"label": "Scatter plot: log y"},
    # ---- events
    "events.stimulation_frame": {"label": "Stimulation frame", "widget": "frame",
        "help": "First frame with the stimulus (0-based). Empty = detect automatically"},
    "events.calibration_frame": {"label": "Calibration frame", "widget": "frame",
        "help": "First frame with the calibration. Empty = detect automatically"},
    "events.baseline_only": {"label": "Baseline only (no stimulation)"},
    "events.no_calibration": {"label": "No calibration"},
    "events.sensitivity": {"label": "Detection threshold (× noise σ)",
        "help": "How far a jump in the mean trace must stand out from the noise to count as a stimulation or "
        "calibration. Lower = more sensitive: finds weaker responses, or responses of fewer cells, but also more "
        "false ones. Default 5; try 3–4 when only a few cells respond, or set the frames by hand."},
    "events.margin": {"label": "Margin (frames)", "help": "Frames excluded before each transition"},
    # ---- screening
    "screening.enabled": {"label": "Screen for hits"},
    "screening.criteria": {"label": "Hit criteria", "widget": "criteria", "enable": SCREEN},
    "screening.stage_positions_file": {"label": "Stage positions file (.lif or text file)", "widget": "file",
        "enable": SCREEN, "filetypes": "positions", "placeholder": "none — positions from the images",
        "help": "Either the .lif file of the experiment, or a text file (.txt, .tsv, .csv) with one X Y pair in "
        "metres per image, in the order of the images: x0 y0 x1 y1 … Rarely needed: tile folders, stitched images, "
        ".lif files and TIFFs exported by LAS X (with their MetaData folder) carry their stage positions. A .lif "
        "only fills in for images without a position; a text file overrides the positions in the images."},
    "screening.classify_additional_channel": {"label": "Classify cells on the additional channel", "enable": SCREEN},
    "screening.logic": {"label": "Default criterion logic", "choices": {"OR": "OR", "AND": "AND"}, "enable": SCREEN},
    "screening.baseline_calibration_diff": {"label": "Gate: calibration − baseline", "widget": "pair", "enable": SCREEN,
        "help": "Valid cells only; empty = off"},
    "screening.max_baseline_deviation": {"label": "Gate: |baseline − population| ≤", "enable": SCREEN, "help": "Empty = off"},
    "screening.response_window": {"label": "Response window (frames)", "enable": SCREEN, "help": "Empty = the whole response",
        "placeholder": "whole response"},
    "screening.response_window_anchor": {"label": "Response window anchor", "enable": SCREEN, "choices": {
        "before_calibration": "before calibration", "after_stimulation": "after stimulation"}},
    "screening.response_window_margin": {"label": "Response window margin", "enable": SCREEN},
    "screening.rise_time_fraction": {"label": "Rise time fraction", "enable": SCREEN},
    "screening.additional_channel_metric": {"label": "Additional channel metric", "enable": SCREEN,
        "choices": {"mean": "mean over time", "first": "first frame"}},
    "screening.classification_threshold": {"label": "Classification threshold", "enable": SCREEN, "help": "Empty = Otsu"},
    "screening.sort_by": {"label": "Sort hits by", "enable": SCREEN, "widget": "metric", "help": "Empty = cell order"},
    "screening.sort_descending": {"label": "Order", "widget": "boolselect", "enable": SCREEN,
        "choices": {"true": "highest first", "false": "lowest first"}},
    "screening.manual_hits": {"label": "Hand-picked hits (TSV)", "widget": "file", "enable": SCREEN,
        "help": "Replaces the criteria (export from a dashboard selection)"},
    "screening.random_hits": {"label": "Random hits (testing)", "enable": SCREEN},
    "screening.random_seed": {"label": "Random seed", "enable": SCREEN},
    "screening.n_tiles": {"label": "Tiles (nx, ny)", "widget": "pair", "unused": UNUSED_TILES},
    "screening.tile_overlap": {"label": "Tile overlap (%)", "unused": UNUSED_TILES},
    "screening.max_hits_per_rgn": {"label": "Hits per .rgn file", "enable": SCREEN},
    "screening.optimize_path": {"label": "Optimize the route", "enable": SCREEN},
    "screening.max_optimization_time": {"label": "Route optimization time (s per file)", "enable": SCREEN},
    "screening.rgn_swap_xy": {"label": ".rgn: swap stage X and Y", "enable": SCREEN},
    "screening.rgn_invert_x": {"label": ".rgn: invert X", "enable": SCREEN},
    "screening.rgn_invert_y": {"label": ".rgn: invert Y", "enable": SCREEN},
}

# Shown when hovering over a setting in the interface: what it does and when to change it, in plain words. The short
# 'help' line under a field stays; this is the fuller explanation. Every setting has one (checked by a test).
TIPS: dict[str, str] = {
    # ---- images
    "input.files": "The time-lapse images to analyze. Each .tif is one image; a .lif file can hold many images "
        "(series), and a folder of tiles exported from LAS X is stitched into one image. All are analyzed with the "
        "same settings, and the screening is done over all of them together.",
    "input.output": "Folder for all results: tables, plots, dashboards and .rgn files. Each image gets a subfolder. "
        "An existing output folder is overwritten by a new run, or re-used by 'Re-apply screening'. In a screen of "
        "several samples: one output folder per sample, inside the experiment folder.",
    "input.experiment": "For a screen of several samples, each analyzed in its own run with the same settings: the "
        "folder that holds the output folders of all samples. It gets an overview of all samples (index.html), "
        "updated after every run and re-apply of a sample in it, with a warning when samples were analyzed with "
        "different settings. 'New sample' then proposes the output folder <experiment folder>\\<image name>. "
        "Empty = no experiment.",
    "input.sample_label": "A short description of this sample (e.g. its condition, cell line or library), shown in "
        "the experiment overview. Empty = none.",
    "input.modality": "What the pixel values mean, and so how the lifetime (or ratio) per cell is calculated. TCSPC: "
        "two amplitude images from a 2-component fit (LAS X / TauSeparation). Fast FLIM and TauContrast: an "
        "intensity and a lifetime channel. Ratio: two intensity channels, the first divided by the second.",
    "input.tau1": "Lifetime (ns) of the first, short component of the 2-component fit. Must match the value used for "
        "the fit in LAS X; the cell lifetime is the amplitude-weighted average of τ₁ and τ₂.",
    "input.tau2": "Lifetime (ns) of the second, long component of the 2-component fit. Must match the value used for "
        "the fit in LAS X.",
    "input.additional_channel": "An extra channel, e.g. a transfection or cell-cycle marker. Its mean intensity is "
        "measured in every cell and can be used to sort, filter or classify cells. Empty = none.",
    "input.intensity_channel": "The channel with the first FLIM component (TCSPC), the intensity (Fast FLIM, "
        "TauContrast) or the numerator (ratio). The lifetime, second component or denominator must be the channel "
        "right after it. Usually 1.",
    "input.default_frame_interval": "Time between frames (s), used only when the image file does not store it. "
        "Only affects time axes and times in seconds; the detection works in frames.",
    "input.pixel_size": "Size of one pixel (µm). Normally read from the file; fill it in only when the file has no "
        "or a wrong calibration. Affects cell sizes and the stage positions of the hits.",
    "input.remove_last_frame": "Leave out the last frame of every image, e.g. when it is incomplete because the "
        "acquisition was stopped during that frame.",
    "input.series": "Which images (series) of a .lif file to analyze, counted from 0, e.g. '0, 2, 5'. Empty = all "
        "series. Ignored for .tif files and tile folders.",
    # ---- frequency-domain FLIM
    "fdflim.reference": "Phase stack of a dye with a known lifetime, recorded with the same settings. Used to "
        "calibrate the phase and modulation of the instrument.",
    "fdflim.phases": "Number of phase steps in each stack (frames per lifetime measurement).",
    "fdflim.frequency_mhz": "Modulation frequency of the light source in MHz.",
    "fdflim.tau_ref": "Known lifetime (ns) of the reference dye.",
    "fdflim.lifetime_from": "Calculate the lifetime from the phase shift or from the demodulation. The phase is "
        "usually less noisy.",
    "fdflim.background": "Optional phase stack without sample (background), subtracted before the calculation.",
    # ---- pre-processing
    "preprocess.correct_bidirectional": "With bidirectional scanning, the lines scanned forward and backward can be "
        "slightly shifted, which makes edges look jagged. This measures the shift and corrects it. For tile folders "
        "and .lif tile scans, one shift is measured over all tiles and applied to each tile before stitching.",
    "preprocess.bidirectional_axis": "Direction of the shift between forward and backward scan lines: along y when "
        "the fast scan direction is vertical in the image (Leica Stellaris), along x when it is horizontal. A "
        "property of the microscope.",
    "preprocess.correct_drift": "Align all frames to each other, to correct a slow movement of the sample during the "
        "time-lapse. Needed when cells visibly move; otherwise traces mix neighbouring cells.",
    "preprocess.drift_reference": "Frame that the others are aligned to: the first, the last, or each frame to the "
        "one before it (best for slow, gradual drift).",
    "preprocess.drift_edge_detect": "Align on the edges in the image instead of the intensity itself. Helps when the "
        "brightness changes during the experiment.",
    "preprocess.drift_blur_sigma": "The drift of a frame is the position of the peak of its cross-correlation with the "
        "reference frame. Blurring that cross-correlation image (σ in pixels) makes the peak easier to find in noisy "
        "images, as in the Fiji version (which used 4). Default 2; larger = more robust, less precise. 0 = no blur.",
    # ---- segmentation
    "segmentation.method": "How the cells are found. Cellpose: a deep-learning model (best, uses the GPU). Existing "
        "label image: cells outlined elsewhere (e.g. in Fiji). Threshold + watershed: a simple classical method, no "
        "Cellpose needed.",
    "segmentation.cellpose_model": "The Cellpose model. cyto3: whole cells (Cellpose 3). nuclei: nuclei only. cpsam: "
        "Cellpose-SAM (Cellpose 4), generally the most accurate but slower. Or a model you trained yourself.",
    "segmentation.diameter": "Typical cell diameter in pixels. 0 = let Cellpose 3 estimate it per image. Giving it "
        "is faster and often more consistent. Threshold + watershed uses it for smoothing and for splitting touching "
        "cells (0 = 20 px).",
    "segmentation.labelmap": "An image in which every cell has its own number (0 = background), with the same size "
        "as the analyzed image.",
    "segmentation.min_cell_size": "Objects smaller than this (pixels) are removed: debris, fragments and noise.",
    "segmentation.use_gpu": "Run Cellpose on the graphics card, which is much faster. Switch it off only when the "
        "GPU causes problems.",
    "segmentation.cellpose3_python": "Python of a separate environment with Cellpose 3, used when Cellpose 3 is not "
        "installed alongside FAST-HIPPOS. The status line shows whether it works.",
    "segmentation.cellpose4_python": "Python of a separate environment with Cellpose 4, used when Cellpose 4 is not "
        "installed alongside FAST-HIPPOS. The status line shows whether it works.",
    "segmentation.cellpose_version": "Force Cellpose 3 or 4. Empty = 4 for the cpsam model, 3 for the others.",
    "segmentation.flow_threshold": "Cellpose quality check of the cell shapes. Lower = stricter: fewer, cleaner "
        "cells. Higher = more cells, including less regular ones. Cellpose's own default is 0.4; here 1.0 (lenient).",
    "segmentation.cellprob_threshold": "How certain Cellpose must be that a pixel belongs to a cell. Lower (e.g. -2) "
        "= larger cells and more dim cells; higher = smaller cells and fewer dim ones. Default 0.",
    "segmentation.channel": "Use another channel to find the cells, e.g. a membrane or nuclear stain. Empty = the "
        "intensity of the FLIM data.",
    "segmentation.gamma": "Brighten dim cells before segmentation: values below 1 (e.g. 0.5) lift dark regions. "
        "Only affects finding the cells, not the measurements. Useful for Threshold + watershed, whose automatic "
        "(Otsu) threshold can miss dim cells next to bright ones. Empty = off.",
    "segmentation.start_frame": "The cells are found in the average of a range of frames. First frame of that range "
        "(0-based). Empty = from the start.",
    "segmentation.end_frame": "Last frame (0-based, included) of the range that is averaged for finding the cells. "
        "Empty = to the end.",
    "segmentation.max_circularity": "Remove objects that are too round, e.g. dead or rounded-up cells. A perfect "
        "circle is 1, so 1 means no filter; 0.9 removes the roundest objects.",
    "segmentation.min_cell_intensity": "Remove cells whose mean intensity is below this value, e.g. untransfected "
        "or out-of-focus cells: the mean pixel value per frame, in the units of the image (as mean_intensity in the "
        "tables of the dashboard). 0 = no filter.",
    "segmentation.classifier": "A pixel classifier that recognizes nuclei. With it, the stage position of a hit is "
        "the centre of its nucleus instead of the centre of the cell outline. Train one with fast-hippos-cli "
        "train-classifier.",
    "segmentation.classifier_class": "Which class of the classifier is 'nucleus' (the number used when training).",
    "segmentation.position_erosion": "The cell outline is shrunk by this many pixels before looking for the nucleus, "
        "so that a neighbouring nucleus at the edge is not picked.",
    # ---- display
    "display.min_lifetime": "Lower end of the colour scale and lifetime axes. Empty = from the data (1st "
        "percentile). Can also be changed in the dashboard.",
    "display.max_lifetime": "Upper end of the colour scale and lifetime axes. Empty = from the data (99th "
        "percentile).",
    "display.lut": "Colour scale for lifetime images and plots.",
    "display.smooth_traces": "Average each trace over neighbouring frames to reduce noise: radius in frames (1 = "
        "average of 3 frames). Also used for the hit criteria. 0 = no smoothing.",
    "display.overlay_smooth_xy": "Spatial smoothing (radius in pixels; 1 = the mean of 3 × 3 pixels) of the lifetime "
        "colours of the image in the dashboard: how it starts, changeable there (Smoothing, under the image). Over "
        "time the image is smoothed as the traces are (Smooth traces). Only for display. 0 = none.",

    "display.histogram_bins": "Number of bars in the histograms of the dashboard.",
    "display.dashboard": "Make an interactive dashboard (HTML page) per image, to explore cells, traces and hits.",
    "display.dashboard_max_size": "Images larger than this (pixels, longest side) are shown downsized in the "
        "dashboard overview, to keep it fast.",
    "display.dashboard_max_megapixels": "Size limit of the dashboard movie (pixels × frames, in millions). Above it, "
        "frames are skipped in the overview so that the page stays responsive.",
    "display.dashboard_tiles": "For large images: save full-resolution pieces that the dashboard loads when you zoom "
        "in. Takes extra disk space (folder 'tiles').",
    "display.save_png_plots": "Also save the plots (traces, kymographs, histograms) as PNG images.",
    "display.save_tables": "Save tables with the value of every cell in every frame (TSV, opens in Excel).",
    "display.traces_view": "How the Traces panel of the dashboards starts: every cell its own line, the median with "
        "percentile bands, or a density map. Automatic: lines up to 300 cells, bands for more. Can be changed in the "
        "dashboard, which remembers it.",
    "display.scatter_x": "The value on the horizontal axis of the scatter plot when a dashboard opens (it can be "
        "changed there). 'at frame' values follow the current frame.",
    "display.scatter_log_x": "Start the scatter plot with a logarithmic horizontal axis, e.g. for intensities.",
    "display.scatter_y": "The value on the vertical axis of the scatter plot when a dashboard opens.",
    "display.scatter_log_y": "Start the scatter plot with a logarithmic vertical axis.",
    # ---- stimulation and calibration
    "events.stimulation_frame": "First frame in which the stimulus acts (0-based). The frames before it are the "
        "baseline. Empty = found automatically as the first clear jump in the average trace (before the "
        "calibration frame, if that is set).",
    "events.calibration_frame": "First frame with the calibration stimulus (e.g. forskolin + IBMX), which gives the "
        "maximal response. Empty = found automatically as the second jump (after the stimulation frame, if that is "
        "set). For experiments without a calibration, tick 'No calibration'.",
    "events.no_calibration": "For experiments without a calibration: only the stimulation is looked for (or set), "
        "and the response lasts until the end of the time-lapse. Without this, the end of a transient response "
        "may be taken for a calibration. The calibration gate is then not used.",
    "events.baseline_only": "For experiments without a stimulus: the whole time-lapse is baseline; no stimulation or "
        "calibration is looked for.",
    "events.sensitivity": "How far a jump in the average trace must stand out from the noise to count as a "
        "stimulation or calibration, in units of the noise σ. Lower = more sensitive, but more false detections. "
        "Used for the frames that are empty.",
    "events.margin": "Frames left out just before each transition (end of the baseline and end of the response), "
        "because the change may already start there.",
    # ---- screening
    "screening.enabled": "Select hit cells with the criteria and write their stage positions to .rgn files for "
        "LAS X, to revisit them on the microscope.",
    "screening.criteria": "Conditions that a cell must meet to be a hit, e.g. response_max_diff > 0.3. AND: must "
        "pass. OR: at least one of the OR criteria must pass. Hover over a metric for its meaning; thresholds can be "
        "tuned later in the dashboard.",
    "screening.stage_positions_file": "For images without stage positions of their own. A text file with the stage "
        "X Y in metres for every image, in the order of the images (x0 y0 x1 y1 …; it replaces the positions in the "
        "images), or the .lif file of the experiment (used only for images without positions of their own).",
    "screening.classify_additional_channel": "Split the cells in two groups on the intensity of the additional "
        "channel (e.g. transfected or not), with an automatic threshold. Adds a class column to the tables.",
    "screening.logic": "AND or OR, for criteria that do not set their own.",
    "screening.baseline_calibration_diff": "Quality check: only cells whose calibration response (calibration − "
        "baseline) lies in this range can be hits. Removes cells that do not respond to the calibration. In the unit "
        "of the measured value: ns for lifetimes, ratio units for ratio imaging, intensity for intensity data. The "
        "default 0.5–1 ns is for lifetimes; for ratio and intensity data the gate starts off (set it from its "
        "histogram in the dashboard). Empty = off.",
    "screening.max_baseline_deviation": "Quality check: only cells whose baseline differs at most this much from "
        "the population baseline can be hits. Removes outliers. In the unit of the measured value; the default "
        "0.2 ns is for lifetimes, for ratio and intensity data the gate starts off. Empty = off.",
    "screening.response_window": "Length (frames) of the part of the response used for the 'mean' response metrics. "
        "Empty = the whole response, from stimulation to calibration.",
    "screening.response_window_anchor": "Where that window lies: at the start of the response (after the "
        "stimulation) or at its end (just before the calibration).",
    "screening.response_window_margin": "Frames skipped between the anchor and the window, e.g. to leave out the "
        "first frames after the stimulation.",
    "screening.rise_time_fraction": "Rise time = number of frames until a cell reaches this fraction of its maximal "
        "response (0.75 = 75 %).",
    "screening.additional_channel_metric": "Intensity of the additional channel per cell: the mean over all frames, "
        "or only the first frame (when the marker bleaches or changes).",
    "screening.classification_threshold": "Intensity that separates the two classes of the additional channel. "
        "Empty = chosen automatically (Otsu).",
    "screening.sort_by": "Order of the hits in the hit list and .rgn files before the route is optimized. Empty = "
        "cell order.",
    "screening.sort_descending": "Sort the hits from the highest to the lowest value of 'Sort hits by', or the "
        "other way round.",
    "screening.manual_hits": "Use cells you picked yourself (a TSV exported from a dashboard selection) as hits, "
        "instead of the criteria.",
    "screening.random_hits": "Testing only: take this many random cells as hits. Empty = off.",
    "screening.random_seed": "Testing only: a fixed seed, so that 'random hits' gives the same cells every time.",
    "screening.n_tiles": "Not used by the Python version: the tile layout comes from the stitched image. Kept for "
        "settings files of the Fiji version.",
    "screening.tile_overlap": "Not used by the Python version: the tile overlap comes from the stitched image. Kept "
        "for settings files of the Fiji version.",
    "screening.max_hits_per_rgn": "The hits are split over .rgn files of at most this many positions (LAS X can be "
        "slow with very long lists).",
    "screening.optimize_path": "Order the positions in each .rgn file for the shortest stage route (typically 13–18 % "
        "shorter than always going to the nearest next hit).",
    "screening.max_optimization_time": "Time limit for optimizing the route of each .rgn file. Longer can give a "
        "slightly shorter route.",
    "screening.rgn_swap_xy": "How the stage position of an image (X, Y, as LAS X stores it in the image metadata) is "
        "turned into the coordinates of the .rgn file (the frame of the LAS X Navigator). On, the default: the .rgn X "
        "comes from the stage Y and the .rgn Y from the stage X, as on the Leica Stellaris where this was validated. "
        "Check it on your microscope: load a .rgn file in the Navigator and see whether the positions land on the "
        "cells. A re-apply uses a changed setting.",
    "screening.rgn_invert_x": "Negate the .rgn X (default on, Leica Stellaris): see '.rgn: swap stage X and Y'. "
        "Change it when the positions in the Navigator are mirrored left-right.",
    "screening.rgn_invert_y": "Negate the .rgn Y (default on, Leica Stellaris): see '.rgn: swap stage X and Y'. "
        "Change it when the positions in the Navigator are mirrored top-bottom.",
}

FD = {"input.modality": ["fd_flim"]}

# Cards of the form: the basic settings, then the advanced ones under subheadings (an expanding pane).
# Every setting appears exactly once (checked by the tests).
# "|" in a group starts a new row, so that only related settings are next to each other
LAYOUT = [
    {"title": "Images", "basic": ["input.files", "input.experiment", "input.output", "input.sample_label", "input.modality", "input.tau1", "input.tau2",
                                  "input.additional_channel"],
     "advanced": [
         ("Channels and metadata", ["input.intensity_channel", "input.series", "|", "input.pixel_size",
                                    "input.default_frame_interval", "|", "input.remove_last_frame"]),
         ("Bidirectional scanning", ["preprocess.correct_bidirectional", "preprocess.bidirectional_axis"]),
         ("Drift correction", ["preprocess.correct_drift", "|", "preprocess.drift_reference", "preprocess.drift_edge_detect",
                               "|", "preprocess.drift_blur_sigma"]),
         ("Frequency-domain FLIM", ["fdflim.reference", "fdflim.background", "|", "fdflim.phases", "fdflim.frequency_mhz",
                                    "|", "fdflim.tau_ref", "fdflim.lifetime_from"], FD),
     ]},
    {"title": "Cell segmentation", "basic": ["segmentation.method", "segmentation.cellpose_model", "segmentation.diameter",
                                             "segmentation.labelmap", "segmentation.min_cell_size"],
     "advanced": [
         ("Cellpose", ["segmentation.use_gpu", "segmentation.cellpose_version", "|", "segmentation.flow_threshold",
                       "segmentation.cellprob_threshold"], CELLPOSE),
         ("Cellpose environments", ["segmentation.cellpose3_python", "segmentation.cellpose4_python"], CELLPOSE),
         ("Image used for segmentation", ["segmentation.channel", "segmentation.gamma", "|", "segmentation.start_frame",
                                          "segmentation.end_frame"]),
         ("Cell filters", ["segmentation.max_circularity", "segmentation.min_cell_intensity"]),
         ("Hit positions on the nuclei", ["segmentation.classifier", "|", "segmentation.classifier_class",
                                          "segmentation.position_erosion"]),
     ]},
    {"title": "Stimulation and calibration", "basic": ["events.stimulation_frame", "events.calibration_frame",
                                                       "events.baseline_only", "events.no_calibration"],
     "advanced": [
         ("Automatic detection", ["events.sensitivity", "events.margin"]),
         ("Traces", ["display.smooth_traces"]),
     ]},
    {"title": "Screening", "basic": ["screening.enabled", "screening.criteria", "screening.classify_additional_channel"],
     "advanced": [
         ("Criteria", ["screening.logic", "screening.rise_time_fraction"]),
         ("Response window", ["screening.response_window", "|", "screening.response_window_anchor",
                              "screening.response_window_margin"]),
         ("Quality gates", ["screening.baseline_calibration_diff", "screening.max_baseline_deviation"]),
         ("Additional channel", ["screening.additional_channel_metric", "screening.classification_threshold"]),
         ("Hit list", ["screening.sort_by", "screening.sort_descending", "|", "screening.manual_hits"]),
         ("Stage positions and .rgn files", ["screening.stage_positions_file", "|", "screening.max_hits_per_rgn", "|",
                                             "screening.optimize_path", "screening.max_optimization_time"]),
         ("Stage axes in the .rgn files (LAS X Navigator)", ["screening.rgn_swap_xy", "screening.rgn_invert_x",
                                                             "screening.rgn_invert_y"], None, "column"),
         ("Tiles (only for settings files of the Fiji version)", ["screening.n_tiles", "screening.tile_overlap"]),
         ("Testing", ["screening.random_hits", "screening.random_seed"]),
     ]},
    {"title": "Display and output", "basic": [],
     "note": "The defaults suit most runs; colours and ranges can also be changed in the dashboard.",
     "advanced": [
         ("Colour scale", ["display.lut", "|", "display.min_lifetime", "display.max_lifetime"]),
         ("Lifetime overlay", ["display.overlay_smooth_xy"]),
         ("Dashboard", ["display.dashboard", "|", "display.dashboard_max_size", "display.dashboard_max_megapixels",
                        "|", "display.dashboard_tiles", "display.histogram_bins"]),
         ("Dashboard views", ["display.traces_view", "|", "display.scatter_x", "display.scatter_log_x", "|",
                              "display.scatter_y", "display.scatter_log_y"]),
         ("Files", ["display.save_png_plots", "display.save_tables"]),
     ]},
]

# Conditions under which a setting is used; otherwise it is greyed out, with the reason as tooltip.
# {field: [allowed values]} or {field: {"set": bool}} or {field: {"not": [values]}}; all must hold.
ENABLE = {
    "events.stimulation_frame": {"events.baseline_only": [False]},
    "events.calibration_frame": {"events.baseline_only": [False], "events.no_calibration": [False]},
    "events.no_calibration": {"events.baseline_only": [False]},
    "events.sensitivity": {"events.baseline_only": [False]},
    "preprocess.bidirectional_axis": {"preprocess.correct_bidirectional": [True]},
    "preprocess.drift_reference": {"preprocess.correct_drift": [True]},
    "preprocess.drift_edge_detect": {"preprocess.correct_drift": [True]},
    "preprocess.drift_blur_sigma": {"preprocess.correct_drift": [True]},
    "screening.criteria": {"screening.manual_hits": {"set": False}, "screening.random_hits": {"set": False}},
    "screening.logic": {"screening.manual_hits": {"set": False}, "screening.random_hits": {"set": False}},
    "screening.classify_additional_channel": {"input.additional_channel": {"set": True}},
    "screening.additional_channel_metric": {"input.additional_channel": {"set": True}},
    "screening.classification_threshold": {"input.additional_channel": {"set": True},
                                           "screening.classify_additional_channel": [True]},
    "screening.response_window_anchor": {"screening.response_window": {"set": True}},
    "screening.response_window_margin": {"screening.response_window": {"set": True}},
    "screening.sort_descending": {"screening.sort_by": {"set": True}},
    "screening.random_seed": {"screening.random_hits": {"set": True}},
    "screening.max_optimization_time": {"screening.optimize_path": [True]},
    "segmentation.classifier_class": {"segmentation.classifier": {"set": True}},
    "segmentation.position_erosion": {"segmentation.classifier": {"set": True}},
    "display.dashboard_max_size": {"display.dashboard": [True]},
    "display.dashboard_max_megapixels": {"display.dashboard": [True]},
    "display.dashboard_tiles": {"display.dashboard": [True]},
    **{f"display.{k}": {"display.dashboard": [True]} for k in ("traces_view", "scatter_x", "scatter_log_x", "scatter_y",
                                                              "scatter_log_y")},
    "display.histogram_bins": {"display.dashboard": [True]},
}
REASONS = {  # why a condition on this field disables others
    "events.baseline_only": "'Baseline only' is on",
    "events.no_calibration": "'No calibration' is on",
    "preprocess.correct_drift": "drift correction is off",
    "preprocess.correct_bidirectional": "bidirectional correction is off",
    "screening.enabled": "screening is off",
    "screening.manual_hits": "replaced by the hand-picked hits",
    "screening.random_hits": "replaced by random hits",
    "input.additional_channel": "needs an additional channel",
    "screening.classify_additional_channel": "classification is off",
    "screening.response_window": "only for a response window of a number of frames (not the whole response)",
    "screening.sort_by": "the hits are in cell order",
    "screening.optimize_path": "route optimization is off",
    "segmentation.classifier": "needs a nuclei classifier",
    "display.dashboard": "no dashboard",
}

SECTIONS = {"input": "Input", "fdflim": "Frequency-domain FLIM", "preprocess": "Pre-processing",
            "segmentation": "Segmentation", "display": "Display", "events": "Stimulation & calibration",
            "screening": "Screening"}
SECTION_SHOW = {"fdflim": {"input.modality": ["fd_flim"]}}


def _kind(tp) -> tuple[str, bool]:
    """Widget kind for a type hint, and whether the value is optional."""
    args = get_args(tp)
    optional = type(None) in args
    if optional:
        tp = next(a for a in args if a is not type(None))
    origin = get_origin(tp)
    if tp is bool:
        return "bool", optional
    if tp is int:
        return "int", optional
    if tp is float:
        return "float", optional
    if tp is Path:
        return "file", optional
    if isinstance(tp, type) and issubclass(tp, StrEnum):
        return "select", optional
    if origin is list and get_args(tp)[0] is Path:
        return "files", optional
    if origin is list and get_args(tp)[0] is int:
        return "intlist", optional
    if origin is list and get_args(tp)[0] is Criterion:
        return "criteria", optional
    if origin is tuple:
        return "pair", optional
    return "text", optional


def schema() -> dict:
    defaults = Settings().to_dict()
    sections = []
    section_types = get_type_hints(Settings)
    for section in fields(Settings):
        cls = section_types[section.name]
        if not is_dataclass(cls):  # Settings.image: shown under 'Stimulation and calibration', not as fields
            continue
        hints = get_type_hints(cls)
        items = []
        for f in fields(cls):
            key = f"{section.name}.{f.name}"
            kind, optional = _kind(hints[f.name])
            spec = {"key": key, "kind": kind, "optional": optional,
                    "label": f.name.replace("_", " ").capitalize(), "default": defaults[section.name][f.name]}
            if kind == "select":
                enum = next(a for a in (get_args(hints[f.name]) or (hints[f.name],)) if isinstance(a, type))
                spec["choices"] = {m.value: m.value for m in enum}
            extra = dict(FIELDS.get(key, {}))
            enable = (extra.pop("enable", None) or {}) | ENABLE.get(key, {})
            if enable:
                spec["enable"] = enable
            if "widget" in extra:
                extra["kind"] = extra.pop("widget")
            elif "choices" in extra:
                extra["kind"] = "select"
            spec |= extra
            spec["tip"] = TIPS.get(key, "")
            items.append(spec)
        sections.append({"name": section.name, "title": SECTIONS.get(section.name, section.name),
                         "show": SECTION_SHOW.get(section.name), "fields": items})
    basic = {k for card in LAYOUT for k in card["basic"]}
    for sec in sections:
        for f in sec["fields"]:
            f["level"] = "basic" if f["key"] in basic else "advanced"
    layout = [{"title": c["title"], "basic": c["basic"], "note": c.get("note"),
               "advanced": [{"title": a[0], "keys": a[1], "show": a[2] if len(a) > 2 else None,
                             "column": len(a) > 3 and a[3] == "column"} for a in c["advanced"]]}
              for c in LAYOUT]
    return {"version": __version__, "sections": sections, "layout": layout, "metrics": METRICS, "reasons": REASONS}


# ---------------------------------------------------------------- TOML


def _toml_value(v) -> str:
    if v is None:
        return '""'  # "" means 'not set' when the config is read
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {_toml_value(x)}" for k, x in v.items() if x is not None) + " }"
    if isinstance(v, (list, tuple)):
        if v and isinstance(v[0], dict):
            return "[\n" + "".join(f"  {_toml_value(x)},\n" for x in v) + "]"
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    raise TypeError(type(v))


def to_toml(settings: dict, header: str = "") -> str:
    lines = [header] if header else []
    if "image" in settings and not settings["image"]:  # said explicitly, so that a re-apply removes those of the run
        lines.append("image = {}  # no own settings of single images")
    for section, values in settings.items():
        if section == "image":  # per-image settings: [image."<name>".events] etc.
            for name, sections in (values or {}).items():
                for sec, vals in sections.items():
                    lines.append(f"\n[image.{json.dumps(name, ensure_ascii=False)}.{sec}]")
                    lines += [f"{k} = {_toml_value(v)}" for k, v in vals.items()]
            continue
        lines.append(f"\n[{section}]")
        for k, v in values.items():
            if v is None and isinstance(Settings().to_dict()[section].get(k), (list, tuple)):
                lines.append(f"{k} = []")
            else:
                lines.append(f"{k} = {_toml_value(v)}")
    return "\n".join(lines).lstrip("\n") + "\n"


def settings_from_plain(data: dict) -> Settings:
    """Validate a settings dict from the page (raises ValueError with a readable message)."""
    try:
        return _from_dict(Settings, data)
    except (TypeError, ValueError, KeyError) as e:
        raise ValueError(f"Invalid settings: {e}") from e


def load_toml(path: Path) -> dict:
    return Settings.from_toml(path).to_dict()


# ---------------------------------------------------------------- helpers for the page


def inspect_file(path: Path) -> dict:
    """Quick look at an image file (metadata only), shown when files are added."""
    path = Path(path)
    out: dict = {"path": str(path), "name": path.name, "exists": path.exists()}
    if not path.exists():
        return out
    if path.is_file():
        out["size_mb"] = round(path.stat().st_size / 1e6, 1)
    try:
        from .io import image_info

        infos = image_info(path)
        first = {k: v for k, v in infos[0].items() if k != "name"}
        out |= first
        if len(infos) > 1:
            out |= {"series": len(infos), "channels": min(i["channels"] for i in infos), "frames": min(i["frames"] for i in infos)}
    except Exception as e:  # noqa: BLE001 - shown to the user
        out["error"] = f"{type(e).__name__}: {e}"
    return out


_CELLPOSE_PROBE = (
    "import json\n"
    "info = {}\n"
    "try:\n"
    "    from importlib.metadata import version\n"
    "    info['cellpose'] = version('cellpose')\n"
    "    import torch\n"
    "    info['torch'] = torch.__version__\n"
    "    info['gpu'] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None\n"
    "except Exception as e:\n"
    "    info['error'] = f'{type(e).__name__}: {e}'\n"
    "print(json.dumps(info))\n"
)


def _check(settings: dict) -> list[str]:
    from .checks import check_inputs

    return check_inputs(settings_from_plain(settings))


def output_info(path: str, job: Job | None = None, settings: dict | None = None) -> dict:
    """The run in an output folder, if any: which images a re-apply would process, and (with the page's settings)
    exactly what a new run would move away first ("plan", see pipeline.clear_plan). Its results can then also be
    opened via the GUI."""
    from .pipeline import clear_plan, input_paths, run_info

    out = Path(path) if path else None
    exists = bool(out and out.is_dir())
    info = run_info(out) if exists else None
    if info and job is not None:
        job.roots.add(out.resolve())
    result = {"exists": exists, "images": [i["folder"] for i in info["images"]] if info else [], "run": info,
              "index": bool(exists and (out / "index.html").exists())}
    if info:
        from .pipeline import run_image_settings

        info["image_settings"] = run_image_settings(out)  # the images with their own settings in that run
        info["inputs"] = [os.path.normcase(str(Path(p).resolve())) for p in info.get("inputs") or []] or None
        try:
            used = json.loads((out / "settings_used.json").read_text())
            info["stage_positions_file"] = used.get("screening", {}).get("stage_positions_file")
            info["sample_label"] = used.get("input", {}).get("sample_label")
        except (OSError, ValueError):
            info["stage_positions_file"] = None
    if settings is not None and exists:
        result["plan"] = clear_plan(out, input_paths(settings_from_plain(settings)))
    return result


def remember_settings(settings: dict) -> None:
    """The settings of the page, so that the window starts with them next time (also without a run)."""
    settings_from_plain(settings)  # only valid settings
    STATE_DIR.mkdir(exist_ok=True)
    LAST_SETTINGS.write_text(to_toml(settings, f"# FAST-HIPPOS {__version__} settings, written by the GUI"), encoding="utf-8")


def experiment_info(path: str, settings: dict | None = None, job: Job | None = None) -> dict:
    """The samples (runs) in an experiment folder, and (with the page's settings) which of them were analyzed with
    other settings than those of the page ('differs': {sample: [settings]}; the own settings of single images and
    the settings that do not change the analysis, such as paths and display, are not compared)."""
    from .experiment import comparable_settings, read_overview_data, run_folders

    folder = Path(path) if path else None
    if not folder or not folder.is_dir():
        return {"exists": False, "samples": [], "index": False, "differs": {}}
    if job is not None:
        job.roots.add(folder.resolve())
    page = comparable_settings(settings_from_plain(settings).to_dict()) if settings else None
    samples, differs = [], {}
    for run in run_folders(folder):
        try:
            used = json.loads((run / "settings_used.json").read_text())
            started = read_overview_data(run / "index.html").get("started")
        except (OSError, ValueError):
            continue
        samples.append({"name": run.name, "label": (used.get("input") or {}).get("sample_label") or "", "started": started})
        if page is not None:
            theirs = comparable_settings(used)
            keys = [k for k in dict.fromkeys([*page, *theirs])
                    if json.dumps(page.get(k), sort_keys=True, default=str) != json.dumps(theirs.get(k), sort_keys=True, default=str)]
            if keys:
                differs[run.name] = keys
    return {"exists": True, "samples": samples, "index": (folder / "index.html").exists(), "differs": differs}


def start_reapply_experiment(job: Job, gui_settings: dict) -> int:
    """'Re-apply to all samples' in the GUI: the event, screening and display settings of the page for every sample
    (run) in the experiment folder, which keep the own settings of their single images; then the experiment overview."""
    experiment = gui_settings["input"].get("experiment")
    if not experiment or not experiment_info(experiment)["samples"]:
        raise ValueError("No samples (runs) in the experiment folder")
    return job.start(gui_settings, reapply=True, remember=gui_settings, experiment=experiment)


def start_reapply(job: Job, gui_settings: dict) -> int:
    """'Re-apply screening' in the GUI: the run in the output folder with the event, screening and display settings
    of the page; the page's own settings are remembered for the next start."""
    from .pipeline import reapply_settings

    merged = reapply_settings(Path(gui_settings["input"]["output"]), gui_settings)
    return job.start(merged, reapply=True, remember=gui_settings)


CELLPOSE_CACHE = STATE_DIR / "cellpose_check.json"


def check_cellpose(python: str | None, fresh: bool = False) -> dict:
    """Cellpose version and GPU of an environment (empty = this one). Starting that environment and importing
    PyTorch takes seconds, so the last result is returned at once (with "cached": true) unless fresh is set;
    the page then asks again with fresh=True in the background."""
    exe = python or _python()
    try:
        cache = json.loads(CELLPOSE_CACHE.read_text())
    except Exception:  # noqa: BLE001 - no cache yet
        cache = {}
    if not fresh and exe in cache:
        return cache[exe] | {"cached": True}
    result = _probe_cellpose(exe)
    cache[exe] = result
    try:
        STATE_DIR.mkdir(exist_ok=True)
        CELLPOSE_CACHE.write_text(json.dumps(cache, indent=1))
    except OSError:
        pass
    return result


def _probe_cellpose(exe: str) -> dict:
    if not Path(exe).exists():
        return {"error": f"Not found: {exe}"}
    try:
        r = subprocess.run([exe, "-c", _CELLPOSE_PROBE], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=120, check=False,
                           creationflags=NO_WINDOW)
        return json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"error": r.stderr[-500:]}
    except Exception as e:  # noqa: BLE001 - shown to the user
        return {"error": f"{type(e).__name__}: {e}"}


_DIALOG = r"""
import json, sys, tkinter as tk
from tkinter import filedialog
kind, title, initial, types = sys.argv[1], sys.argv[2], sys.argv[3] or None, json.loads(sys.argv[4])
root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
opts = dict(parent=root, title=title, initialdir=initial)
if kind == "files":
    r = list(filedialog.askopenfilenames(filetypes=types, **opts))
elif kind == "folder":
    r = filedialog.askdirectory(mustexist=False, **opts)
elif kind == "save":
    r = filedialog.asksaveasfilename(filetypes=types, defaultextension=types[0][1][1:] if types else "", **opts)
else:
    r = filedialog.askopenfilename(filetypes=types, **opts)
print(json.dumps(r))
"""

FILETYPES = {
    "files": [["Images", "*.tif *.tiff *.lif"], ["All files", "*.*"]],
    "file": [["All files", "*.*"]],
    "positions": [["Stage positions: .lif file or text file", "*.lif *.txt *.tsv *.csv"], ["All files", "*.*"]],
    "python": [["Python", "python.exe python"], ["All files", "*.*"]],
    "toml": [["Settings", "*.toml"], ["All files", "*.*"]],
}


def browse(kind: str, title: str, initial: str = "", types: str = "file"):
    """Native file dialog, run in a separate process (Tk needs its own main thread)."""
    if initial and Path(initial).is_file():
        initial = str(Path(initial).parent)
    r = subprocess.run([_python(), "-c", _DIALOG, kind, title, initial or "", json.dumps(FILETYPES.get(types, []))],
                       capture_output=True, text=True, check=False, creationflags=NO_WINDOW)
    return json.loads(r.stdout) if r.stdout.strip() else None


# ---------------------------------------------------------------- runs


class Job:
    """One analysis run in a subprocess; the log is kept for the page."""

    def __init__(self):
        self.lines: list[str] = []
        self.proc: subprocess.Popen | None = None
        self.state = "idle"  # idle | running | done | failed | stopped
        self.output: str | None = None
        self.settings: dict | None = None
        self.source = "gui"  # who started the run: "gui" or "dashboard"
        self.applied = ""  # what a dashboard applied, for the page
        self.removed: dict[str, set[str]] = {}  # output folder -> images whose own settings were removed in the page
        self.run_id = 0
        self.roots: set[Path] = set()  # output folders whose files may be served (dashboards)
        self.lock = threading.Lock()

    def start(self, settings: dict, reapply: bool, source: str = "gui", remember: dict | None = None,
              experiment: str | None = None) -> int:
        """Run (or re-apply) with these settings, in a subprocess. remember: settings of the page, kept for the next
        start of the GUI (None: leave them, e.g. for 'Apply to run' from a dashboard). experiment: re-apply to all
        samples of this experiment folder instead (cli experiment --reapply)."""
        if self.state == "running":
            raise ValueError("A run is already in progress")
        settings_from_plain(settings)  # validate before starting
        out = Path(experiment or settings["input"]["output"])
        out.mkdir(parents=True, exist_ok=True)
        # the run itself writes fast_hippos_settings.toml into the output folder, after moving the previous run away
        STATE_DIR.mkdir(exist_ok=True)
        toml = STATE_DIR / "run_settings.toml"
        header = f"# FAST-HIPPOS {__version__} settings, written by the GUI"
        toml.write_text(to_toml(settings, header), encoding="utf-8")
        if remember is not None:
            LAST_SETTINGS.write_text(to_toml(remember, header), encoding="utf-8")
        cmd = [_python(), "-u", "-m", "fast_hippos.cli", "reapply" if reapply else "run", str(toml)]
        if experiment:
            cmd = [*cmd[:4], "experiment", str(out), "--reapply", str(toml)]
        if source == "gui":  # the page sends its complete own settings of single images
            self.removed.pop(_key(out), None)
            self.applied = ""
        with self.lock:
            self.lines, self.state, self.output = [f"$ fast-hippos {' '.join(cmd[4:])}"], "running", str(out)
            self.settings, self.source, self.run_id = settings, source, self.run_id + 1
            self.roots.add(out.resolve())
        env = os.environ | {"PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                     errors="replace", env=env, creationflags=NO_WINDOW)
        threading.Thread(target=self._read, daemon=True).start()
        return self.run_id

    def _read(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            with self.lock:
                self.lines.append(line.rstrip())
        code = self.proc.wait()
        with self.lock:
            if self.state == "running":
                self.state = "done" if code == 0 else "failed"

    def stop(self) -> None:
        if self.proc and self.state == "running":
            with self.lock:
                self.state = "stopped"
            self.proc.terminate()
            from .pipeline import PREVIOUS_RUN

            previous = Path(self.output) / PREVIOUS_RUN if self.output else None
            if previous and previous.is_dir():
                with self.lock:
                    self.lines.append(f"Stopped. The results of the previous run are kept in {previous}; "
                                      "move them back to use them again.")

    def status(self, since: int) -> dict:
        with self.lock:
            out = {"state": self.state, "lines": self.lines[since:], "n": len(self.lines), "output": self.output,
                   "output_key": _key(self.output) if self.output else None,
                   "run_id": self.run_id, "source": self.source, "applied": self.applied,
                   "settings": self.settings if self.source == "dashboard" else None}
        if self.output and self.state == "done":
            o = Path(self.output)
            out["index"] = str(o / "index.html") if (o / "index.html").exists() else None
            out["dashboards"] = [str(p) for p in sorted(o.glob("*/dashboard.html"))]
        return out


def apply_from_dashboard(job: Job, dashboard: str, toml_text: str, manual_tsv: str | None = None, image: str | None = None,
                         scope: str = "all") -> int:
    """The apply buttons of a dashboard (<output>/<image>/dashboard.html); either way all images are re-applied, since
    the hit list and the .rgn files cover all of them.
    scope "all" ('Apply to all images'): the dashboard's screening settings for all images of the output folder; a
    timing changed there is used for all images too, and replaces the own timing of this image (other images keep
    theirs). scope "image" ('Apply to this image only'): only the settings that can differ per image (stimulation
    settings, response window) become this image's own; everything else stays as it is."""
    import tomllib

    from .config import IMAGE_SETTINGS, _image_settings
    from .pipeline import reapply_settings, run_image_settings

    out = Path(dashboard).parent.parent
    (out / "screening_from_dashboard.toml").write_text(toml_text, encoding="utf-8")  # a record of what was applied
    changes = tomllib.loads(toml_text)
    removed = job.removed.get(_key(out), set())  # removed in the page since: they stay removed
    own_all = {name: {sec: dict(v) for sec, v in secs.items()} for name, secs in run_image_settings(out).items()
               if name not in removed}
    if scope == "image":
        if not image:
            raise ValueError("Apply to this image only: the dashboard did not say which image")
        own = {sec: {k: v for k, v in changes.get(sec, {}).items() if k in keys} for sec, keys in IMAGE_SETTINGS.items()}
        own_all[image] = {sec: v for sec, v in own.items() if v}
        removed.discard(image)
        changes = {}
        job.applied = f"Own settings of {image} applied from its dashboard"
    else:
        manual = changes.get("screening", {}).get("manual_hits")
        if manual_tsv:
            manual = manual or "manual_hits.tsv"
            (out / manual).write_text(manual_tsv, encoding="utf-8")
        if manual and not Path(manual).is_absolute():  # a hit list named in the dashboard's settings lives in the folder
            changes.setdefault("screening", {})["manual_hits"] = str(out / manual)
        mine = own_all.get(image or "", {})
        timing = ("stimulation_frame", "calibration_frame", "baseline_only")
        if any(k in changes.get("events", {}) for k in timing):  # a timing for all images replaces its own timing as a whole
            for k in timing:
                mine.get("events", {}).pop(k, None)
        for sec in ("events", "screening"):  # this image's own values of what the dashboard sends
            for k in [k for k in mine.get(sec, {}) if k in changes.get(sec, {})]:
                if sec == "screening" and changes[sec][k] == mine[sec][k]:
                    del changes[sec][k]  # its own response window, unchanged: not for all images
                else:
                    del mine[sec][k]  # set here for all images: replaces its own value
        job.applied = f"Settings for all images applied from the dashboard of {image}" if image else "Settings for all images applied from a dashboard"
    changes["image"] = _image_settings({name: {sec: v for sec, v in secs.items() if v} for name, secs in own_all.items()})
    settings = reapply_settings(out, changes)
    _remember_applied(out, settings)
    return job.start(settings, reapply=True, source="dashboard")


def _remember_applied(out: Path, settings: dict) -> None:
    """Keep what a dashboard applied (stimulation, screening and display settings, own settings of single images) in
    the settings the window starts with, when those are for this output folder: a later Re-apply or Run from a
    reopened window then uses them too."""
    try:
        last = load_toml(LAST_SETTINGS)
        if _key(last["input"]["output"]) != _key(out):
            return
        for section in ("events", "screening", "display"):
            last[section] = settings[section]
        last["image"] = settings.get("image", {})
        LAST_SETTINGS.write_text(to_toml(last, f"# FAST-HIPPOS {__version__} settings, written by the GUI"), encoding="utf-8")
    except (OSError, ValueError, KeyError):
        pass


# ---------------------------------------------------------------- server


def _png_url(name: str) -> str:  # (not imported from .dashboard: that pulls in matplotlib and pandas, ~2 s)
    raw = resources.files("fast_hippos").joinpath("templates", name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def load_prefs() -> dict:
    try:
        return json.loads(PREFS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_prefs(changes: dict) -> dict:
    """Store the known interface preferences: theme ("", "light", "dark") and folded sections (titles)."""
    ok = {}
    if changes.get("theme") in ("", "light", "dark"):
        ok["theme"] = changes["theme"]
    if isinstance(changes.get("folded"), list):
        ok["folded"] = [str(t)[:100] for t in changes["folded"] if isinstance(t, str)][:50]
    prefs = load_prefs() | ok
    STATE_DIR.mkdir(exist_ok=True)
    PREFS.write_text(json.dumps(prefs), encoding="utf-8")
    return prefs


def _page(token: str) -> bytes:
    html = resources.files("fast_hippos").joinpath("templates", "gui.html").read_text(encoding="utf-8")
    html = html.replace("__FH_LOGO__", _png_url("logo.png")).replace("__FH_ICON__", _png_url("favicon.png"))
    prefs = load_prefs()
    html = html.replace("__FH_THEME__", prefs.get("theme", ""))  # in the page itself: no flash of the other theme
    html = html.replace("__FH_PREFS__", json.dumps(prefs).replace("<", "\\u003c"))
    return html.replace("__FH_TOKEN__", token).encode("utf-8")


def _key(path: str | Path) -> str:
    """Comparable form of a folder path."""
    return os.path.normcase(str(Path(path).resolve()))


# Added to pages served by the GUI: reload when a run or re-apply of their output folder has finished (e.g. one
# started from another dashboard or from the GUI), with a small banner while it runs.
_WATCH = """<script>
window.FH_GUI = { token: "__TOKEN__", output: "__OUTPUT__", run: __RUN__ };
(function () {
  let banner = null;
  const show = (text) => {
    if (!banner) { banner = document.createElement("div"); document.body.appendChild(banner);
      banner.style.cssText = "position:fixed;left:50%;bottom:14px;transform:translateX(-50%);z-index:99;padding:6px 14px;" +
        "border-radius:8px;background:#1f6fd1;color:#fff;font:13px system-ui,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.3)"; }
    banner.textContent = text;
  };
  async function watch() {
    try {
      const r = await fetch("/api/status", { method: "POST", headers: { "Content-Type": "application/json", "X-FH-Token": window.FH_GUI.token }, body: '{"since": 1e9}' });
      const st = await r.json();
      if (st.run_id > window.FH_GUI.run && st.output_key === window.FH_GUI.output) {
        if (st.state === "running") show("FAST-HIPPOS is updating these results… this page reloads when it is done");
        else if (st.state === "done") { show("Updated: reloading…"); location.reload(); return; }
        else if (banner) show("The update " + st.state + "; this page shows the previous results");
      }
    } catch (e) { /* GUI not reachable: keep the page as it is */ }
    setTimeout(watch, 2500);
  }
  setTimeout(watch, 2500);
})();
</script></head>"""


def _served(job: Job, url_path: str) -> Path | None:
    """The file behind /files/<absolute path>, if it lies in an output folder of this session."""
    p = Path(urllib.parse.unquote(url_path.removeprefix("/files/").split("?")[0])).resolve()
    return p if p.is_file() and any(p.is_relative_to(r) for r in job.roots) else None


def file_url(base: str, path: Path) -> str:
    return f"{base}/files/{urllib.parse.quote(Path(path).resolve().as_posix())}"


def make_handler(token: str, job: Job, ctx: dict | None = None):
    ctx = ctx if ctx is not None else {}

    def quit_server() -> None:
        job.stop()
        if ctx.get("server"):
            threading.Thread(target=ctx["server"].shutdown, daemon=True).start()

    def open_path(path: str) -> None:
        p = Path(path)
        if not p.exists():
            raise ValueError(f"Not found: {p}")
        if p.suffix.lower() == ".html" and ctx.get("base"):
            # through this server, so that the dashboard can apply settings to the run
            job.roots.add((p.parent if p.name == "index.html" else p.parent.parent).resolve())
            webbrowser.open(file_url(ctx["base"], p))
        else:
            _open(path)

    def initial_settings() -> dict:
        if LAST_SETTINGS.exists():
            try:
                return load_toml(LAST_SETTINGS)
            except Exception as e:  # noqa: BLE001 - fall back to the defaults
                log.warning("Could not load %s: %s", LAST_SETTINGS, e)
        return Settings().to_dict()

    api = {
        "schema": lambda q: schema(),
        "initial": lambda q: {"settings": initial_settings(), "from": str(LAST_SETTINGS) if LAST_SETTINGS.exists() else None},
        "defaults": lambda q: {"settings": Settings().to_dict()},
        "browse": lambda q: {"result": browse(q["kind"], q.get("title", "FAST-HIPPOS"), q.get("initial", ""), q.get("types", "file"))},
        "inspect": lambda q: {"files": [inspect_file(Path(p)) | {"path": p} for p in q["paths"]]},
        "cellpose": lambda q: check_cellpose(q.get("python"), bool(q.get("fresh"))),
        "output": lambda q: output_info(q.get("path", ""), job, q.get("settings")),
        "experiment": lambda q: experiment_info(q.get("path", ""), q.get("settings"), job),
        "load": lambda q: {"settings": load_toml(Path(q["path"]))},
        "save": lambda q: (Path(q["path"]).write_text(to_toml(q["settings"]), encoding="utf-8"), {"ok": True})[1],
        "validate": lambda q: (settings_from_plain(q["settings"]), {"ok": True})[1],
        "check": lambda q: {"problems": _check(q["settings"])},
        "run": lambda q: {"run_id": start_reapply_experiment(job, q["settings"]) if q.get("experiment")
                          else start_reapply(job, q["settings"]) if q.get("reapply")
                          else job.start(q["settings"], False, remember=q["settings"])},
        # the run that 'Apply to run' in a dashboard would process (<output>/<image>/dashboard.html)
        "runinfo": lambda q: output_info(str(Path(q["dashboard"]).parent.parent)),
        "apply": lambda q: {"run_id": apply_from_dashboard(job, q["dashboard"], q["toml"], q.get("manual_tsv"), q.get("image"),
                                                           q.get("scope", "all"))},
        # the own settings of an image were removed in the page: a dashboard apply must not bring them back
        "unown": lambda q: (job.removed.setdefault(_key(q["output"]), set()).add(q["image"]), {"ok": True})[1],
        # the settings of the page, kept for the next start of the window (after every change)
        "remember": lambda q: (remember_settings(q["settings"]), {"ok": True})[1],
        "stop": lambda q: (job.stop(), {"ok": True})[1],
        "status": lambda q: job.status(int(q.get("since", 0))),
        "open": lambda q: (open_path(q["path"]), {"ok": True})[1],
        "quit": lambda q: (quit_server(), {"ok": True})[1],
        "prefs": lambda q: save_prefs(q),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json", cookie: bool = False) -> None:
            self.send_response(code)
            if cookie:  # lets this browser load dashboard files; not sent with requests from other sites
                self.send_header("Set-Cookie", f"fh_token={token}; HttpOnly; SameSite=Strict; Path=/")
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            ctx["last"] = time.monotonic()
            if self.path == "/ping":  # lets a second start find this instance
                self._send(200, b'"fast-hippos"')
                return
            if self.path.split("?")[0] in ("/", "/index.html"):
                self._send(200, _page(token), "text/html; charset=utf-8", cookie=True)
                return
            cookies = dict(c.strip().split("=", 1) for c in (self.headers.get("Cookie") or "").split(";") if "=" in c)
            allowed = cookies.get("fh_token") == token
            p = _served(job, self.path) if allowed and self.path.startswith("/files/") else None
            if p is None:
                self._send(404, b"{}")
                return
            body = p.read_bytes()
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if p.suffix.lower() == ".html":  # lets the dashboard talk to this server
                root = p.parent if p.name == "index.html" else p.parent.parent
                inject = (_WATCH.replace("__TOKEN__", token).replace("__RUN__", str(job.run_id))
                          .replace("__OUTPUT__", json.dumps(_key(root))[1:-1]))
                body = body.decode("utf-8").replace("</head>", inject, 1).encode("utf-8")
                ctype = "text/html; charset=utf-8"
            elif p.suffix.lower() == ".js":
                ctype = "text/javascript; charset=utf-8"
            self._send(200, body, ctype)

        def do_POST(self):
            ctx["last"] = time.monotonic()
            name = self.path.strip("/").removeprefix("api/")
            if self.headers.get("X-FH-Token") != token or name not in api:
                self._send(403, b'{"error": "forbidden"}')
                return
            n = int(self.headers.get("Content-Length") or 0)
            try:
                q = json.loads(self.rfile.read(n) or b"{}")
                body = json.dumps(api[name](q), default=str).encode()
                self._send(200, body)
            except Exception as e:  # noqa: BLE001 - reported on the page
                self._send(400, json.dumps({"error": str(e)}).encode())

    return Handler


def _open(path: str) -> None:
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Not found: {p}")
    if p.suffix.lower() == ".html":
        webbrowser.open(p.resolve().as_uri())
    elif hasattr(os, "startfile"):
        os.startfile(p)
    else:
        subprocess.run(["xdg-open", str(p)], check=False)


def _running_instance() -> str | None:
    """URL of a GUI that is already running, if any."""
    try:
        port = json.loads(INSTANCE.read_text())["port"]
        url = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(url + "/ping", timeout=1) as r:
            return url + "/" if r.read() == b'"fast-hippos"' else None
    except Exception:  # noqa: BLE001 - no (reachable) instance
        return None


def _say(msg: str) -> None:
    if sys.stdout:  # None under pythonw.exe
        print(msg, flush=True)
    log.info(msg)


def serve(port: int = 0, open_browser: bool = True) -> None:
    if port == 0 and (url := _running_instance()):
        _say(f"FAST-HIPPOS is already running at {url}")
        if open_browser:
            webbrowser.open(url)
        return
    token = secrets.token_urlsafe(16)
    job = Job()
    ctx: dict = {"last": time.monotonic()}
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, job, ctx))
    ctx["server"] = server
    ctx["base"] = f"http://127.0.0.1:{server.server_address[1]}"
    url = ctx["base"] + "/"
    STATE_DIR.mkdir(exist_ok=True)
    INSTANCE.write_text(json.dumps({"port": server.server_address[1], "pid": os.getpid()}))

    def watchdog():  # stop when no browser has talked to us for a while (e.g. all tabs closed)
        while True:
            time.sleep(30)
            if job.state != "running" and time.monotonic() - ctx["last"] > IDLE_TIMEOUT:
                _say("No browser activity: stopping")
                server.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    _say(f"FAST-HIPPOS {__version__}: the interface runs in your browser at {url}")
    _say("Close it with 'Quit' in the interface" + (" or Ctrl+C here." if sys.stdout else "."))
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        job.stop()
        try:
            if json.loads(INSTANCE.read_text()).get("pid") == os.getpid():
                INSTANCE.unlink()
        except Exception:  # noqa: BLE001, S110 - already gone
            pass


def main_gui() -> int:
    """Entry point of fast-hippos.exe (no console window): the GUI, with a log file instead of a console."""
    STATE_DIR.mkdir(exist_ok=True)
    logging.basicConfig(filename=STATE_DIR / "gui.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        serve(open_browser=not os.environ.get("FAST_HIPPOS_NO_BROWSER"))
    except Exception:
        log.exception("The FAST-HIPPOS interface stopped with an error")
        try:
            import tkinter
            from tkinter import messagebox

            tkinter.Tk().withdraw()
            messagebox.showerror("FAST-HIPPOS", f"FAST-HIPPOS could not start. Details are in {STATE_DIR / 'gui.log'}")
        except Exception:  # noqa: BLE001, S110 - no way left to report it
            pass
        return 1
    return 0
