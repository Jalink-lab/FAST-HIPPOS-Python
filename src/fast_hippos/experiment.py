"""A screen of several samples: one run (output folder) per sample, all inside one experiment folder.

The experiment folder gets its own overview (index.html, with experiment_summary.tsv): the images of all its samples
in one table, with the same plots as the overview of a run, and a warning when the samples were not all analyzed with
the same settings. It is made from the overviews of the runs (their index.html holds all the data it needs), and
updated after every run and re-apply of a sample in the folder (pipeline.run).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pandas as pd

from . import __version__
from .overview import QC, _flags, _level, summary_table

log = logging.getLogger(__name__)

SUMMARY_FILE = "experiment_summary.tsv"
LOG_FILE = "experiment_log.txt"  # of the last "Re-apply all samples"

# settings that make no difference to how comparable the samples are (paths, output, display, .rgn files, ...)
NOT_COMPARED = {
    "input": {"files", "output", "experiment", "sample_label", "series"},
    "segmentation": {"cellpose3_python", "cellpose4_python", "use_gpu"},
    "screening": {"stage_positions_file", "n_tiles", "tile_overlap", "max_hits_per_rgn", "optimize_path",
                  "max_optimization_time", "random_seed", "rgn_swap_xy", "rgn_invert_x", "rgn_invert_y",
                  "sort_by", "sort_descending", "manual_hits"},
}
COMPARED_DISPLAY = {"smooth_traces"}  # of [display], only this changes the analysis
SKIPPED_SECTIONS = {"image"}  # own settings of single images are deliberate differences


def is_run_folder(folder: Path) -> bool:
    return (folder / "run.json").is_file() and (folder / "index.html").is_file() and (folder / "settings_used.json").is_file()


def run_folders(experiment: Path) -> list[Path]:
    """The output folders (runs) of the samples: the subfolders with a run in them, by name."""
    experiment = Path(experiment)
    if not experiment.is_dir():
        return []
    return sorted((d for d in experiment.iterdir() if d.is_dir() and not d.name.startswith("_") and is_run_folder(d)),
                  key=lambda d: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", d.name.lower())])


def in_experiment(out: Path, experiment: Path | None) -> bool:
    """Whether an output folder is a sample of the experiment (a folder directly inside it)."""
    if not experiment:
        return False
    try:
        return Path(out).resolve().parent == Path(experiment).resolve()
    except OSError:
        return False


def read_overview_data(index_html: Path) -> dict:
    """The data embedded in an overview page (written by overview.write_overview)."""
    page = Path(index_html).read_text(encoding="utf-8")
    m = re.search(r'<script id="fh-data" type="application/json">(.*?)</script>', page, re.DOTALL)
    if not m:
        raise ValueError(f"{index_html}: no overview data")
    return json.loads(m.group(1).replace("<\\/", "</"))


def comparable_settings(settings: dict) -> dict[str, object]:
    """The settings of a run that matter for comparing samples, as {'section.key': value}."""
    out = {}
    for section, values in settings.items():
        if section in SKIPPED_SECTIONS or not isinstance(values, dict):
            continue
        for key, value in values.items():
            if section == "display" and key not in COMPARED_DISPLAY:
                continue
            if key in NOT_COMPARED.get(section, set()):
                continue
            out[f"{section}.{key}"] = value
    return out


def settings_differences(by_run: dict[str, dict]) -> list[dict]:
    """The settings that differ between runs: [{'setting', 'values': {run: value}}], in the order of the settings."""
    flat = {run: comparable_settings(s) for run, s in by_run.items()}
    keys = list(dict.fromkeys(k for f in flat.values() for k in f))
    diffs = []
    for key in keys:
        values = {run: f.get(key) for run, f in flat.items()}
        if len({json.dumps(v, sort_keys=True, default=str) for v in values.values()}) > 1:
            diffs.append({"setting": key, "values": values})
    return diffs


def _short(value) -> str:
    if value is None:
        return "empty"
    if isinstance(value, list) and value and isinstance(value[0], dict):  # criteria
        return "; ".join(f"{c.get('logic') or ''} {c.get('metric')} {c.get('op')} {c.get('value')}"
                         + (f"–{c.get('value2')}" if c.get("op") == "between" else "") for c in value).strip()
    return json.dumps(value, default=str) if not isinstance(value, str) else value


def _label(key: str) -> str:
    """The name of a setting in the window ('Hit criteria'), or its key."""
    try:
        from .gui import FIELDS

        return FIELDS.get(key, {}).get("label") or key
    except Exception:  # noqa: BLE001 - only a nicer name
        return key


def describe_differences(diffs: list[dict], max_runs: int = 6) -> list[str]:
    """One readable line per differing setting: 'Hit criteria (screening.criteria) — A: …; B, C: …'."""
    lines = []
    for d in diffs:
        groups: dict[str, list[str]] = {}
        for run, v in d["values"].items():
            groups.setdefault(_short(v), []).append(run)
        parts = []
        for v, runs in groups.items():
            names = ", ".join(runs[:max_runs]) + (f" and {len(runs) - max_runs} more" if len(runs) > max_runs else "")
            parts.append(f"{names}: {v}")
        name = _label(d["setting"])
        lines.append((f"{name} ({d['setting']})" if name != d["setting"] else name) + " — " + " · ".join(parts))
    return lines


def build_experiment_data(experiment: Path, failed: list[str] | None = None) -> dict:
    """The overview data of all samples of an experiment folder (the images of all runs, with their sample)."""
    experiment = Path(experiment)
    runs = run_folders(experiment)
    images, settings_by_run, notes, run_list = [], {}, [], []
    first: dict | None = None
    names = set()
    y_lo, y_hi = [], []
    for folder in runs:
        try:
            data = read_overview_data(folder / "index.html")
            settings = json.loads((folder / "settings_used.json").read_text())
        except (OSError, ValueError) as e:
            notes.append(f"{folder.name} is left out: its overview cannot be read ({e})")
            continue
        first = first or data
        settings_by_run[folder.name] = settings
        label = (settings.get("input") or {}).get("sample_label") or ""
        run_list.append({"name": folder.name, "href": f"{folder.name}/index.html", "label": label,
                         "started": data.get("started"), "reapplied": data.get("reapplied"), "n_images": len(data["images"])})
        y_lo.append(data["y_range"][0]); y_hi.append(data["y_range"][1])
        for im in data["images"]:
            im = dict(im)
            im["image"] = im["name"]  # its own name (the tables); "name" is unique in the page
            # in the window every image has a folder of its own, named as the image (or renamed): that name
            im["name"] = folder.name if len(data["images"]) == 1 else f"{folder.name}: {im['name']}"
            im["screened"] = bool(data.get("screening"))  # hits only for images that were screened
            names.add(im["name"])
            im["sample"], im["label"] = folder.name, label
            im["run_started"] = data.get("started")
            if im.get("href"):
                im["href"] = f"{folder.name}/{im['href']}"
            images.append(im)
    for k, im in enumerate(images):
        im["index"] = k
    # QC flags compared with all samples of the experiment
    stim = [i["events"]["stimulation"] for i in images if i["events"]["stimulation"] is not None]
    stats = {"n_images": len(images),
             "median_cells": float(pd.Series([i["n_cells"] for i in images]).median()) if images else 0,
             "with_stimulation": len(stim),
             "with_calibration": sum(i["events"]["calibration"] is not None for i in images),
             "stimulation_mode": max(set(stim), key=stim.count) if stim else None}
    screening = any(im["screened"] for im in images)
    for im in images:
        im["flags"] = [{"key": f, "level": _level(f, im), "text": QC[f]} for f in _flags(im, stats, screening)]
    diffs = settings_differences(settings_by_run)
    if diffs:
        from .pipeline import REAPPLY_SECTIONS

        fixable = any(d["setting"].split(".")[0] in REAPPLY_SECTIONS for d in diffs)
        fixed_only = any(d["setting"].split(".")[0] not in REAPPLY_SECTIONS for d in diffs)
        notes.insert(0, "The images were not all analyzed with the same settings, so their results are not fully "
                        "comparable: " + " | ".join(describe_differences(diffs)) + "."
                        + (" 'Re-apply all images' in the FAST-HIPPOS window makes the stimulation, screening and "
                           "display settings the same." if fixable else "")
                        + (" Other settings (segmentation, traces, image type, …) only change by analyzing those images "
                           "again." if fixed_only else ""))
    if failed:
        notes.insert(0, f"Not re-applied (the last 'Re-apply all images' failed for them; they keep their earlier "
                        f"results): {', '.join(failed)}. See experiment_log.txt.")
    units = {i.get("unit") for i in images if i.get("unit")}
    if len(units) > 1:
        notes.append("The images hold different kinds of values: " + ", ".join(sorted(units)))
    base = first or {}
    return {
        "version": __version__, "kind": "experiment", "title": experiment.name, "screening": screening,
        "unit": base.get("unit", ""), "is_lifetime": base.get("is_lifetime", False),
        "response_metric": base.get("response_metric", "response_max_diff"), "criteria": base.get("criteria", []),
        "max_hits_per_rgn": base.get("max_hits_per_rgn", 1000), "optimize_path": base.get("optimize_path", True),
        "metrics": base.get("metrics", {}), "qc": QC, "bands": base.get("bands", []), "max_cells": base.get("max_cells"),
        "y_range": [min(y_lo), max(y_hi)] if y_lo else [0, 1],
        "started": min((r["started"] for r in run_list if r["started"]), default=None), "reapplied": None,
        "chunks": [], "files": ([SUMMARY_FILE] if images else []) + [f for f in [LOG_FILE] if (experiment / f).exists()],
        "runs": run_list, "notes": notes,
        "differences": diffs, "images": images,
    }


def write_experiment_overview(experiment: Path, failed: list[str] | None = None) -> Path | None:
    """index.html (the overview of all samples) and experiment_summary.tsv in the experiment folder; None when the
    folder holds no runs yet. failed: samples whose re-apply failed (noted on the page)."""
    from .dashboard import _bundle, _embed
    from .overview import OVERVIEW_JS

    experiment = Path(experiment)
    if not run_folders(experiment):
        return None
    data = build_experiment_data(experiment, failed)
    for note in data["notes"]:
        if "is left out" in note:
            log.warning(note)
    table = summary_table(data)
    if len(table):
        table["image"] = [im["image"] for im in data["images"]]
    table.insert(0, "label", [im["label"] for im in data["images"]] if len(table) else [])
    table.insert(0, "sample", [im["sample"] for im in data["images"]] if len(table) else [])
    table.to_csv(experiment / SUMMARY_FILE, sep="\t", index=False, float_format="%.6g")
    path = experiment / "index.html"
    path.write_text(_embed(_bundle("overview", ["style.css"], OVERVIEW_JS), data), encoding="utf-8")
    log.info("Experiment overview: %s (%d images)%s", path, len(data["images"]),
             "; the images were analyzed with different settings" if data["differences"] else "")
    return path
