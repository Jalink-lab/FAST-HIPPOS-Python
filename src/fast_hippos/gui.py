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
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import fields
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

# label, help, level ("basic" or "advanced"), optional: widget, choices, show (field -> allowed values).
# Settings that are not listed here are shown in the advanced tab with a generated label.
FIELDS: dict[str, dict] = {
    # ---- input
    "input.files": {"label": "Images", "widget": "files",
        "help": "Time-lapse images: .tif (ImageJ hyperstack) or .lif, or a folder of tiles exported from LAS X "
        "(stitched by the stage positions of the tiles). Several are analyzed in one run."},
    "input.output": {"label": "Output folder", "widget": "folder"},
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
    "preprocess.drift_blur_sigma": {"label": "Drift: blur σ (px)"},
    # ---- segmentation
    "segmentation.method": {"label": "Segmentation", "choices": {
        "cellpose": "Cellpose", "labelmap": "Existing label image", "threshold": "Threshold + watershed (no Cellpose)"}},
    "segmentation.cellpose_model": {"label": "Cellpose model", "widget": "model", "show": CELLPOSE,
        "help": "cyto3 / nuclei: Cellpose 3 · cpsam: Cellpose 4 (Cellpose-SAM) · or a custom model file"},
    "segmentation.diameter": {"label": "Cell diameter (px)", "show": CELLPOSE,
        "help": "0 = automatic (Cellpose 3 models). Setting it is faster."},
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
    "display.overlay_smooth_xy": {"label": "Overlay smoothing xy (px)"},
    "display.overlay_smooth_t": {"label": "Overlay smoothing t (frames)"},
    "display.dashboard_max_size": {"label": "Dashboard overview size (px)"},
    "display.dashboard_tiles": {"label": "Full-resolution tiles for large images"},
    "display.save_png_plots": {"label": "Save PNG plots"},
    "display.save_tables": {"label": "Save per-frame trace tables"},
    # ---- events
    "events.stimulation_frame": {"label": "Stimulation frame", "widget": "frame",
        "help": "First frame with the stimulus (0-based). Empty = detect automatically"},
    "events.calibration_frame": {"label": "Calibration frame", "widget": "frame",
        "help": "First frame with the calibration. Empty = detect automatically"},
    "events.baseline_only": {"label": "Baseline only (no stimulation)"},
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
    "screening.response_window": {"label": "Response window (frames)", "enable": SCREEN, "help": "-1 = full response"},
    "screening.response_window_anchor": {"label": "Response window anchor", "enable": SCREEN, "choices": {
        "before_calibration": "before calibration", "after_stimulation": "after stimulation"}},
    "screening.response_window_margin": {"label": "Response window margin", "enable": SCREEN},
    "screening.rise_time_fraction": {"label": "Rise time fraction", "enable": SCREEN},
    "screening.additional_channel_metric": {"label": "Additional channel metric", "enable": SCREEN,
        "choices": {"mean": "mean over time", "first": "first frame"}},
    "screening.classification_threshold": {"label": "Classification threshold", "enable": SCREEN, "help": "Empty = Otsu"},
    "screening.sort_by": {"label": "Sort hits by", "enable": SCREEN, "widget": "metric", "help": "Empty = cell order"},
    "screening.sort_descending": {"label": "Highest first", "enable": SCREEN},
    "screening.manual_hits": {"label": "Hand-picked hits (TSV)", "widget": "file", "enable": SCREEN,
        "help": "Replaces the criteria (export from a dashboard selection)"},
    "screening.random_hits": {"label": "Random hits (testing)", "enable": SCREEN},
    "screening.random_seed": {"label": "Random seed", "enable": SCREEN},
    "screening.n_tiles": {"label": "Tiles (nx, ny)", "widget": "pair", "enable": SCREEN, "help": "Overruled by stitched metadata"},
    "screening.tile_overlap": {"label": "Tile overlap (%)", "enable": SCREEN},
    "screening.max_hits_per_rgn": {"label": "Hits per .rgn file", "enable": SCREEN},
    "screening.optimize_path": {"label": "Optimize the route", "enable": SCREEN},
    "screening.max_optimization_time": {"label": "Route optimization time (s per file)", "enable": SCREEN},
}

# Shown when hovering over a setting in the interface: what it does and when to change it, in plain words. The short
# 'help' line under a field stays; this is the fuller explanation. Every setting has one (checked by a test).
TIPS: dict[str, str] = {
    # ---- images
    "input.files": "The time-lapse images to analyze. Each .tif is one image; a .lif file can hold many images "
        "(series), and a folder of tiles exported from LAS X is stitched into one image. All are analyzed with the "
        "same settings, and the screening is done over all of them together.",
    "input.output": "Folder for all results: tables, plots, dashboards and .rgn files. Each image gets a subfolder. "
        "An existing output folder is overwritten by a new run, or re-used by 'Re-apply screening'.",
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
        "and .lif tile scans it is done per tile.",
    "preprocess.bidirectional_axis": "Direction of the shift between forward and backward scan lines: along y when "
        "the fast scan direction is vertical in the image (Leica Stellaris), along x when it is horizontal. A "
        "property of the microscope.",
    "preprocess.correct_drift": "Align all frames to each other, to correct a slow movement of the sample during the "
        "time-lapse. Needed when cells visibly move; otherwise traces mix neighbouring cells.",
    "preprocess.drift_reference": "Frame that the others are aligned to: the first, the last, or each frame to the "
        "one before it (best for slow, gradual drift).",
    "preprocess.drift_edge_detect": "Align on the edges in the image instead of the intensity itself. Helps when the "
        "brightness changes during the experiment.",
    "preprocess.drift_blur_sigma": "Blurring (pixels) before aligning, so that noise does not disturb the alignment. "
        "Larger = more robust, less precise.",
    # ---- segmentation
    "segmentation.method": "How the cells are found. Cellpose: a deep-learning model (best, uses the GPU). Existing "
        "label image: cells outlined elsewhere (e.g. in Fiji). Threshold + watershed: a simple classical method, no "
        "Cellpose needed.",
    "segmentation.cellpose_model": "The Cellpose model. cyto3: whole cells (Cellpose 3). nuclei: nuclei only. cpsam: "
        "Cellpose-SAM (Cellpose 4), generally the most accurate but slower. Or a model you trained yourself.",
    "segmentation.diameter": "Typical cell diameter in pixels. 0 = let Cellpose 3 estimate it per image. Giving it "
        "is faster and often more consistent.",
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
        "Only affects finding the cells, not the measurements. Empty = off.",
    "segmentation.start_frame": "The cells are found in the average of a range of frames. First frame of that range "
        "(0-based). Empty = from the start.",
    "segmentation.end_frame": "Last frame (0-based, included) of the range that is averaged for finding the cells. "
        "Empty = to the end.",
    "segmentation.max_circularity": "Remove objects that are too round, e.g. dead or rounded-up cells. A perfect "
        "circle is 1, so 1 means no filter; 0.9 removes the roundest objects.",
    "segmentation.min_cell_intensity": "Remove cells whose mean intensity is below this value, e.g. untransfected "
        "or out-of-focus cells. 0 = no filter.",
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
    "display.overlay_smooth_xy": "Spatial smoothing (pixels) of the lifetime colour overlay in the dashboard. Only "
        "for display.",
    "display.overlay_smooth_t": "Temporal smoothing (frames) of the lifetime colour overlay in the dashboard. Only "
        "for display.",
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
    # ---- stimulation and calibration
    "events.stimulation_frame": "First frame in which the stimulus acts (0-based). The frames before it are the "
        "baseline. Empty = found automatically as the first clear jump in the average trace.",
    "events.calibration_frame": "First frame with the calibration stimulus (e.g. forskolin + IBMX), which gives the "
        "maximal response. Empty = found automatically as the second jump.",
    "events.baseline_only": "For experiments without a stimulus: the whole time-lapse is baseline; no stimulation or "
        "calibration is looked for.",
    "events.sensitivity": "How far a jump in the average trace must stand out from the noise to count as a "
        "stimulation or calibration, in units of the noise σ. Lower = more sensitive, but more false detections. "
        "Only used when the frames are empty.",
    "events.margin": "Frames left out just before each transition (end of the baseline and end of the response), "
        "because the change may already start there.",
    # ---- screening
    "screening.enabled": "Select hit cells with the criteria and write their stage positions to .rgn files for "
        "LAS X, to revisit them on the microscope.",
    "screening.criteria": "Conditions that a cell must meet to be a hit, e.g. response_max_diff > 0.3. AND: must "
        "pass. OR: at least one of the OR criteria must pass. Hover over a metric for its meaning; thresholds can be "
        "tuned later in the dashboard.",
    "screening.stage_positions_file": "Only for images without stage positions of their own: the .lif file of the "
        "experiment, or a text file with X Y in metres per image (x0 y0 x1 y1 …).",
    "screening.classify_additional_channel": "Split the cells in two groups on the intensity of the additional "
        "channel (e.g. transfected or not), with an automatic threshold. Adds a class column to the tables.",
    "screening.logic": "AND or OR, for criteria that do not set their own.",
    "screening.baseline_calibration_diff": "Quality check: only cells whose calibration response (calibration − "
        "baseline) lies in this range can be hits. Removes cells that do not respond to the calibration. Empty = "
        "off.",
    "screening.max_baseline_deviation": "Quality check: only cells whose baseline differs at most this much from "
        "the population baseline can be hits. Removes outliers. Empty = off.",
    "screening.response_window": "Length (frames) of the part of the response used for the 'mean' response metrics. "
        "-1 = the whole response, from stimulation to calibration.",
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
    "screening.sort_descending": "Sort the hits from the highest to the lowest value.",
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
}

FD = {"input.modality": ["fd_flim"]}

# Cards of the form: the basic settings, then the advanced ones under subheadings (an expanding pane).
# Every setting appears exactly once (checked by the tests).
LAYOUT = [
    {"title": "Images", "basic": ["input.files", "input.output", "input.modality", "input.tau1", "input.tau2",
                                  "input.additional_channel"],
     "advanced": [
         ("Channels and metadata", ["input.intensity_channel", "input.pixel_size", "input.default_frame_interval",
                                    "input.remove_last_frame", "input.series"]),
         ("Pre-processing", ["preprocess.correct_bidirectional", "preprocess.bidirectional_axis", "preprocess.correct_drift", "preprocess.drift_reference",
                             "preprocess.drift_edge_detect", "preprocess.drift_blur_sigma"]),
         ("Frequency-domain FLIM", ["fdflim.reference", "fdflim.background", "fdflim.phases", "fdflim.frequency_mhz",
                                    "fdflim.tau_ref", "fdflim.lifetime_from"], FD),
     ]},
    {"title": "Cell segmentation", "basic": ["segmentation.method", "segmentation.cellpose_model", "segmentation.diameter",
                                             "segmentation.labelmap", "segmentation.min_cell_size"],
     "advanced": [
         ("Cellpose", ["segmentation.use_gpu", "segmentation.flow_threshold", "segmentation.cellprob_threshold",
                       "segmentation.cellpose_version", "segmentation.channel", "segmentation.gamma"], CELLPOSE),
         ("Cellpose environments", ["segmentation.cellpose3_python", "segmentation.cellpose4_python"], CELLPOSE),
         ("Projection used for segmentation", ["segmentation.start_frame", "segmentation.end_frame"]),
         ("Cell filters", ["segmentation.max_circularity", "segmentation.min_cell_intensity"]),
         ("Hit positions on the nuclei", ["segmentation.classifier", "segmentation.classifier_class",
                                          "segmentation.position_erosion"]),
     ]},
    {"title": "Stimulation and calibration", "basic": ["events.stimulation_frame", "events.calibration_frame",
                                                       "events.baseline_only"],
     "advanced": [
         ("Automatic detection", ["events.sensitivity", "events.margin"]),
         ("Traces", ["display.smooth_traces"]),
     ]},
    {"title": "Screening", "basic": ["screening.enabled", "screening.criteria", "screening.classify_additional_channel"],
     "advanced": [
         ("Criteria", ["screening.logic", "screening.rise_time_fraction"]),
         ("Response window", ["screening.response_window", "screening.response_window_anchor",
                              "screening.response_window_margin"]),
         ("Quality gates", ["screening.baseline_calibration_diff", "screening.max_baseline_deviation"]),
         ("Additional channel", ["screening.additional_channel_metric", "screening.classification_threshold"]),
         ("Hit list", ["screening.sort_by", "screening.sort_descending", "screening.manual_hits"]),
         ("Stage positions and .rgn files", ["screening.stage_positions_file", "screening.n_tiles", "screening.tile_overlap", "screening.max_hits_per_rgn",
                                             "screening.optimize_path", "screening.max_optimization_time"]),
         ("Testing", ["screening.random_hits", "screening.random_seed"]),
     ]},
    {"title": "Display and output", "basic": [],
     "note": "The defaults suit most runs; colours and ranges can also be changed in the dashboard.",
     "advanced": [
         ("Colour scale", ["display.lut", "display.min_lifetime", "display.max_lifetime"]),
         ("Lifetime overlay", ["display.overlay_smooth_xy", "display.overlay_smooth_t"]),
         ("Dashboard", ["display.dashboard", "display.dashboard_max_size", "display.dashboard_max_megapixels",
                        "display.dashboard_tiles", "display.histogram_bins"]),
         ("Files", ["display.save_png_plots", "display.save_tables"]),
     ]},
]

# Conditions under which a setting is used; otherwise it is greyed out, with the reason as tooltip.
# {field: [allowed values]} or {field: {"set": bool}} or {field: {"not": [values]}}; all must hold.
ENABLE = {
    "events.stimulation_frame": {"events.baseline_only": [False]},
    "events.calibration_frame": {"events.baseline_only": [False]},
    "events.sensitivity": {"events.baseline_only": [False], "events.stimulation_frame": {"set": False}},
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
    "screening.response_window_anchor": {"screening.response_window": {"not": [-1]}},
    "screening.response_window_margin": {"screening.response_window": {"not": [-1]}},
    "screening.sort_descending": {"screening.sort_by": {"set": True}},
    "screening.random_seed": {"screening.random_hits": {"set": True}},
    "screening.max_optimization_time": {"screening.optimize_path": [True]},
    "segmentation.classifier_class": {"segmentation.classifier": {"set": True}},
    "segmentation.position_erosion": {"segmentation.classifier": {"set": True}},
    "display.dashboard_max_size": {"display.dashboard": [True]},
    "display.dashboard_max_megapixels": {"display.dashboard": [True]},
    "display.dashboard_tiles": {"display.dashboard": [True]},
    "display.histogram_bins": {"display.dashboard": [True]},
}
REASONS = {  # why a condition on this field disables others
    "events.baseline_only": "'Baseline only' is on",
    "events.stimulation_frame": "only for automatic detection (no stimulation frame set)",
    "preprocess.correct_drift": "drift correction is off",
    "preprocess.correct_bidirectional": "bidirectional correction is off",
    "screening.enabled": "screening is off",
    "screening.manual_hits": "replaced by the hand-picked hits",
    "screening.random_hits": "replaced by random hits",
    "input.additional_channel": "needs an additional channel",
    "screening.classify_additional_channel": "classification is off",
    "screening.response_window": "only for a timed response window (not -1)",
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
               "advanced": [{"title": a[0], "keys": a[1], "show": a[2] if len(a) > 2 else None} for a in c["advanced"]]}
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
    for section, values in settings.items():
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


def output_info(path: str, job: Job | None = None) -> dict:
    """Whether an output folder holds results that 'reapply' can use (they can then be opened via the GUI)."""
    out = Path(path) if path else None
    images = sorted(p.parent.name for p in out.glob("*/traces.npz")) if out and out.is_dir() else []
    if images and job is not None:
        job.roots.add(out.resolve())
    return {"exists": bool(out and out.is_dir()), "images": images, "index": bool(out and (out / "index.html").exists())}


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
        r = subprocess.run([exe, "-c", _CELLPOSE_PROBE], capture_output=True, text=True, timeout=120, check=False,
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
        self.run_id = 0
        self.roots: set[Path] = set()  # output folders whose files may be served (dashboards)
        self.lock = threading.Lock()

    def start(self, settings: dict, reapply: bool, source: str = "gui") -> int:
        if self.state == "running":
            raise ValueError("A run is already in progress")
        settings_from_plain(settings)  # validate before starting
        out = Path(settings["input"]["output"])
        out.mkdir(parents=True, exist_ok=True)
        toml = out / SETTINGS_NAME
        header = f"# FAST-HIPPOS {__version__} settings, written by the GUI\n# Run again with: fast-hippos-cli run {SETTINGS_NAME}"
        toml.write_text(to_toml(settings, header), encoding="utf-8")
        STATE_DIR.mkdir(exist_ok=True)
        LAST_SETTINGS.write_text(to_toml(settings, header), encoding="utf-8")
        cmd = [_python(), "-u", "-m", "fast_hippos.cli", "reapply" if reapply else "run", str(toml)]
        with self.lock:
            self.lines, self.state, self.output = [f"$ fast-hippos {cmd[4]} {toml}"], "running", str(out)
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

    def status(self, since: int) -> dict:
        with self.lock:
            out = {"state": self.state, "lines": self.lines[since:], "n": len(self.lines), "output": self.output,
                   "output_key": _key(self.output) if self.output else None,
                   "run_id": self.run_id, "source": self.source,
                   "settings": self.settings if self.source == "dashboard" else None}
        if self.output and self.state == "done":
            o = Path(self.output)
            out["index"] = str(o / "index.html") if (o / "index.html").exists() else None
            out["dashboards"] = [str(p) for p in sorted(o.glob("*/dashboard.html"))]
        return out


def apply_from_dashboard(job: Job, dashboard: str, toml_text: str, manual_tsv: str | None = None) -> int:
    """Re-apply the screening settings of a dashboard to its whole run (the 'Apply to run' button)."""
    out = Path(dashboard).parent.parent  # <output>/<image>/dashboard.html
    used = out / "settings_used.json"
    if not used.exists():
        raise ValueError(f"No settings_used.json in {out}: run the analysis again with this version first")
    base = json.loads(used.read_text(encoding="utf-8"))
    override = out / "screening_from_dashboard.toml"  # kept as a record of what was applied
    override.write_text(toml_text, encoding="utf-8")
    if manual_tsv:
        import tomllib

        name = tomllib.loads(toml_text).get("screening", {}).get("manual_hits") or "manual_hits.tsv"
        (out / name).write_text(manual_tsv, encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        base_toml = Path(tmp) / "base.toml"
        base_toml.write_text(to_toml(base), encoding="utf-8")
        merged = Settings.from_toml(base_toml, overrides=[override]).to_dict()
    merged["input"]["output"] = str(out)
    return job.start(merged, reapply=True, source="dashboard")


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
        "output": lambda q: output_info(q.get("path", ""), job),
        "load": lambda q: {"settings": load_toml(Path(q["path"]))},
        "save": lambda q: (Path(q["path"]).write_text(to_toml(q["settings"]), encoding="utf-8"), {"ok": True})[1],
        "validate": lambda q: (settings_from_plain(q["settings"]), {"ok": True})[1],
        "check": lambda q: {"problems": _check(q["settings"])},
        "run": lambda q: {"run_id": job.start(q["settings"], bool(q.get("reapply")))},
        "apply": lambda q: {"run_id": apply_from_dashboard(job, q["dashboard"], q["toml"], q.get("manual_tsv"))},
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
