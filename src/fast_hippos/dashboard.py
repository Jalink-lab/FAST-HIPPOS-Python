"""Self-contained interactive HTML dashboards (one per image + an index page for the run)."""

from __future__ import annotations

import base64
import json
import math
import os
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
            cols[name] = [None if not np.isfinite(v) else (int(v) if float(v).is_integer() and abs(v) < 2**31 else round(float(v), 7)) for v in s.to_numpy(dtype=float)]
        else:
            cols[name] = s.astype(str).tolist()
    return cols


def display_range(result: ImageResult, settings: Settings) -> tuple[float, float]:
    if result.unit == "Intensity":
        finite = result.kymo[np.isfinite(result.kymo)]
        return (float(np.percentile(finite, 1)), float(np.percentile(finite, 99))) if finite.size else (0.0, 1.0)
    return settings.display.min_lifetime, settings.display.max_lifetime


def _png_url(name: str) -> str:
    raw = resources.files("fast_hippos").joinpath("templates", name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def _embed(template: str, data: dict) -> str:
    payload = json.dumps(_clean(data), separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    page = template.replace("__FH_LOGO__", _png_url("logo.png")).replace("__FH_ICON__", _png_url("favicon.png"))
    return page.replace("__FH_DATA__", payload)


# dashboard modules, in load order (templates/dashboard); screening.js is shared with the tests
DASHBOARD_JS = ["core.js", "plot.js", "viewer.js", "traces.js", "kymo.js", "dist.js", "scatter.js", "cellcard.js",
                "table.js", "screenui.js", "export.js", "main.js"]


def _dashboard_template() -> str:
    base = resources.files("fast_hippos").joinpath("templates", "dashboard")
    page = base.joinpath("page.html").read_text(encoding="utf-8")
    css = base.joinpath("style.css").read_text(encoding="utf-8")
    js = "\n".join([_template("screening.js")] + [base.joinpath(f).read_text(encoding="utf-8") for f in DASHBOARD_JS])
    return page.replace("/*__CSS__*/", css).replace("/*__JS__*/", js)


def build_image_data(result: ImageResult, viewer: ViewerData, settings: Settings) -> dict:
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
        "unit": result.unit,
        "is_lifetime": result.unit.startswith("Lifetime"),
        "n_cells": result.n_cells,
        "n_frames": t,
        "frame_interval": result.frame_interval,
        "pixel_size": result.pixel_size,
        "image_size": [w, h],
        "display": {"min": dmin, "max": dmax, "lut": settings.display.lut if settings.display.lut in LUTS else "turbo",
                    "bins": settings.display.histogram_bins},
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
        "population_baseline": cells.attrs.get("population_baseline") if hasattr(cells, "attrs") else None,
        "cells": _columns(cells),
        "luts": _luts(),
    }


def write_image_dashboard(result: ImageResult, viewer: ViewerData, settings: Settings) -> Path:
    path = result.out_dir / "dashboard.html"
    path.write_text(_embed(_dashboard_template(), build_image_data(result, viewer, settings)), encoding="utf-8")
    return path


def write_index(results: list[ImageResult], settings: Settings, out: Path) -> Path:
    images = []
    for r in results:
        cells = r.cells
        images.append({
            "name": r.name,
            "href": Path(os.path.relpath(r.out_dir / "dashboard.html", out)).as_posix(),
            "folder": Path(os.path.relpath(r.out_dir, out)).as_posix(),
            "n_cells": r.n_cells,
            "n_hits": int(cells["hit"].sum()),
            "n_frames": r.shape[0],
            "stimulation": r.events.stimulation,
            "calibration": r.events.calibration,
            "frame_interval": r.frame_interval,
            "median_baseline": float(np.nanmedian(cells["baseline_mean"])) if len(cells) else None,
            "tiles": r.tiles,
            "hits": {
                "cell": cells.loc[cells["hit"], "cell"].tolist(),
                "x": cells.loc[cells["hit"], "abs_x_m"].tolist(),
                "y": cells.loc[cells["hit"], "abs_y_m"].tolist(),
            },
        })
    chunks_file = out / "hit_chunks.json"
    chunks = json.loads(chunks_file.read_text()) if chunks_file.exists() and settings.screening.enabled else []
    files = sorted(p.name for p in out.iterdir() if p.is_file() and p.suffix in (".tsv", ".rgn", ".png", ".txt", ".json"))
    data = {
        "version": __version__,
        "title": out.name,
        "screening": settings.screening.enabled,
        "unit": results[0].unit if results else "",
        "images": images,
        "chunks": chunks,
        "files": files,
    }
    path = out / "index.html"
    path.write_text(_embed(_template("index.html"), data), encoding="utf-8")
    return path
