"""End-to-end processing: per image (segment, measure, analyze, save, dashboard) and per run (screening output)."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__, events, kymograph, modalities, plots, preprocess, screening, segmentation, stage
from .config import Modality, Settings
from .io import ImageData, iter_images, safe_name, write_tiff
from .viewer_data import ViewerData, prepare

log = logging.getLogger("fast_hippos")

BASE_COLUMNS = [
    "image", "tile", "cell", "area_px", "mean_intensity", "circularity", "centroid_x", "centroid_y",
    "pos_x_px", "pos_y_px", "abs_x_m", "abs_y_m",
]


@dataclass
class ImageResult:
    name: str
    out_dir: Path
    index: int
    pixel_size: float
    frame_interval: float
    shape: tuple[int, int, int]  # (T, Y, X)
    unit: str
    kymo: np.ndarray
    kymo_smoothed: np.ndarray
    additional: np.ndarray | None
    base: pd.DataFrame  # BASE_COLUMNS
    stage_xy: tuple[float, float] | None = None
    tile_size: tuple[float, float] | None = None
    tiles: list[tuple[float, float, float, float]] = field(default_factory=list)  # (x0, y0, w, h) in abs frame (m)
    stage_info_block: str | None = None
    events: events.Events | None = None
    order: np.ndarray | None = None
    cells: pd.DataFrame | None = None
    classification_threshold: float | None = None
    source: str = ""  # the input file (or tile folder) the image came from
    stage_known: bool = True  # False: no stage position was found and (0, 0) stands in for it

    @property
    def n_cells(self) -> int:
        return self.kymo.shape[1]

    @property
    def hit_kymo(self) -> np.ndarray:
        return self.kymo_smoothed


# ---------------------------------------------------------------- run


def run(settings: Settings, reapply: bool = False) -> list[ImageResult]:
    """Analyze the images (one output folder holds one run: a new run first removes the results of the previous one),
    or, with reapply, redo the analysis after segmentation for the images of the run in the output folder. For a
    reapply, `settings` are those of that run with other event / screening / display settings (reapply_settings)."""
    out = Path(settings.input.output)
    out.mkdir(parents=True, exist_ok=True)
    _close_logging()  # the log of an earlier run in this process is moved along with that run
    info = run_info(out) if reapply else None
    if reapply and not info:
        raise ValueError(f"No analysis results in {out}: run the analysis first")
    if not reapply:  # stop now, not after minutes of work, if the settings do not fit the images
        from .checks import SettingsError, check_inputs

        problems = check_inputs(settings)
        if not problems:
            try:
                moved = clear_run(out, input_paths(settings))
            except ValueError as e:
                problems = str(e).splitlines()
        if problems:
            _setup_logging(out / "run_log.txt")
            for p in problems:
                log.error(p)
            raise SettingsError(problems)
        _start_run_file(out, settings)
    _setup_logging(out / "run_log.txt")
    log.info("FAST-HIPPOS (Python) %s%s", __version__, " - re-applying the analysis after segmentation" if reapply else "")
    if not reapply and moved:
        log.info("The results of the previous run in this folder were moved to %s%s (removed when this run is complete, "
                 "kept if it is not): %s", PREVIOUS_RUN, os.sep, ", ".join(moved))
    (out / "settings_used.json").write_text(json.dumps(settings.to_dict(), indent=2))

    results: list[ImageResult] = []
    if reapply:
        log.info("Re-applying stimulation detection, screening and dashboards to the %d image(s) of the run of %s "
                 "in this folder (segmentation and traces are kept): %s", len(info["images"]), info.get("started", "?"),
                 ", ".join(i["name"] for i in info["images"]))
        for meta in (d / "meta.json" for d, _ in _result_folders(out)):
            result = load_result(meta.parent)
            analyze(result, settings)
            save_tables(result, settings)
            results.append(result)
        results.sort(key=lambda r: r.index)
    else:
        positions_all = None
        positions_file = settings.screening.stage_positions_file
        if settings.screening.enabled and positions_file:
            positions_all = stage.read_positions_file(Path(positions_file))
        # a text file overrides the positions in the images; a .lif only fills in where an image has none
        override = positions_file is not None and Path(positions_file).suffix.lower() != ".lif"
        p = settings.preprocess
        bidirectional = p.bidirectional_axis if p.correct_bidirectional else None
        index = 0
        for path in settings.input.files:
            if Path(path).is_dir():
                images = [_stitch(Path(path), settings, out)]
            else:
                images = iter_images(Path(path), settings.input.series, bidirectional, _reg_channels(settings))
            for image in images:
                log.info("--- %s", image.name)
                if image.extra.get("tiles") and not Path(path).is_dir():  # a tile scan in a .lif, stitched
                    image.extra["stitched_file"] = _save_stitched(image, out)
                if "stitched_file" in image.extra:
                    _record_file(out, image.extra["stitched_file"])
                result = process_image(image, index, settings, positions_all, override)
                if result is not None:
                    results.append(result)
                index += 1
    if not results:
        log.warning("No images with cells were analyzed%s", "" if reapply else
                    f"; the previous run (if any) is kept in {PREVIOUS_RUN}{os.sep}")
        return results
    hits = write_screening_outputs(results, settings, out) if settings.screening.enabled else None
    # dashboards last, so that they can show the route of the .rgn files
    routes = _routes(results, out) if settings.screening.enabled else {}
    from .overview import thumbnail, write_overview

    thumbs = {}
    for result in results:
        viewer = ViewerData.load(result.out_dir / "viewer.npz")
        _write_dashboard(result, viewer, settings, routes.get(result.name))
        thumbs[result.name] = thumbnail(viewer.projection8)
    started = info["started"] if reapply else _read_run_file(out).get("started")
    write_overview(results, settings, out, hits, thumbs, {"started": started,
                                                          "reapplied": time.strftime("%Y-%m-%d %H:%M") if reapply else None})
    _write_run_file(out, results, reapply, info["started"] if reapply else None)
    log.info("Done. Output in %s", out)
    return results


# ---------------------------------------------------------------- the run in an output folder

RUN_FILE = "run.json"  # the images of the run in an output folder, its input files and the files it wrote next to them
PREVIOUS_RUN = "_previous_run"  # where the last complete run waits while a new run is running (removed when it is done)
REAPPLY_SECTIONS = ("events", "screening", "display")  # what a re-apply may change
# settings in those sections that only take effect in a full run (overlay, dashboard image, stage positions): a re-apply
# keeps the values of the run, so that the record of the run stays true
RUN_TIME_ONLY = {"display": ("overlay_smooth_xy", "overlay_smooth_t", "dashboard_max_size", "dashboard_max_megapixels",
                             "dashboard_tiles"), "screening": ("stage_positions_file",)}
# files that a run writes in the output folder itself (they go with the run)
_RUN_OUTPUTS = re.compile(r"(index\.html|cell_coordinates\.tsv|hits\.tsv|hits_\d+-\d+\.tsv|HITS_.*\.rgn|hit_positions\.png|"
                          r"hit_chunks\.json|screening_from_dashboard\.toml|settings_used\.json|run\.json|run_log\.txt|run_summary\.tsv)")
_QUIET = ("settings_used.json", "run.json", "run_log.txt")  # moved along, but not worth listing to the user


def _result_folders(out: Path) -> list[tuple[Path, dict]]:
    """The image result folders in an output folder, with their meta.json: only folders that FAST-HIPPOS wrote
    (meta.json with a name and a version, and the traces next to it); anything else in the folder is never touched."""
    found = []
    for meta_path in sorted(Path(out).glob("*/meta.json")):
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict) and "name" in meta and "version" in meta and (meta_path.parent / "traces.npz").exists():
            found.append((meta_path.parent, meta))
    return found


def _read_run_file(out: Path) -> dict:
    try:
        info = json.loads((Path(out) / RUN_FILE).read_text(encoding="utf-8"))
        return info if isinstance(info, dict) else {}
    except (OSError, ValueError):
        return {}


def run_info(out: Path) -> dict | None:
    """The run in an output folder: {"started", "reapplied", "version", "complete", "inputs", "files", "images":
    [{"name", "folder", "source", "cells", "index"}], "previous_run"}; None if the folder holds no results. The images
    are read from the image folders themselves."""
    out = Path(out)
    folders = _result_folders(out)
    if not folders:
        return None
    images = sorted(({"name": m["name"], "folder": d.name, "source": m.get("source", ""), "cells": m.get("n_cells"),
                      "index": m.get("index", 0)} for d, m in folders), key=lambda i: i["index"])
    info = _read_run_file(out)
    if "started" not in info:  # results of an earlier version: when the first image result was written
        first = min((d / "meta.json").stat().st_mtime for d, _ in folders)
        info["started"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(first))
    return info | {"images": images, "previous_run": (out / PREVIOUS_RUN).is_dir()}


def input_paths(settings: Settings) -> list[Path]:
    """Every file or folder that a run reads."""
    s_in, seg, sc, fd = settings.input, settings.segmentation, settings.screening, settings.fdflim
    paths = list(s_in.files) + [seg.labelmap, seg.classifier, sc.stage_positions_file, sc.manual_hits, fd.reference,
                                fd.background]
    return [Path(p).resolve() for p in paths if p]


def clear_plan(out: Path, keep: list[Path] = ()) -> dict:
    """What a new run in this output folder would move away: {"folders": image result folders, "files": files of the
    run next to them, "blocked": reasons why it cannot (a file the new run reads lies inside a result folder)}. Files in
    `keep` (the inputs of the new run) are never moved."""
    out = Path(out).resolve()
    keep = [Path(k).resolve() for k in keep]
    folders = [d for d, _ in _result_folders(out)]
    blocked = [f"{k} is inside {d.name}{os.sep}, a result of the previous run that a new run moves away: move it out of "
               "the output folder first, or choose another output folder" for d in folders for k in keep if k.is_relative_to(d)]
    files = {out / n for n in _read_run_file(out).get("files", []) if (out / n).is_file() and (out / n).parent == out}
    files |= {p for p in out.iterdir() if p.is_file() and _RUN_OUTPUTS.fullmatch(p.name)} if out.is_dir() else set()
    files = sorted(p for p in files if p not in keep)
    return {"folders": [d.name for d in folders], "files": [p.name for p in files], "blocked": blocked}


def clear_run(out: Path, keep: list[Path] = ()) -> list[str]:
    """Before a new run: move the results of the previous run to PREVIOUS_RUN (they are removed once the new run is
    complete; if it is not, they stay there). If PREVIOUS_RUN already exists, an earlier attempt did not finish: its
    partial results are removed and the complete run in PREVIOUS_RUN is kept. Raises ValueError when a file that the
    new run reads would be moved. Returns the names of what was moved (or removed)."""
    out = Path(out)
    plan = clear_plan(out, keep)
    if plan["blocked"]:
        raise ValueError("\n".join(plan["blocked"]))
    prev = out / PREVIOUS_RUN
    if prev.is_dir() and _read_run_file(out).get("complete", True):
        shutil.rmtree(prev)  # left over from a complete run (its removal failed): the folder holds the newer run
    partial = prev.is_dir()
    prev.mkdir(exist_ok=True)
    for name in plan["folders"] + plan["files"]:
        src = out / name
        if partial:
            shutil.rmtree(src) if src.is_dir() else src.unlink()
        else:
            shutil.move(str(src), str(prev / name))
    return [n + "/" for n in plan["folders"]] + [n for n in plan["files"] if n not in _QUIET]


def _start_run_file(out: Path, settings: Settings) -> None:
    """run.json at the start of a run: not complete yet, and every file the run writes next to the image folders is
    added as soon as it exists (so that a run that does not finish leaves no unknown files)."""
    info = {"version": __version__, "started": time.strftime("%Y-%m-%d %H:%M"), "complete": False,
            "inputs": [str(f) for f in settings.input.files], "files": [], "images": []}
    (Path(out) / RUN_FILE).write_text(json.dumps(info, indent=2), encoding="utf-8")


def _record_file(out: Path, name: str) -> None:
    info = _read_run_file(out)
    info["files"] = sorted(set(info.get("files", [])) | {name})
    (Path(out) / RUN_FILE).write_text(json.dumps(info, indent=2), encoding="utf-8")


def _write_run_file(out: Path, results: list[ImageResult], reapply: bool, started: str | None = None) -> None:
    """run.json when a run (or re-apply) is complete; the previous run is then removed."""
    now = time.strftime("%Y-%m-%d %H:%M")
    info = _read_run_file(out)
    info |= {"version": __version__, "started": started or info.get("started", now), "complete": True,
             "images": [{"name": r.name, "folder": r.out_dir.name, "source": r.source, "cells": r.n_cells,
                         "index": r.index} for r in results]}
    if reapply:
        info["reapplied"] = now
    (Path(out) / RUN_FILE).write_text(json.dumps(info, indent=2), encoding="utf-8")
    shutil.rmtree(Path(out) / PREVIOUS_RUN, ignore_errors=True)


def reapply_settings(out: Path, changes: dict) -> dict:
    """Settings for re-applying the analysis in an output folder: those of the run in it (settings_used.json), with
    the event, screening and display settings taken from `changes`, key by key (the images, segmentation and traces
    stay those of the run, and so do the RUN_TIME_ONLY settings, which a re-apply cannot change)."""
    out = Path(out)
    used = out / "settings_used.json"
    if not used.exists() or not run_info(out):
        raise ValueError(f"No analysis results in {out}: run the analysis first")
    base = json.loads(used.read_text())
    for section in REAPPLY_SECTIONS:
        if isinstance(changes.get(section), dict):
            kept = {k: base.get(section, {})[k] for k in RUN_TIME_ONLY.get(section, ()) if k in base.get(section, {})}
            base[section] = base.get(section, {}) | changes[section] | kept
    base["input"]["output"] = str(out)
    return base


def _reg_channels(settings: Settings) -> list[int]:
    """1-based channels used for the bidirectional and drift correction."""
    c = settings.input.intensity_channel
    return [c, c + 1] if settings.input.modality in (Modality.TCSPC, Modality.RATIO) else [c]


def _stitch(folder: Path, settings: Settings, out: Path) -> ImageData:
    """Stitch a folder of tiles (bidirectional correction per tile, if on) and save the result in the output folder,
    where Fiji or a next run can use it as an ordinary stitched image."""
    from .stitch import stitch_folder

    p, sc = settings.preprocess, settings.screening
    lif = sc.stage_positions_file if sc.stage_positions_file and Path(sc.stage_positions_file).suffix.lower() == ".lif" else None
    image = stitch_folder(folder, lif, settings.input.pixel_size, p.bidirectional_axis if p.correct_bidirectional else None,
                          _reg_channels(settings))
    image.extra["stitched_file"] = _save_stitched(image, out)
    return image


def _save_stitched(image: ImageData, out: Path) -> str:
    path = out / f"{_safe(image.name)}{'' if image.name.endswith('_STITCHED') else '_STITCHED'}.tif"
    write_tiff(path, image.data, "TCYX", image.pixel_size, image.frame_interval, image.info)
    log.info("Stitched image saved: %s", path)
    return path.name


def _close_logging() -> None:
    logger = logging.getLogger("fast_hippos")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()


def _setup_logging(path: Path) -> None:
    logger = logging.getLogger("fast_hippos")
    logger.setLevel(logging.INFO)
    _close_logging()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    for handler in (logging.FileHandler(path, mode="w", encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(fmt)
        logger.addHandler(handler)


# ---------------------------------------------------------------- per image


def process_image(
    image: ImageData, index: int, settings: Settings, positions_all: np.ndarray | None = None, override: bool = True
) -> ImageResult | None:
    s_in, s_seg, s_disp = settings.input, settings.segmentation, settings.display
    if s_in.remove_last_frame and image.n_frames > 1:
        image.data = image.data[:-1]
    reg_channels = _reg_channels(settings)
    stitched = stage.parse_stitched_info(image.info)
    if stitched is not None and stitched.bidirectional is not None:
        log.info("Bidirectional phase correction: done per tile when stitching (%.2f px)", stitched.bidirectional)
    elif settings.preprocess.correct_bidirectional:
        image.data, _ = preprocess.correct_bidirectional(image.data, reg_channels, settings.preprocess.bidirectional_axis)
    if settings.preprocess.correct_drift and image.n_frames > 1:
        p = settings.preprocess
        image.data, _ = preprocess.correct_drift(image.data, reg_channels, p.drift_reference, p.drift_edge_detect, p.drift_blur_sigma)

    intensity, lifetime = modalities.compute(image, s_in, settings.fdflim)
    n_frames, height, width = intensity.shape
    pixel_size = s_in.pixel_size or image.pixel_size
    if not pixel_size:
        log.warning("Pixel size unknown; using 1 µm (set input.pixel_size)")
        pixel_size = 1.0
    frame_interval = image.frame_interval or s_in.default_frame_interval
    if not image.frame_interval:
        log.warning("Frame interval not found; using %.3g s", frame_interval)

    # segmentation
    proj = segmentation.projection(intensity, s_seg.start_frame, s_seg.end_frame)
    seg_img = proj if s_seg.channel is None else segmentation.projection(image.channel(s_seg.channel), s_seg.start_frame, s_seg.end_frame)
    labels = segmentation.segment(seg_img, s_seg)
    labels = segmentation.filter_labels(labels, proj, s_seg.min_cell_size, s_seg.max_circularity, s_seg.min_cell_intensity)
    n = int(labels.max())
    log.info("%d cells", n)
    if n == 0:
        log.warning("No cells found in %s - skipped", image.name)
        return None
    stats = segmentation.cell_statistics(labels, proj)

    # traces
    kymo = kymograph.cell_values(intensity, lifetime, labels, s_in.modality)
    kymo_s = kymograph.smooth_time(kymo, s_disp.smooth_traces)
    additional = None
    if s_in.additional_channel:
        additional = kymograph.mean_intensity(image.channel(s_in.additional_channel), labels)

    # positions
    centroids = stats[["centroid_x", "centroid_y"]].to_numpy()
    positions = centroids
    if s_seg.classifier:
        from .pixel_classifier import predict_probability

        prob = predict_probability(proj, Path(s_seg.classifier), s_seg.classifier_class)
        positions = stage.refined_positions(labels, prob, centroids, s_seg.position_erosion)

    out_dir = Path(s_in.output) / _safe(image.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = ImageResult(
        name=image.name, out_dir=out_dir, index=index, pixel_size=pixel_size, frame_interval=frame_interval,
        shape=(n_frames, height, width), unit=modalities.UNITS[s_in.modality], kymo=kymo, kymo_smoothed=kymo_s,
        additional=additional, base=pd.DataFrame(),
        source=str(image.source) + (f" (series {image.extra['series']})" if "series" in image.extra else ""),
    )
    _stage_geometry(result, image, positions_all, settings, override)
    base = pd.DataFrame({
        "image": image.name, "tile": index, "cell": stats["label"].to_numpy(),
        "area_px": stats["area_px"].to_numpy(), "mean_intensity": stats["mean_intensity"].to_numpy(),
        "circularity": stats["circularity"].to_numpy(),
        "centroid_x": centroids[:, 0], "centroid_y": centroids[:, 1],
        "pos_x_px": positions[:, 0], "pos_y_px": positions[:, 1],
        **{c: stats[c].to_numpy() for c in ("bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1")},
    })
    if result.stage_xy is not None:
        absolute = stage.absolute_positions(positions, np.asarray(result.stage_xy), result.tile_size, pixel_size)
        base["abs_x_m"], base["abs_y_m"] = absolute[:, 0], absolute[:, 1]
    else:
        base["abs_x_m"] = base["abs_y_m"] = np.nan
    result.base = base

    analyze(result, settings)
    save_image_outputs(result, labels, proj, lifetime, settings)
    from .dashboard import display_range

    tiles_dir = out_dir / "tiles"
    if tiles_dir.exists():
        shutil.rmtree(tiles_dir)
    big = max(height, width) > s_disp.dashboard_max_size
    viewer = prepare(
        intensity, lifetime, proj, labels, display_range(result, settings),
        s_disp.overlay_smooth_xy, s_disp.overlay_smooth_t, s_disp.dashboard_max_size, s_disp.dashboard_max_megapixels,
        tiles_dir if (big and s_disp.dashboard and s_disp.dashboard_tiles) else None,
    )
    viewer.save(out_dir / "viewer.npz")  # the dashboard is written at the end of the run
    return result


_safe = safe_name


def _stage_geometry(result: ImageResult, image: ImageData, positions_all: np.ndarray | None, settings: Settings,
                    override: bool = True):
    """Stage position of the image origin, tile size and tile outlines (only needed for screening)."""
    if not settings.screening.enabled:
        return
    _, height, width = result.shape
    px = result.pixel_size
    info = stage.parse_stitched_info(image.info)
    if info is not None and len(info.positions):
        n_tiles = info.n_tiles
        overlap = info.overlap
        tile_size = info.tile_size or stage.tile_size_from_image(width, height, px, n_tiles, overlap)
        positions = info.positions
        origin_xy = info.origin_xy
        log.info("Stitched image: %d x %d tiles, overlap %.1f %%", n_tiles[0], n_tiles[1], overlap * 100)
        result.stage_info_block = stage.stitched_info_block(stage.StageInfo(positions, n_tiles, tile_size, overlap,
                                                                            info.origin, info.bidirectional))
    else:
        # one image = one tile (fixes the macro dividing a single tile by the number of tiles, issue I16)
        tile_size = (width * px * 1e-6, height * px * 1e-6)
        if positions_all is not None and (override or image.stage_position is None):
            if result.index >= len(positions_all):
                raise ValueError(f"Stage positions file has {len(positions_all)} positions; image {result.index} has none")
            position = positions_all[result.index]
        elif image.stage_position is not None:
            position = image.stage_position
        else:
            log.warning("No stage position for %s: using (0, 0)", image.name)
            position = (0.0, 0.0)
            result.stage_known = False
        positions = np.array([position], dtype=float)
        origin_xy = tuple(positions[0])
    result.stage_xy = tuple(float(v) for v in origin_xy)
    result.tile_size = tuple(tile_size)
    w, h = tile_size
    result.tiles = [(-p[1] - w / 2, -p[0] - h / 2, w, h) for p in positions]


def analyze(result: ImageResult, settings: Settings) -> None:
    """Events, sorting, metrics, classification and hits (cheap; re-run by `reapply`)."""
    sc = settings.screening
    result.kymo_smoothed = kymograph.smooth_time(result.kymo, settings.display.smooth_traces)
    ev = events.determine(kymograph.population_mean(result.kymo), settings.events, result.kymo)
    result.events = ev
    result.order = events.response_order(result.kymo, ev)
    metrics = screening.compute_metrics(result.hit_kymo, ev, sc, result.additional)
    cells = pd.concat([result.base.reset_index(drop=True), metrics.drop(columns="cell")], axis=1)
    if result.additional is not None and sc.classify_additional_channel:
        cells["class_additional"], result.classification_threshold = screening.classify_additional(
            cells["additional_intensity"], sc.classification_threshold
        )
    has_cal = ev.calibration_window.stop > ev.calibration_window.start
    if sc.enabled and sc.manual_hits:
        cells["valid"] = screening.validity(cells, sc, has_cal)
        cells["hit"] = screening.manual_hits(Path(sc.manual_hits), result.name, cells["cell"])
    elif sc.enabled:
        cells = screening.find_hits(cells, sc, has_cal)
    else:
        cells["valid"] = screening.validity(cells, sc, has_cal)
        cells["hit"] = False
    rank = np.empty(result.n_cells, dtype=int)
    rank[result.order] = np.arange(result.n_cells)
    cells["response_rank"] = rank
    result.cells = cells


# ---------------------------------------------------------------- saving / loading


def save_image_outputs(result: ImageResult, labels, projection, lifetime, settings: Settings) -> None:
    d, px, fi = result.out_dir, result.pixel_size, result.frame_interval
    write_tiff(d / "labels.tif", labels.astype(np.uint16 if labels.max() < 65536 else np.float32), "YX", px, info=result.stage_info_block)
    write_tiff(d / "intensity_projection.tif", projection, "YX", px)
    write_tiff(d / "weighted_lifetime.tif", np.nan_to_num(lifetime), "TYX", px, fi)
    write_tiff(d / "kymograph.tif", result.kymo, "YX")
    write_tiff(d / "kymograph_smoothed.tif", result.kymo_smoothed, "YX")
    if result.additional is not None:
        write_tiff(d / "kymograph_additional.tif", result.additional, "YX")
    arrays = {"kymo": result.kymo} | ({"additional": result.additional} if result.additional is not None else {})
    np.savez_compressed(d / "traces.npz", **arrays)
    meta = {
        "name": result.name, "index": result.index, "pixel_size_um": px, "frame_interval_s": fi,
        "shape": list(result.shape), "n_cells": result.n_cells, "unit": result.unit,
        "stage_xy_m": result.stage_xy, "tile_size_m": result.tile_size, "tiles": result.tiles,
        "stage_info_block": result.stage_info_block, "version": __version__, "source": result.source,
        "stage_known": result.stage_known,
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=2))
    result.base.to_csv(d / "cells_base.tsv", sep="\t", index=False)
    save_tables(result, settings)


def save_tables(result: ImageResult, settings: Settings) -> None:
    d = result.out_dir
    write_tiff(d / "kymograph_sorted.tif", result.kymo[:, result.order], "YX")
    result.cells.to_csv(d / "cells.tsv", sep="\t", index=False, float_format="%.6g")
    (d / "events.json").write_text(json.dumps(result.events.to_dict(), indent=2))
    if settings.display.save_tables:
        time = np.arange(result.kymo.shape[0]) * result.frame_interval
        cols = [f"cell_{i:05d}" for i in range(1, result.n_cells + 1)]
        table = pd.DataFrame(result.kymo, columns=cols)
        table.insert(0, "time_s", time)
        table.to_csv(d / "lifetime_traces.tsv", sep="\t", index=False, float_format="%.6g")
        if result.additional is not None:
            add = pd.DataFrame(result.additional, columns=cols)
            add.insert(0, "time_s", time)
            add.to_csv(d / "additional_traces.tsv", sep="\t", index=False, float_format="%.6g")
    if settings.display.save_png_plots:
        from .dashboard import display_range

        ylim = None if settings.input.modality == Modality.INTENSITY else display_range(result, settings)
        hits = result.cells["hit"].to_numpy() if settings.screening.enabled else None
        plots.traces(d / "traces.png", result.kymo_smoothed, result.frame_interval, result.events, result.unit, ylim, hits, result.name)


def load_result(d: Path) -> ImageResult:
    meta = json.loads((d / "meta.json").read_text())
    with np.load(d / "traces.npz") as z:
        kymo = z["kymo"]
        additional = z["additional"] if "additional" in z.files else None
    return ImageResult(
        name=meta["name"], out_dir=d, index=meta["index"], pixel_size=meta["pixel_size_um"],
        frame_interval=meta["frame_interval_s"], shape=tuple(meta["shape"]), unit=meta["unit"],
        kymo=kymo, kymo_smoothed=kymo, additional=additional,
        base=pd.read_csv(d / "cells_base.tsv", sep="\t"),
        stage_xy=tuple(meta["stage_xy_m"]) if meta["stage_xy_m"] else None,
        tile_size=tuple(meta["tile_size_m"]) if meta["tile_size_m"] else None,
        tiles=[tuple(t) for t in meta["tiles"]], stage_info_block=meta["stage_info_block"],
        source=meta.get("source", ""), stage_known=meta.get("stage_known", True),
    )


def _write_dashboard(result: ImageResult, viewer: ViewerData, settings: Settings, route=None) -> None:
    if settings.display.dashboard:
        from .dashboard import write_image_dashboard

        write_image_dashboard(result, viewer, settings, route)


def _routes(results: list[ImageResult], out: Path) -> dict[str, list[list[int]]]:
    """Visiting order of the .rgn chunks per image, as row indices into result.cells (from hit_chunks.json)."""
    path = out / "hit_chunks.json"
    if not path.exists():
        return {}
    chunks = json.loads(path.read_text())
    routes = {}
    for r in results:
        index = {int(c): i for i, c in enumerate(r.cells["cell"])}
        routes[r.name] = [[index[int(c)] for im, c in zip(ch["image"], ch["cell"], strict=True)
                           if str(im) == r.name and int(c) in index] for ch in chunks]
    return routes


# ---------------------------------------------------------------- screening output (all images)


def write_screening_outputs(results: list[ImageResult], settings: Settings, out: Path) -> pd.DataFrame:
    sc = settings.screening
    # remove hit files of an earlier run/reapply, so that no stale chunks remain next to the new ones
    stale = re.compile(r"(hits_\d+-\d+\.tsv|HITS_.*\.rgn|hit_positions\.png)")
    for p in out.iterdir():
        if p.is_file() and stale.fullmatch(p.name):
            p.unlink()
    all_cells = pd.concat([r.cells for r in results], ignore_index=True)
    coord_cols = [c for c in BASE_COLUMNS if c in all_cells.columns] + (
        ["additional_intensity"] if "additional_intensity" in all_cells else []
    ) + (["class_additional"] if "class_additional" in all_cells else [])
    all_cells[coord_cols].to_csv(out / "cell_coordinates.tsv", sep="\t", index=False, float_format="%.10g")

    hits = screening.sort_hits(all_cells[all_cells["hit"]].copy(), sc)
    hits.insert(0, "rank", np.arange(1, len(hits) + 1))
    hits.to_csv(out / "hits.tsv", sep="\t", index=False, float_format="%.10g")
    run_name = _safe(results[0].name if len(results) == 1 else out.name)
    have_positions = hits[["abs_x_m", "abs_y_m"]].notna().all(axis=None) if len(hits) else False
    chunks: list[pd.DataFrame] = []
    if len(hits) and have_positions:
        stage.write_rgn(out / f"HITS_{run_name}.rgn", hits[["abs_x_m", "abs_y_m"]].to_numpy())
        size = max(1, sc.max_hits_per_rgn)
        # the routes are chained: the first starts near the first tile of the scan, every next one near the end
        # of the previous one
        first_tile = results[0].tiles[0] if results[0].tiles else None
        start = np.array([first_tile[0] + first_tile[2] / 2, first_tile[1] + first_tile[3] / 2]) if first_tile else None
        for k in range(math.ceil(len(hits) / size)):
            chunk = hits.iloc[k * size : (k + 1) * size]
            a, b = k * size + 1, k * size + len(chunk)
            if sc.optimize_path and len(chunk) > 2:
                order = stage.optimize_path(chunk[["abs_x_m", "abs_y_m"]].to_numpy(), sc.max_optimization_time, start)
                chunk = chunk.iloc[order]  # whole rows are reordered (fixes issue I9)
                start = chunk[["abs_x_m", "abs_y_m"]].to_numpy()[-1]
            chunk = chunk.copy()
            chunk.insert(1, "visit_order", np.arange(1, len(chunk) + 1))
            chunk.to_csv(out / f"hits_{a}-{b}.tsv", sep="\t", index=False, float_format="%.10g")
            stage.write_rgn(out / f"HITS_{run_name}_{a}-{b}.rgn", chunk[["abs_x_m", "abs_y_m"]].to_numpy())
            chunks.append(chunk)
        tiles = [t for r in results for t in r.tiles]
        tiles = list(dict.fromkeys(tiles))
        plots.hit_positions(out / "hit_positions.png", chunks, tiles)
    elif len(hits):
        log.warning("Hits found but no stage positions: no .rgn files written")
    log.info("Screening total: %d hits in %d cells", len(hits), len(all_cells))
    (out / "hit_chunks.json").write_text(
        json.dumps([{"image": c["image"].tolist(), "cell": c["cell"].tolist()} for c in chunks])
    )
    return hits
