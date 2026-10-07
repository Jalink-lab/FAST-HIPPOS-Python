"""Cell segmentation, label filtering and per-cell statistics."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage import filters, measure, morphology, segmentation

from .config import SegmentationSettings

log = logging.getLogger(__name__)


def projection(stack: np.ndarray, start: int | None = None, end: int | None = None) -> np.ndarray:
    """Sum projection of a (T, Y, X) stack over frames [start, end] (inclusive, 0-based); NaN counts as 0."""
    sl = slice(start or 0, None if end is None else end + 1)
    return np.nansum(stack[sl], axis=0).astype(np.float32)


def prepare_for_cellpose(img: np.ndarray, gamma: float | None = None, saturated: float = 0.35) -> np.ndarray:
    """NaN -> mean of the darkest 5 %, optional gamma, contrast stretch with `saturated` % clipping, to uint16."""
    img = img.astype(np.float64).copy()
    finite = np.isfinite(img)
    if not finite.all():
        low = img[finite][img[finite] <= np.percentile(img[finite], 5)]
        img[~finite] = low.mean() if low.size else 0
    if gamma:
        img = np.clip(img - img.min(), 0, None) ** gamma
    lo, hi = np.percentile(img, [saturated / 2, 100 - saturated / 2])
    if hi <= lo:
        hi = lo + 1
    return (np.clip((img - lo) / (hi - lo), 0, 1) * 65535).astype(np.uint16)


def segment(img: np.ndarray, settings: SegmentationSettings) -> np.ndarray:
    """Return an int32 label image for a 2-D projection."""
    method = settings.method
    if method == "labelmap":
        from .io import read_tiff

        if settings.labelmap is None:
            raise ValueError("segmentation.method = 'labelmap' requires segmentation.labelmap")
        labels = read_tiff(Path(settings.labelmap)).data[0, 0].astype(np.int32)
        if labels.shape != img.shape:
            raise ValueError(f"Labelmap shape {labels.shape} does not match the image {img.shape}")
        return labels
    if method == "threshold":
        return threshold_segmentation(img, settings.diameter or 20)
    if method == "cellpose":
        return run_cellpose(prepare_for_cellpose(img, settings.gamma), settings)
    raise ValueError(f"Unknown segmentation method '{method}'")


def threshold_segmentation(img: np.ndarray, diameter: float = 20) -> np.ndarray:
    """Classical fallback: Otsu threshold + distance-transform watershed (no GPU / Cellpose needed)."""
    img = np.nan_to_num(img.astype(np.float64))
    smooth = ndi.gaussian_filter(img, max(diameter / 15, 1))
    mask = smooth > filters.threshold_otsu(smooth)
    mask = morphology.remove_small_objects(mask, max_size=int(np.pi * (diameter / 4) ** 2))
    distance = ndi.distance_transform_edt(mask)
    peaks = morphology.h_maxima(ndi.gaussian_filter(distance, 1), max(diameter / 10, 1))
    markers = measure.label(peaks)
    return segmentation.watershed(-distance, markers, mask=mask).astype(np.int32)


def cellpose_version(settings: SegmentationSettings) -> int:
    if settings.cellpose_version:
        return settings.cellpose_version
    return 4 if settings.cellpose_model == "cpsam" else 3


def run_cellpose(img: np.ndarray, settings: SegmentationSettings) -> np.ndarray:
    version = cellpose_version(settings)
    params = {
        "model": settings.cellpose_model,
        "diameter": settings.diameter,
        "flow_threshold": settings.flow_threshold,
        "cellprob_threshold": settings.cellprob_threshold,
        "use_gpu": settings.use_gpu,
    }
    if _installed_cellpose_major() == version:
        from . import _cellpose_runner

        log.info("Running Cellpose %d in-process (model %s)", version, settings.cellpose_model)
        return _cellpose_runner.run(img, params)

    python = settings.cellpose4_python if version == 4 else settings.cellpose3_python
    if python is None:
        raise RuntimeError(
            f"Cellpose {version} is not installed in this environment. Set segmentation.cellpose{version}_python "
            f"to the python executable of an environment with Cellpose {version}."
        )
    log.info("Running Cellpose %d via %s (model %s)", version, python, settings.cellpose_model)
    runner = Path(__file__).with_name("_cellpose_runner.py")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "image.npy", Path(tmp) / "masks.npy"
        np.save(src, img)
        result = subprocess.run(
            [str(python), str(runner), str(src), str(dst), json.dumps(params)], capture_output=True, text=True, check=False
        )
        if result.returncode != 0 or not dst.exists():
            raise RuntimeError(f"Cellpose failed:\n{result.stderr[-3000:]}")
        return np.load(dst).astype(np.int32)


def _installed_cellpose_major() -> int | None:
    try:
        from importlib.metadata import version

        return int(version("cellpose").split(".")[0])
    except Exception:  # noqa: BLE001 - not installed / broken metadata
        return None


def circularity(labels: np.ndarray) -> np.ndarray:
    """4*pi*area/perimeter^2 per label (index = label - 1), Crofton perimeter as in MorphoLibJ.

    Clipped to 1: small digital objects can otherwise exceed 1, which would make them fail
    a 'max_circularity = 1' filter.
    """
    props = measure.regionprops(labels)
    circ = np.ones(labels.max(), dtype=float)
    for p in props:
        perimeter = p.perimeter_crofton
        if perimeter > 0:
            circ[p.label - 1] = min(4 * np.pi * p.area / perimeter**2, 1.0)
    return circ


def filter_labels(
    labels: np.ndarray, intensity: np.ndarray, min_size: int, max_circularity: float, min_intensity: float
) -> np.ndarray:
    """Remove labels that are too small, too round or too dim; relabel to 1..N.

    All criteria are evaluated on the same (original) label ids, which fixes the misaligned
    circularity filter of the Fiji macro (SPEC issue I5).
    """
    labels, _, _ = segmentation.relabel_sequential(labels)
    n = int(labels.max())
    if n == 0:
        return labels
    idx = np.arange(1, n + 1)
    area = ndi.sum_labels(np.ones_like(labels), labels, idx)
    mean = ndi.mean(np.nan_to_num(intensity), labels, idx)
    keep = area >= min_size
    if max_circularity < 1.0:
        keep &= circularity(labels) < max_circularity
    if min_intensity > 0:
        keep &= mean >= min_intensity
    lut = np.zeros(n + 1, dtype=np.int32)
    lut[1:][keep] = np.arange(1, keep.sum() + 1)
    log.info("Label filtering: %d of %d labels kept", keep.sum(), n)
    return lut[labels]


def cell_statistics(labels: np.ndarray, intensity: np.ndarray) -> pd.DataFrame:
    """Per-cell statistics on the projection (row i <-> label i+1)."""
    props = measure.regionprops_table(
        labels,
        intensity_image=np.nan_to_num(intensity),
        properties=("label", "area", "intensity_mean", "centroid", "bbox", "perimeter_crofton"),
    )
    df = pd.DataFrame(props).rename(
        columns={
            "area": "area_px",
            "intensity_mean": "mean_intensity",
            "centroid-0": "centroid_y",
            "centroid-1": "centroid_x",
            "bbox-0": "bbox_y0",
            "bbox-1": "bbox_x0",
            "bbox-2": "bbox_y1",
            "bbox-3": "bbox_x1",
        }
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        df["circularity"] = np.clip(4 * np.pi * df["area_px"] / df.pop("perimeter_crofton") ** 2, 0, 1)
    return df.set_index("label", drop=False)
