"""Self-contained interactive HTML dashboards (one per image + an index page for the run)."""

from __future__ import annotations

import base64
import json
import math
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from matplotlib import colormaps

from . import __version__
from .config import METRICS
from .screening import timed_window
from .viewer_data import ViewerData, float_b64, frame_urls, labels_url, png_data_url

if TYPE_CHECKING:
    from .config import Settings
    from .pipeline import ImageResult

LUTS = ["turbo", "viridis", "plasma", "magma", "inferno", "cividis", "gray"]


def _template(name: str) -> str:
    return resources.files("fast_hippos").joinpath("templates", name).read_text(encoding="utf-8")


def _luts() -> dict[str, str]:
    out = {}
    for name in LUTS:
        rgb = (colormaps[name](np.linspace(0, 1, 256))[:, :3] * 255).round().astype(np.uint8)
        out[name] = base64.b64encode(rgb.tobytes()).decode("ascii")
    return out


def _clean(v):
    """JSON-safe values: NaN/inf -> None, numpy scalars -> Python."""
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return f if math.isfinite(f) else None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def _columns(df: pd.DataFrame) -> dict[str, list]:
    cols = {}
    for name in df.columns:
        s = df[name]
        if s.dtype == bool:
            cols[name] = s.astype(int).tolist()
        elif pd.api.types.is_numeric_dtype(s):
            # stage positions in m keep full precision (the dashboard's routes must match those of the run)
            digits = 12 if name.endswith("_m") else 7
            cols[name] = [None if not np.isfinite(v) else (int(v) if float(v).is_integer() and abs(v) < 2**31 else round(float(v), digits)) for v in s.to_numpy(dtype=float)]
        else:
            cols[name] = s.astype(str).tolist()
    return cols


def display_range(result: ImageResult, settings: Settings) -> tuple[float, float]:
    """Initial colour / axis range: display.min_lifetime and max_lifetime if set, else from the data (1st-99th
    percentile of all cell values, rounded outward to a round step). The dashboard can change it later."""
    lo, hi = auto_range(result.kymo)
    d = settings.display
    lo = lo if d.min_lifetime is None else d.min_lifetime
    hi = hi if d.max_lifetime is None else d.max_lifetime
    return (lo, hi) if hi > lo else (lo, lo + 1.0)


def auto_range(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return 0.0, 1.0
    p1, p99 = (float(x) for x in np.percentile(finite, [1, 99]))
    span = p99 - p1 or abs(p99) or 1.0
    raw = span / 10
    step = min((m * 10 ** math.floor(math.log10(raw)) for m in (1, 2, 2.5, 5, 10)), key=lambda s: abs(s - raw))
    return round(math.floor(p1 / step) * step, 10), round(math.ceil(p99 / step) * step, 10)


def _png_url(name: str) -> str:
    raw = resources.files("fast_hippos").joinpath("templates", name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def _embed(template: str, data: dict) -> str:
    payload = json.dumps(_clean(data), separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    page = template.replace("__FH_LOGO__", _png_url("logo.png")).replace("__FH_ICON__", _png_url("favicon.png"))
    return page.replace("__FH_DATA__", payload)


# page modules, in load order; screening.js is shared with the tests, templates/common by the dashboard and the Overview
COMMON_JS = ["base.js", "plot.js"]
DASHBOARD_JS = ["core.js", "persist.js", "viewer.js", "traces.js", "kymo.js", "dist.js", "scatter.js", "cellcard.js",
                "table.js", "screenui.js", "export.js", "main.js"]


def _bundle(folder: str, css: list[str], js: list[str]) -> str:
    """templates/<folder>/page.html with the shared files of templates/common and its own CSS and scripts inlined."""
    t = resources.files("fast_hippos").joinpath("templates")

    def read(*parts: str) -> str:
        return t.joinpath(*parts).read_text(encoding="utf-8")

    styles = "\n".join([read("common", "base.css")] + [read(folder, f) for f in css])
    scripts = "\n".join([read("screening.js")] + [read("common", f) for f in COMMON_JS] + [read(folder, f) for f in js])
    return read(folder, "page.html").replace("/*__CSS__*/", styles).replace("/*__JS__*/", scripts)


def _dashboard_template() -> str:
    return _bundle("dashboard", ["style.css"], DASHBOARD_JS)


SCATTER_AT_FRAME = {"value_at_frame": "@value", "additional_at_frame": "@additional"}


def _axis(name: str) -> str:
    """A scatter axis of the settings as the dashboard names it (value_at_frame -> @value)."""
    return SCATTER_AT_FRAME.get(name, name)


def build_image_data(result: ImageResult, viewer: ViewerData, settings: Settings, route=None) -> dict:
    ev = result.events
    sc = settings.screening
    cells = result.cells
    tw = timed_window(ev, sc)
    dmin, dmax = display_range(result, settings)
    criteria = [
        f"{c.metric} {c.op} {c.value}" + (f" and {c.value2}" if c.op == "between" else "") for c in sc.criteria
    ]
    t, h, w = result.shape
    return {
        "version": __version__,
        "name": result.name,
        # the image's own settings (Settings.image), if any: shown in the dashboard and kept by 'Apply to all images'
        "own_settings": settings.image.get(result.name) or None,
        "unit": result.unit,
        "is_lifetime": result.unit.startswith("Lifetime"),
        "n_cells": result.n_cells,
        "n_frames": t,
        "frame_interval": result.frame_interval,
        "pixel_size": result.pixel_size,
        "image_size": [w, h],
        "display": {"min": dmin, "max": dmax, "lut": settings.display.lut if settings.display.lut in LUTS else "turbo",
                    "bins": settings.display.histogram_bins,
                    # how the views start: the trace view, the axes of the scatter plot
                    "traces": settings.display.traces_view,
                    "sx": _axis(settings.display.scatter_x), "sy": _axis(settings.display.scatter_y),
                    "slogx": settings.display.scatter_log_x, "slogy": settings.display.scatter_log_y},
        "smooth_traces": settings.display.smooth_traces,
        "viewer": {
            "factor": viewer.factor,
            "frames": viewer.frames.tolist(),
            "lo": viewer.lo,
            "hi": viewer.hi,
            "images": frame_urls(viewer),
            "projection": png_data_url(viewer.projection8),
            "labels": labels_url(viewer.labels),
            "size": [int(viewer.labels.shape[1]), int(viewer.labels.shape[0])],
            "tiles": viewer.tiles,
        },
        "kymo": float_b64(result.kymo),
        "additional": float_b64(result.additional) if result.additional is not None else None,
        "order": result.order.tolist(),
        "events": ev.to_dict() | {"timed_window": [tw.start, tw.stop]},
        "screening": {
            "enabled": sc.enabled,
            "logic": sc.logic,
            "criteria": criteria,
            "n_hits": int(cells["hit"].sum()),
            "classification_threshold": result.classification_threshold,
            "random": bool(sc.random_hits),
        },
        # starting point for the live screening panel (recomputed in the browser by screening.js)
        "screen": {
            "events": {"stimulation": ev.stimulation, "calibration": ev.calibration, "baseline_only": ev.baseline_only,
                       "margin": ev.margin, "detected": ev.detected},
            # how the frames of this image were given (None = detected): an export keeps what was not changed
            "event_settings": {"stimulation_frame": settings.events.stimulation_frame,
                               "calibration_frame": settings.events.calibration_frame,
                               "no_calibration": settings.events.no_calibration},
            "params": {
                "smooth_traces": settings.display.smooth_traces,
                "response_window": sc.response_window,
                "response_window_anchor": sc.response_window_anchor,
                "response_window_margin": sc.response_window_margin,
                "baseline_calibration_diff": list(sc.baseline_calibration_diff) if sc.baseline_calibration_diff else None,
                "max_baseline_deviation": sc.max_baseline_deviation,
                "rise_time_fraction": sc.rise_time_fraction,
                "additional_channel_metric": sc.additional_channel_metric,
                "classify_additional_channel": sc.classify_additional_channel,
                "classification_threshold": result.classification_threshold,
                "logic": sc.logic.upper(),
                "criteria": [{"metric": c.metric, "op": c.op, "value": c.value, "value2": c.value2,
                              "logic": (c.logic or sc.logic).upper()} for c in sc.criteria],
                "sort_by": sc.sort_by,
                "sort_descending": sc.sort_descending,
                "max_hits_per_rgn": sc.max_hits_per_rgn,
                "optimize_path": sc.optimize_path,
            },
            "metrics": METRICS,
        },
        # visiting order of the hits per .rgn chunk, as optimized by the run (row indices); None = not computed
        "route": route if route and any(route) else None,
        # where the routes start (centre of the first tile of the scan, stage frame in m), as in the run
        "route_start": [result.tiles[0][0] + result.tiles[0][2] / 2, result.tiles[0][1] + result.tiles[0][3] / 2] if result.tiles else None,
        "population_baseline": cells.attrs.get("population_baseline") if hasattr(cells, "attrs") else None,
        # pos_x/y_px is the cell position used for the stage positions (the centroid, or the centre of the nucleus with
        # a nuclei classifier); the centroid itself stays in the tables of the output folder
        "cells": _columns(cells.drop(columns=["centroid_x", "centroid_y"], errors="ignore")),
        "luts": _luts(),
    }


def write_image_dashboard(result: ImageResult, viewer: ViewerData, settings: Settings, route=None) -> Path:
    path = result.out_dir / "dashboard.html"
    path.write_text(_embed(_dashboard_template(), build_image_data(result, viewer, settings, route)), encoding="utf-8")
    return path
