"""End-to-end processing: per image (segment, measure, analyze, save, dashboard) and per run (screening output)."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__, events, kymograph, modalities, plots, preprocess, screening, segmentation, stage
from .config import Modality, Settings
from .io import ImageData, iter_images, write_tiff
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

    @property
    def n_cells(self) -> int:
        return self.kymo.shape[1]

    @property
    def hit_kymo(self) -> np.ndarray:
        return self.kymo_smoothed


# ---------------------------------------------------------------- run


def run(settings: Settings, reapply: bool = False) -> list[ImageResult]:
    out = Path(settings.input.output)
    out.mkdir(parents=True, exist_ok=True)
    _setup_logging(out / "run_log.txt")
    log.info("FAST-HIPPOS (Python) %s%s", __version__, " - re-applying analysis to saved data" if reapply else "")
    (out / "settings_used.json").write_text(json.dumps(settings.to_dict(), indent=2))

    results: list[ImageResult] = []
    if reapply:
        for meta in sorted(out.glob("*/meta.json")):
            result = load_result(meta.parent)
            analyze(result, settings)
            save_tables(result, settings)
            _write_dashboard(result, ViewerData.load(result.out_dir / "viewer.npz"), settings)
            results.append(result)
        results.sort(key=lambda r: r.index)
    else:
        positions_all = None
        if settings.screening.enabled and settings.screening.stage_positions_file:
            positions_all = stage.read_positions_file(Path(settings.screening.stage_positions_file))
        index = 0
        for path in settings.input.files:
            for image in iter_images(Path(path), settings.input.series):
                log.info("--- %s", image.name)
                result = process_image(image, index, settings, positions_all)
                if result is not None:
                    results.append(result)
                index += 1
    if not results:
        log.warning("No images with cells were analyzed")
        return results
    if settings.screening.enabled:
        write_screening_outputs(results, settings, out)
    from .dashboard import write_index

    write_index(results, settings, out)
    log.info("Done. Output in %s", out)
    return results


def _setup_logging(path: Path) -> None:
    logger = logging.getLogger("fast_hippos")
    logger.setLevel(logging.INFO)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    for handler in (logging.FileHandler(path, mode="w", encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(fmt)
        logger.addHandler(handler)


# ---------------------------------------------------------------- per image


def process_image(
    image: ImageData, index: int, settings: Settings, positions_all: np.ndarray | None = None
) -> ImageResult | None:
    s_in, s_seg, s_disp = settings.input, settings.segmentation, settings.display
    if s_in.remove_last_frame and image.n_frames > 1:
        image.data = image.data[:-1]
    c = s_in.intensity_channel
    reg_channels = [c, c + 1] if s_in.modality in (Modality.TCSPC, Modality.RATIO) else [c]
    if settings.preprocess.correct_bidirectional:
        image.data, _ = preprocess.correct_bidirectional(image.data, reg_channels)
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
    )
    _stage_geometry(result, image, positions_all, settings)
    base = pd.DataFrame({
        "image": image.name, "tile": index, "cell": stats["label"].to_numpy(),
        "area_px": stats["area_px"].to_numpy(), "mean_intensity": stats["mean_intensity"].to_numpy(),
        "circularity": stats["circularity"].to_numpy(),
        "centroid_x": centroids[:, 0], "centroid_y": centroids[:, 1],
        "pos_x_px": positions[:, 0], "pos_y_px": positions[:, 1],
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

    viewer = prepare(
        intensity, lifetime, proj, labels, display_range(result, settings),
        s_disp.overlay_smooth_xy, s_disp.overlay_smooth_t, s_disp.dashboard_max_size, s_disp.dashboard_max_megapixels,
    )
    viewer.save(out_dir / "viewer.npz")
    _write_dashboard(result, viewer, settings)
    return result


def _safe(name: str) -> str:
    return "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in name).strip()


def _stage_geometry(result: ImageResult, image: ImageData, positions_all: np.ndarray | None, settings: Settings):
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
        origin = info.origin_tile
        log.info("Stitched image: %d x %d tiles, overlap %.1f %%", n_tiles[0], n_tiles[1], overlap * 100)
        result.stage_info_block = stage.stitched_info_block(stage.StageInfo(positions, n_tiles, tile_size, overlap))
    else:
        # one image = one tile (fixes the macro dividing a single tile by the number of tiles, issue I16)
        tile_size = (width * px * 1e-6, height * px * 1e-6)
        if positions_all is not None:
            if result.index >= len(positions_all):
                raise ValueError(f"Stage positions file has {len(positions_all)} positions; image {result.index} has none")
            position = positions_all[result.index]
        elif image.stage_position is not None:
            position = image.stage_position
        else:
            log.warning("No stage position for %s: using (0, 0)", image.name)
            position = (0.0, 0.0)
        positions, origin = np.array([position], dtype=float), 0
    result.stage_xy = tuple(positions[origin])
    result.tile_size = tuple(tile_size)
    w, h = tile_size
    result.tiles = [(-p[1] - w / 2, -p[0] - h / 2, w, h) for p in positions]


def analyze(result: ImageResult, settings: Settings) -> None:
    """Events, sorting, metrics, classification and hits (cheap; re-run by `reapply`)."""
    sc = settings.screening
    result.kymo_smoothed = kymograph.smooth_time(result.kymo, settings.display.smooth_traces)
    ev = events.determine(kymograph.population_mean(result.kymo), settings.events)
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
        "stage_info_block": result.stage_info_block, "version": __version__,
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
        dm = settings.display
        ylim = None if settings.input.modality == Modality.INTENSITY else (dm.min_lifetime, dm.max_lifetime)
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
    )


def _write_dashboard(result: ImageResult, viewer: ViewerData, settings: Settings) -> None:
    if settings.display.dashboard:
        from .dashboard import write_image_dashboard

        write_image_dashboard(result, viewer, settings)


# ---------------------------------------------------------------- screening output (all images)


def write_screening_outputs(results: list[ImageResult], settings: Settings, out: Path) -> pd.DataFrame:
    sc = settings.screening
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
        for k in range(math.ceil(len(hits) / size)):
            chunk = hits.iloc[k * size : (k + 1) * size]
            a, b = k * size + 1, k * size + len(chunk)
            if sc.optimize_path and len(chunk) > 2:
                order = stage.optimize_path(chunk[["abs_x_m", "abs_y_m"]].to_numpy(), sc.max_optimization_time)
                chunk = chunk.iloc[order]  # whole rows are reordered (fixes issue I9)
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
