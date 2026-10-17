"""The run Overview (index.html): one row per image, linked comparison panels, per-image hit maps and exports.

build_overview_data() turns the results of a run into the data that the page shows; everything comes from arrays
already in memory at the end of a run (no extra reading of images). The page itself is templates/overview/.
Images are mostly different samples, so nothing is pooled over images except a few run totals.
"""

from __future__ import annotations

import base64
import io
import json
import math
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from . import __version__
from .config import METRICS
from .viewer_data import float_b64

if TYPE_CHECKING:
    from .config import Settings
    from .pipeline import ImageResult

MAX_CELLS = 5000  # per image in the page (a subsample that keeps every hit); counts and medians use all cells
BANDS = (10, 25, 50, 75, 90)  # percentiles of the response over time
THUMB = 128  # px, longest side of the thumbnail
CELL_COLUMNS = ["cell", "hit", "valid", "abs_x_m", "abs_y_m", "area_px", "mean_intensity", "circularity",
                "class_additional", *METRICS]
RESPONSE_METRICS = ("response_mean_diff", "response_max_diff", "response_mean_abs", "response_max_abs",
                    "response_max_diff_pop", "response_fraction")
SUMMARY_FILE = "run_summary.tsv"

# QC flags: warnings only (they never filter anything); every threshold is stated in the text shown on hover
QC = {
    "few_cells": "Few cells: fewer than 20, or fewer than 25 % of the median of the images in the run",
    "low_valid": "Low fraction of valid cells (cells that pass the quality gates): below 70 % (warning), below 40 % (bad)",
    "no_stimulation": "No stimulation found, while most images in the run have one",
    "no_calibration": "No calibration found, while most images in the run have one",
    "event_offset": "The stimulation frame differs more than 3 frames from the most common one in the run (only "
                    "meaningful when all images follow the same protocol)",
    "no_cal_response": "No calibration response: the median calibration − baseline is below twice the median spread "
                       "of the baselines (|baseline − population|)",
    "no_positions": "No stage positions: the hits of this image cannot be visited on the microscope",
    "no_hits": "No hits in this image",
}


def _median(values) -> float | None:
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    return float(np.median(a)) if a.size else None


def response_metric(settings: Settings) -> str:
    """The response metric of the table: that of the first criterion that uses one, else response_max_diff."""
    for c in settings.screening.criteria:
        if c.metric in RESPONSE_METRICS:
            return c.metric
    return "response_max_diff"


def _bands(kymo: np.ndarray, columns: np.ndarray) -> str | None:
    """Percentiles BANDS per frame of the given cells, as (5, T) float32 base64; None without cells."""
    if not columns.any():
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # frames without values
        q = np.nanpercentile(kymo[:, columns], BANDS, axis=1)
    return float_b64(np.asarray(q, dtype=np.float32))


def _subsample(cells: pd.DataFrame, seed: int) -> pd.DataFrame:
    if len(cells) <= MAX_CELLS:
        return cells
    hits = cells[cells["hit"].astype(bool)]
    rest = cells[~cells["hit"].astype(bool)]
    keep = rest.sample(n=max(0, MAX_CELLS - len(hits)), random_state=seed)
    return pd.concat([hits, keep]).sort_index()


def _cell_columns(cells: pd.DataFrame) -> dict[str, str]:
    """Per-cell values as float32 base64 columns (NaN for missing)."""
    out = {}
    for name in CELL_COLUMNS:
        if name in cells:
            out[name] = float_b64(pd.to_numeric(cells[name], errors="coerce").to_numpy(dtype=np.float32))
    return out


def thumbnail(projection8: np.ndarray) -> str:
    """A small PNG (data URL) of the intensity projection."""
    from PIL import Image

    img = Image.fromarray(np.asarray(projection8, dtype=np.uint8))
    img.thumbnail((THUMB, THUMB))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _flags(img: dict, run: dict, screening: bool) -> list[str]:
    out = []
    if img["n_cells"] < 20 or (run["n_images"] > 1 and img["n_cells"] < 0.25 * run["median_cells"]):
        out.append("few_cells")
    if img["n_cells"] and img["n_valid"] / img["n_cells"] < 0.7:
        out.append("low_valid")
    ev = img["events"]
    if not ev["baseline_only"]:
        if ev["stimulation"] is None and run["n_images"] > 1 and run["with_stimulation"] > run["n_images"] / 2:
            out.append("no_stimulation")
        if ev["calibration"] is None and run["n_images"] > 1 and run["with_calibration"] > run["n_images"] / 2:
            out.append("no_calibration")
        if (ev["stimulation"] is not None and run["stimulation_mode"] is not None
                and abs(ev["stimulation"] - run["stimulation_mode"]) > 3):
            out.append("event_offset")
    if (ev["calibration"] is not None and img["cal_delta"] is not None and img["baseline_spread"] is not None
            and abs(img["cal_delta"]) < 2 * img["baseline_spread"]):
        out.append("no_cal_response")
    if screening:
        if not img["has_positions"]:
            out.append("no_positions")
        if img["n_hits"] == 0:
            out.append("no_hits")
    return out


def _level(flag: str, img: dict) -> str:
    if flag == "low_valid" and img["n_cells"] and img["n_valid"] / img["n_cells"] < 0.4:
        return "bad"
    return "info" if flag == "no_hits" else "warn"


def _hit_table(hits: pd.DataFrame | None, out: Path) -> dict[tuple[str, int], dict]:
    """(image, cell) -> {rank, chunk, visit} from the run's hit list and its .rgn chunks."""
    table: dict[tuple[str, int], dict] = {}
    if hits is None or not len(hits):
        return table
    for _, h in hits.iterrows():
        table[(str(h["image"]), int(h["cell"]))] = {"rank": int(h["rank"]), "chunk": None, "visit": None}
    chunks_file = out / "hit_chunks.json"
    if chunks_file.exists():
        for k, chunk in enumerate(json.loads(chunks_file.read_text())):
            for v, (image, cell) in enumerate(zip(chunk["image"], chunk["cell"], strict=True)):
                if (str(image), int(cell)) in table:
                    table[(str(image), int(cell))] |= {"chunk": k + 1, "visit": v + 1}
    return table


def build_overview_data(results: list[ImageResult], settings: Settings, out: Path, hits: pd.DataFrame | None = None,
                        thumbs: dict[str, str] | None = None, run: dict | None = None) -> dict:
    """Everything the Overview page shows. hits: the run's hit list (with rank); thumbs: image name -> thumbnail;
    run: run_info of the output folder (start time)."""
    from .dashboard import auto_range

    sc = settings.screening
    metric = response_metric(settings)
    hit_info = _hit_table(hits if sc.enabled else None, out)
    images = []
    for r in results:
        cells = r.cells
        hit = cells["hit"].astype(bool).to_numpy()
        valid = cells["valid"].astype(bool).to_numpy()
        ev = r.events
        dash = r.out_dir / "dashboard.html"
        tiles = r.tiles or []
        has_positions = (r.stage_known and bool(len(cells))
                         and bool(np.isfinite(pd.to_numeric(cells["abs_x_m"], errors="coerce")).any()))
        sub = _subsample(cells, seed=r.index)
        hit_rows = cells[hit]
        img = {
            "name": r.name, "index": r.index, "folder": r.out_dir.name,
            "href": f"{r.out_dir.name}/dashboard.html" if settings.display.dashboard and dash.exists() else None,
            "source": r.source, "n_cells": r.n_cells, "n_valid": int(valid.sum()), "n_hits": int(hit.sum()),
            "frames": r.shape[0], "frame_interval": r.frame_interval, "unit": r.unit,
            "events": ev.to_dict(),
            "baseline": _median(cells.loc[valid, "baseline_mean"]) if valid.any() else None,
            "response": _median(cells.loc[valid, metric]) if valid.any() and metric in cells else None,
            "hit_response": _median(hit_rows[metric]) if len(hit_rows) and metric in cells else None,
            "cal_delta": _median(cells.loc[valid, "calibration_diff"]) if valid.any() else None,
            "baseline_spread": _median(np.abs(pd.to_numeric(cells["baseline_dev_pop"], errors="coerce"))),
            "intensity": _median(cells["mean_intensity"]),
            "class_pos": float(np.nanmean(cells["class_additional"])) * 100 if "class_additional" in cells and len(cells) else None,
            "tiles": tiles, "n_tiles": len(tiles),
            "area_mm2": float(sum(t[2] * t[3] for t in tiles)) * 1e6 if tiles else None,
            "has_positions": has_positions,
            "bands": _bands(r.kymo_smoothed, valid if valid.any() else np.ones(r.n_cells, bool)),
            "bands_hits": _bands(r.kymo_smoothed, hit) if hit.any() else None,
            "cells": _cell_columns(sub), "n_shown": len(sub),
            "hits": [{"cell": int(h["cell"]), "x": float(h["abs_x_m"]) if pd.notna(h["abs_x_m"]) else None,
                      "y": float(h["abs_y_m"]) if pd.notna(h["abs_y_m"]) else None,
                      **hit_info.get((r.name, int(h["cell"])), {"rank": None, "chunk": None, "visit": None})}
                     for _, h in hit_rows.iterrows()],
            "thumb": (thumbs or {}).get(r.name),
        }
        images.append(img)
    stim = [i["events"]["stimulation"] for i in images if i["events"]["stimulation"] is not None]
    run_stats = {
        "n_images": len(images),
        "median_cells": float(np.median([i["n_cells"] for i in images])) if images else 0,
        "with_stimulation": len(stim),
        "with_calibration": sum(i["events"]["calibration"] is not None for i in images),
        "stimulation_mode": max(set(stim), key=stim.count) if stim else None,
    }
    for img in images:
        img["flags"] = [{"key": f, "level": _level(f, img), "text": QC[f]} for f in _flags(img, run_stats, sc.enabled)]
    # one y range for the response of all images, so that the axis does not jump when the selection changes
    d = settings.display
    lo, hi = auto_range(np.concatenate([r.kymo_smoothed.ravel() for r in results])) if results else (0.0, 1.0)
    lo = lo if d.min_lifetime is None else d.min_lifetime
    hi = hi if d.max_lifetime is None else d.max_lifetime
    chunks_file = out / "hit_chunks.json"
    files = sorted(p.name for p in out.iterdir() if p.is_file() and p.suffix.lower() in (".tsv", ".rgn", ".png", ".txt",
                                                                                             ".json", ".toml", ".tif"))
    return {
        "version": __version__, "title": out.name, "screening": sc.enabled,
        "unit": results[0].unit if results else "", "is_lifetime": bool(results) and results[0].unit.startswith("Lifetime"),
        "response_metric": metric,
        "criteria": [{"metric": c.metric, "op": c.op, "value": c.value, "value2": c.value2,
                      "logic": (c.logic or sc.logic).upper()} for c in sc.criteria],
        "max_hits_per_rgn": sc.max_hits_per_rgn, "optimize_path": sc.optimize_path,
        "metrics": METRICS, "qc": QC, "bands": list(BANDS), "max_cells": MAX_CELLS,
        "y_range": [lo, hi] if hi > lo else [lo, lo + 1],
        "started": (run or {}).get("started"), "reapplied": (run or {}).get("reapplied"),
        "chunks": json.loads(chunks_file.read_text()) if sc.enabled and chunks_file.exists() else [],
        "files": files,
        "images": images,
    }


def summary_table(data: dict) -> pd.DataFrame:
    """The images table of the Overview as a table (written as run_summary.tsv)."""
    rows = []
    for i in data["images"]:
        ev = i["events"]
        rows.append({
            "image": i["name"], "cells": i["n_cells"], "valid": i["n_valid"],
            "valid_pct": round(100 * i["n_valid"] / i["n_cells"], 2) if i["n_cells"] else math.nan,
            **({"hits": i["n_hits"], "hit_pct_of_valid": round(100 * i["n_hits"] / i["n_valid"], 3) if i["n_valid"] else math.nan}
               if data["screening"] else {}),
            "median_baseline": i["baseline"], f"median_{data['response_metric']}": i["response"],
            "median_calibration_diff": i["cal_delta"], "frames": i["frames"], "frame_interval_s": i["frame_interval"],
            "stimulation_frame": ev["stimulation"], "calibration_frame": ev["calibration"],
            "events_detected": ev["detected"], "baseline_only": ev["baseline_only"],
            "qc_flags": ",".join(f["key"] for f in i["flags"]), "source": i["source"],
        })
    return pd.DataFrame(rows)


OVERVIEW_JS = ["data.js", "table.js", "panels.js", "maps.js", "export.js", "main.js"]


def write_overview(results: list[ImageResult], settings: Settings, out: Path, hits: pd.DataFrame | None = None,
                   thumbs: dict[str, str] | None = None, run: dict | None = None) -> Path:
    """index.html (the interactive Overview) and run_summary.tsv (its images table) in the output folder."""
    from .dashboard import _bundle, _embed

    data = build_overview_data(results, settings, out, hits, thumbs, run)
    summary_table(data).to_csv(out / SUMMARY_FILE, sep="	", index=False, float_format="%.6g")
    data["files"] = sorted(set(data["files"]) | {SUMMARY_FILE})
    path = out / "index.html"
    path.write_text(_embed(_bundle("overview", ["style.css"], OVERVIEW_JS), data), encoding="utf-8")
    return path
