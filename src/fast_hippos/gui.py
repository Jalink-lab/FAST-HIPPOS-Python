"""Graphical user interface: a small local web app (``fast-hippos gui``).

The settings form is generated from the config dataclasses, so every setting is reachable; ``FIELDS`` adds
labels, help texts, the basic/advanced split and conditions under which a field is shown. Runs are started
as a subprocess (``fast-hippos run <toml>``) whose log is streamed to the page; the settings are saved next
to the output as ``fast_hippos_settings.toml``.

The server only listens on 127.0.0.1 and every API call must carry a random per-session token, so other web
pages in the browser cannot use it.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import sys
import threading
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
SETTINGS_NAME = "fast_hippos_settings.toml"

TCSPC = {"input.modality": ["tcspc"]}
CELLPOSE = {"segmentation.method": ["cellpose"]}
SCREEN = {"screening.enabled": [True]}

# label, help, level ("basic" or "advanced"), optional: widget, choices, show (field -> allowed values).
# Settings that are not listed here are shown in the advanced tab with a generated label.
FIELDS: dict[str, dict] = {
    # ---- input
    "input.files": {"label": "Images", "widget": "files", "level": "basic",
        "help": "Time-lapse images: .tif (ImageJ hyperstack) or .lif. Several files are analyzed in one run."},
    "input.output": {"label": "Output folder", "widget": "folder", "level": "basic"},
    "input.modality": {"label": "Image type", "level": "basic", "choices": {
        "tcspc": "Fitted TCSPC data / TauSeparation (2 lifetime components)", "fast_flim": "Fast FLIM",
        "tau_contrast": "TauContrast", "fd_flim": "Frequency-domain FLIM", "ratio": "Ratio imaging (2 channels)",
        "intensity": "Intensity only"}},
    "input.tau1": {"label": "τ₁ (ns)", "level": "basic", "show": TCSPC, "help": "Lifetime of the first component"},
    "input.tau2": {"label": "τ₂ (ns)", "level": "basic", "show": TCSPC, "help": "Lifetime of the second component"},
    "input.additional_channel": {"label": "Additional channel", "widget": "channel", "level": "basic",
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
    "fdflim.lifetime_from": {"choices": {"phase": "phase", "modulation": "modulation"}},
    # ---- pre-processing
    "preprocess.correct_bidirectional": {"label": "Correct bidirectional scanning phase"},
    "preprocess.correct_drift": {"label": "Correct drift"},
    "preprocess.drift_reference": {"label": "Drift reference frame",
        "choices": {"first": "first", "last": "last", "previous": "previous"}},
    "preprocess.drift_edge_detect": {"label": "Drift: register edges"},
    "preprocess.drift_blur_sigma": {"label": "Drift: blur σ (px)"},
    # ---- segmentation
    "segmentation.method": {"label": "Segmentation", "level": "basic", "choices": {
        "cellpose": "Cellpose", "labelmap": "Existing label image", "threshold": "Threshold + watershed (no Cellpose)"}},
    "segmentation.cellpose_model": {"label": "Cellpose model", "widget": "model", "level": "basic", "show": CELLPOSE,
        "help": "cyto3 / nuclei: Cellpose 3 · cpsam: Cellpose 4 (Cellpose-SAM) · or a custom model file"},
    "segmentation.diameter": {"label": "Cell diameter (px)", "level": "basic", "show": CELLPOSE,
        "help": "0 = automatic (Cellpose 3 models). Setting it is faster."},
    "segmentation.labelmap": {"label": "Label image", "widget": "file", "level": "basic",
        "show": {"segmentation.method": ["labelmap"]}},
    "segmentation.min_cell_size": {"label": "Minimum cell size (px)", "level": "basic"},
    "segmentation.use_gpu": {"label": "Use GPU", "show": CELLPOSE},
    "segmentation.cellpose3_python": {"label": "Cellpose 3 environment (python.exe)", "widget": "python", "show": CELLPOSE,
        "help": "Only needed when Cellpose 3 is not installed in this environment"},
    "segmentation.cellpose4_python": {"label": "Cellpose 4 environment (python.exe)", "widget": "python", "show": CELLPOSE,
        "help": "Only needed when Cellpose 4 is not installed in this environment"},
    "segmentation.cellpose_version": {"label": "Cellpose version", "show": CELLPOSE,
        "help": "Empty = 4 for cpsam, else 3"},
    "segmentation.flow_threshold": {"show": CELLPOSE},
    "segmentation.cellprob_threshold": {"show": CELLPOSE},
    "segmentation.channel": {"label": "Segmentation channel", "widget": "channel",
        "help": "Dedicated channel for segmentation; empty = intensity"},
    "segmentation.gamma": {"label": "Gamma before segmentation", "help": "e.g. 0.5 to enhance dim cells; empty = off"},
    "segmentation.start_frame": {"label": "Projection: first frame"},
    "segmentation.end_frame": {"label": "Projection: last frame"},
    "segmentation.max_circularity": {"label": "Maximum circularity", "help": "1 = no filter; lower removes round objects"},
    "segmentation.min_cell_intensity": {"label": "Minimum cell intensity"},
    "segmentation.classifier": {"label": "Nuclei classifier (.joblib)", "widget": "file",
        "help": "Refines hit positions on the nuclei (fast-hippos train-classifier)"},
    "segmentation.classifier_class": {"label": "Classifier: nuclei class"},
    "segmentation.position_erosion": {"label": "Classifier: erosion (px)"},
    # ---- display
    "display.min_lifetime": {"label": "Display min", "level": "basic", "help": "Lower end of the lifetime / ratio colour scale"},
    "display.max_lifetime": {"label": "Display max", "level": "basic"},
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
    "events.stimulation_frame": {"label": "Stimulation frame", "level": "basic", "widget": "frame",
        "help": "First frame with the stimulus (0-based). Empty = detect automatically"},
    "events.calibration_frame": {"label": "Calibration frame", "level": "basic", "widget": "frame",
        "help": "First frame with the calibration. Empty = detect automatically"},
    "events.baseline_only": {"label": "Baseline only (no stimulation)", "level": "basic"},
    "events.sensitivity": {"label": "Detection sensitivity (σ)"},
    "events.margin": {"label": "Margin (frames)", "help": "Frames excluded before each transition"},
    # ---- screening
    "screening.enabled": {"label": "Screen for hits", "level": "basic"},
    "screening.criteria": {"label": "Hit criteria", "widget": "criteria", "level": "basic", "show": SCREEN},
    "screening.stage_positions_file": {"label": "Stage positions", "widget": "file", "level": "basic", "show": SCREEN,
        "help": "Text file (x0 y0 x1 y1 …, m) or the .lif file. Not needed for "
        "images stitched with 'Stitch tiles' (stored in the image)."},
    "screening.classify_additional_channel": {"label": "Classify cells on the additional channel", "level": "basic", "show": SCREEN},
    "screening.logic": {"label": "Default criterion logic", "choices": {"OR": "OR", "AND": "AND"}, "show": SCREEN},
    "screening.baseline_calibration_diff": {"label": "Gate: calibration − baseline", "widget": "pair", "show": SCREEN,
        "help": "Valid cells only; empty = off"},
    "screening.max_baseline_deviation": {"label": "Gate: |baseline − population| ≤", "show": SCREEN, "help": "Empty = off"},
    "screening.response_window": {"label": "Response window (frames)", "show": SCREEN, "help": "-1 = full response"},
    "screening.response_window_anchor": {"label": "Response window anchor", "show": SCREEN, "choices": {
        "before_calibration": "before calibration", "after_stimulation": "after stimulation"}},
    "screening.response_window_margin": {"label": "Response window margin", "show": SCREEN},
    "screening.rise_time_fraction": {"label": "Rise time fraction", "show": SCREEN},
    "screening.additional_channel_metric": {"label": "Additional channel metric", "show": SCREEN,
        "choices": {"mean": "mean over time", "first": "first frame"}},
    "screening.classification_threshold": {"label": "Classification threshold", "show": SCREEN, "help": "Empty = Otsu"},
    "screening.sort_by": {"label": "Sort hits by", "show": SCREEN, "widget": "metric", "help": "Empty = cell order"},
    "screening.sort_descending": {"label": "Highest first", "show": SCREEN},
    "screening.manual_hits": {"label": "Hand-picked hits (TSV)", "widget": "file", "show": SCREEN,
        "help": "Replaces the criteria (export from a dashboard selection)"},
    "screening.random_hits": {"label": "Random hits (testing)", "show": SCREEN},
    "screening.random_seed": {"label": "Random seed", "show": SCREEN},
    "screening.n_tiles": {"label": "Tiles (nx, ny)", "widget": "pair", "show": SCREEN, "help": "Overruled by stitched metadata"},
    "screening.tile_overlap": {"label": "Tile overlap (%)", "show": SCREEN},
    "screening.max_hits_per_rgn": {"label": "Hits per .rgn file", "show": SCREEN},
    "screening.optimize_path": {"label": "Optimize the route", "show": SCREEN},
    "screening.max_optimization_time": {"label": "Route optimization time (s per file)", "show": SCREEN},
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
            spec = {"key": key, "kind": kind, "optional": optional, "level": "advanced",
                    "label": f.name.replace("_", " ").capitalize(), "default": defaults[section.name][f.name]}
            if kind == "select":
                enum = next(a for a in (get_args(hints[f.name]) or (hints[f.name],)) if isinstance(a, type))
                spec["choices"] = {m.value: m.value for m in enum}
            extra = dict(FIELDS.get(key, {}))
            if "widget" in extra:
                extra["kind"] = extra.pop("widget")
            elif "choices" in extra:
                extra["kind"] = "select"
            spec |= extra
            items.append(spec)
        sections.append({"name": section.name, "title": SECTIONS.get(section.name, section.name),
                         "show": SECTION_SHOW.get(section.name), "fields": items})
    return {"version": __version__, "sections": sections, "metrics": METRICS}


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
    out["size_mb"] = round(path.stat().st_size / 1e6, 1)
    try:
        if path.suffix.lower() in (".tif", ".tiff"):
            import tifffile

            with tifffile.TiffFile(path) as tif:
                s = tif.series[0]
                axes, shape = s.axes, s.shape
                ij = tif.imagej_metadata or {}
                dims = dict(zip(axes, shape, strict=True))
                out |= {"frames": dims.get("T", dims.get("Z", 1)), "channels": dims.get("C", 1),
                        "width": dims.get("X"), "height": dims.get("Y"), "dtype": str(s.dtype),
                        "frame_interval": ij.get("finterval"), "stitched": "Stitched image" in (ij.get("Info") or "")}
                tag = tif.pages[0].tags.get("XResolution")
                if tag and tag.value[0]:
                    out["pixel_size"] = round(tag.value[1] / tag.value[0], 4)
        elif path.suffix.lower() == ".lif":
            from readlif.reader import LifFile

            lif = LifFile(str(path))
            imgs = list(lif.get_iter_image())
            first = imgs[0].info
            out |= {"series": len(imgs), "frames": first["dims"].t, "channels": first["channels"],
                    "width": first["dims"].x, "height": first["dims"].y}
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


def output_info(path: str) -> dict:
    """Whether an output folder holds results that 'reapply' can use."""
    out = Path(path) if path else None
    images = sorted(p.parent.name for p in out.glob("*/traces.npz")) if out and out.is_dir() else []
    return {"exists": bool(out and out.is_dir()), "images": images}


def check_cellpose(python: str | None) -> dict:
    """Cellpose version and GPU of an environment (empty = this one)."""
    exe = python or sys.executable
    if not Path(exe).exists():
        return {"error": f"Not found: {exe}"}
    try:
        r = subprocess.run([exe, "-c", _CELLPOSE_PROBE], capture_output=True, text=True, timeout=120, check=False)
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
    "python": [["Python", "python.exe python"], ["All files", "*.*"]],
    "toml": [["Settings", "*.toml"], ["All files", "*.*"]],
}


def browse(kind: str, title: str, initial: str = "", types: str = "file"):
    """Native file dialog, run in a separate process (Tk needs its own main thread)."""
    if initial and Path(initial).is_file():
        initial = str(Path(initial).parent)
    r = subprocess.run([sys.executable, "-c", _DIALOG, kind, title, initial or "", json.dumps(FILETYPES.get(types, []))],
                       capture_output=True, text=True, check=False)
    return json.loads(r.stdout) if r.stdout.strip() else None


# ---------------------------------------------------------------- runs


class Job:
    """One analysis run in a subprocess; the log is kept for the page."""

    def __init__(self):
        self.lines: list[str] = []
        self.proc: subprocess.Popen | None = None
        self.state = "idle"  # idle | running | done | failed | stopped
        self.output: str | None = None
        self.lock = threading.Lock()

    def start(self, settings: dict, reapply: bool) -> None:
        settings_from_plain(settings)  # validate before starting
        out = Path(settings["input"]["output"])
        out.mkdir(parents=True, exist_ok=True)
        toml = out / SETTINGS_NAME
        header = f"# FAST-HIPPOS {__version__} settings, written by the GUI\n# Run again with: fast-hippos run {SETTINGS_NAME}"
        toml.write_text(to_toml(settings, header), encoding="utf-8")
        STATE_DIR.mkdir(exist_ok=True)
        LAST_SETTINGS.write_text(to_toml(settings, header), encoding="utf-8")
        cmd = [sys.executable, "-u", "-m", "fast_hippos.cli", "reapply" if reapply else "run", str(toml)]
        with self.lock:
            self.lines, self.state, self.output = [f"$ fast-hippos {cmd[4]} {toml}"], "running", str(out)
        env = os.environ | {"PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                     errors="replace", env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._read, daemon=True).start()

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
            out = {"state": self.state, "lines": self.lines[since:], "n": len(self.lines), "output": self.output}
        if self.output and self.state == "done":
            o = Path(self.output)
            out["index"] = str(o / "index.html") if (o / "index.html").exists() else None
            out["dashboards"] = [str(p) for p in sorted(o.glob("*/dashboard.html"))]
        return out


# ---------------------------------------------------------------- server


def _page(token: str) -> bytes:
    from .dashboard import _png_url

    html = resources.files("fast_hippos").joinpath("templates", "gui.html").read_text(encoding="utf-8")
    html = html.replace("__FH_LOGO__", _png_url("logo.png")).replace("__FH_ICON__", _png_url("favicon.png"))
    return html.replace("__FH_TOKEN__", token).encode("utf-8")


def make_handler(token: str, job: Job):
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
        "cellpose": lambda q: check_cellpose(q.get("python")),
        "output": lambda q: output_info(q.get("path", "")),
        "load": lambda q: {"settings": load_toml(Path(q["path"]))},
        "save": lambda q: (Path(q["path"]).write_text(to_toml(q["settings"]), encoding="utf-8"), {"ok": True})[1],
        "validate": lambda q: (settings_from_plain(q["settings"]), {"ok": True})[1],
        "run": lambda q: (job.start(q["settings"], bool(q.get("reapply"))), {"ok": True})[1],
        "stop": lambda q: (job.stop(), {"ok": True})[1],
        "status": lambda q: job.status(int(q.get("since", 0))),
        "open": lambda q: (_open(q["path"]), {"ok": True})[1],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.split("?")[0] in ("/", "/index.html"):
                self._send(200, _page(token), "text/html; charset=utf-8")
            else:
                self._send(404, b"{}")

        def do_POST(self):
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


def serve(port: int = 0, open_browser: bool = True) -> None:
    token = secrets.token_urlsafe(16)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, Job()))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"FAST-HIPPOS GUI at {url}  (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
