"""Per-cell response metrics, validity gates and hit criteria."""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from skimage.filters import threshold_otsu

from .config import CELL_MEASURES, METRICS, Criterion, ScreeningSettings, metric_label
from .events import Events

log = logging.getLogger(__name__)


def _nan(func, a, axis=0):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return func(a, axis=axis)


def timed_window(events: Events, settings: ScreeningSettings) -> slice:
    """Sub-window of the response used for the 'mean' response metrics."""
    r0, r1 = events.response.start, events.response.stop
    w, m = settings.response_window, settings.response_window_margin
    if r1 <= r0 or w is None or w <= 0:  # empty: the whole response
        return slice(r0, r1)
    if settings.response_window_anchor == "after_stimulation":
        a = min(r0 + m, r1)
        return slice(a, min(a + w, r1))
    if settings.response_window_anchor == "before_calibration":
        b = max(r1 - m, r0)
        return slice(max(b - w, r0), b)
    raise ValueError("response_window_anchor must be 'after_stimulation' or 'before_calibration'")


def compute_metrics(
    kymo: np.ndarray,
    events: Events,
    settings: ScreeningSettings,
    additional: np.ndarray | None = None,
) -> pd.DataFrame:
    """All response metrics for all cells; ``kymo`` is (T, N), the (smoothed) lifetime kymograph.

    Mirrored in templates/screening.js (the dashboard recomputes these live); keep both in sync.
    """
    kymo = kymo.astype(np.float64)
    if additional is not None:
        additional = additional.astype(np.float64)
    n = kymo.shape[1]
    base = _nan(np.nanmean, kymo[events.baseline])
    pop_baseline = float(_nan(np.nanmean, base, axis=None)) if n else np.nan
    df = pd.DataFrame({"cell": np.arange(1, n + 1)})
    df["baseline"] = base
    df["baseline_offset_from_population"] = base - pop_baseline

    resp = kymo[events.response]
    if resp.shape[0] > 0:
        timed = kymo[timed_window(events, settings)]
        diff = resp - base
        df["mean_during_response"] = _nan(np.nanmean, timed)
        df["mean_response"] = df["mean_during_response"] - base
        df["peak_during_response"] = _nan(np.nanmax, resp)
        df["peak_response"] = df["peak_during_response"] - base
        df["peak_response_vs_population"] = df["peak_during_response"] - pop_baseline
        with np.errstate(divide="ignore", invalid="ignore"):
            df["mean_peak_response_ratio"] = df["mean_response"] / df["peak_response"]
        reached = np.nan_to_num(diff, nan=-np.inf) >= settings.rise_time_fraction * df["peak_response"].to_numpy()
        first = np.argmax(reached, axis=0).astype(float) + 1
        first[~reached.any(axis=0)] = np.nan
        df["rise_time_(frames)"] = first
        half = resp.shape[0] // 2
        with np.errstate(divide="ignore", invalid="ignore"):
            df["late_early_response_ratio"] = _nan(np.nanmean, diff[half:]) / _nan(np.nanmean, diff[:half]) if half else np.nan
    else:
        for col in ["mean_during_response", "mean_response", "peak_during_response", "peak_response", "peak_response_vs_population", "mean_peak_response_ratio", "rise_time_(frames)", "late_early_response_ratio"]:
            df[col] = np.nan

    cal = kymo[events.calibration_window]
    df["mean_during_calibration"] = _nan(np.nanmean, cal) if cal.shape[0] else np.nan
    df["calibration_response"] = df["mean_during_calibration"] - base

    if additional is not None:
        if settings.additional_channel_metric == "first":
            df["additional_channel_intensity"] = additional[0]
        else:
            df["additional_channel_intensity"] = _nan(np.nanmean, additional)
    df.attrs["population_baseline"] = pop_baseline
    return df


def validity(df: pd.DataFrame, settings: ScreeningSettings, has_calibration: bool) -> pd.Series:
    """Gates that every hit must pass. NaN values fail (the macro's `== NaN` test never did; issue I4)."""
    valid = pd.Series(True, index=df.index)
    if settings.baseline_calibration_diff is not None:
        if has_calibration:
            lo, hi = settings.baseline_calibration_diff
            valid &= df["calibration_response"].between(lo, hi)
        else:
            log.warning("No calibration window: baseline-calibration gate skipped")
    if settings.max_baseline_deviation is not None:
        valid &= df["baseline_offset_from_population"].abs() <= settings.max_baseline_deviation
    valid &= df["baseline"].notna()
    return valid


GATE_OPS = ("inside", "outside")


def in_polygon(x, y, polygon, log_x: bool = False, log_y: bool = False) -> np.ndarray:
    """Which points (x, y) are inside the polygon: even-odd rule, as inPolygon in templates/screening.js (same
    arithmetic, so that the dashboard finds the same cells). On a log axis the edges are straight in log10; a point
    with NaN (or a value <= 0 on a log axis) is never inside."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    px, py = (np.array([float(p[k]) for p in polygon]) for k in (0, 1))
    with np.errstate(divide="ignore", invalid="ignore"):
        if log_x:
            x, px = np.where(x > 0, np.log10(x), np.nan), np.log10(px)
        if log_y:
            y, py = np.where(y > 0, np.log10(y), np.nan), np.log10(py)
        inside = np.zeros(x.shape, dtype=bool)
        j = len(px) - 1
        for i in range(len(px)):
            crosses = (py[i] > y) != (py[j] > y)  # (then py[i] != py[j]: no division by zero where it is used)
            inside ^= crosses & (x < (px[j] - px[i]) * (y - py[i]) / (py[j] - py[i]) + px[i])
            j = i
    return inside & np.isfinite(x) & np.isfinite(y)


def is_gate(criterion: Criterion) -> bool:
    return criterion.op in GATE_OPS


def criterion_text(c) -> str:
    """A criterion (or its dict) in words: 'peak_response > 0.3', 'inside a gate on x vs y'."""
    get = c.get if isinstance(c, dict) else lambda k, d=None: getattr(c, k, d)
    if get("op") in GATE_OPS:
        return (f"{get('op')} a gate on {metric_label(get('metric2'))} vs {metric_label(get('metric'))} "
                f"({len(get('polygon') or [])} points)")
    return f"{metric_label(get('metric'))} {get('op')} {get('value')}" + (f" and {get('value2')}" if get("op") == "between" else "")


def criterion_dict(c: Criterion, default_logic: str) -> dict:
    """A criterion for the pages (dashboard, overview); a gate with its two metrics and polygon."""
    d = {"metric": c.metric, "op": c.op, "value": c.value, "value2": c.value2, "logic": (c.logic or default_logic).upper()}
    if is_gate(c):
        d |= {"metric2": c.metric2, "polygon": [[float(a), float(b)] for a, b in c.polygon or []],
              "log_x": bool(c.log_x), "log_y": bool(c.log_y)}
    return d


def passes(criterion: Criterion, df: pd.DataFrame) -> pd.Series:
    """Which cells pass one criterion (NaN never passes)."""
    c = criterion
    if is_gate(c):
        if not c.metric2 or not c.polygon or len(c.polygon) < 3:
            raise ValueError(f"Gate on '{c.metric}': needs metric2 and a polygon of at least 3 points")
        x, y = df[c.metric].to_numpy(dtype=float), df[c.metric2].to_numpy(dtype=float)
        inside = in_polygon(x, y, c.polygon, c.log_x, c.log_y)
        if c.op == "outside":  # outside, but with values that can be placed in the plane
            ok_x = np.isfinite(x) & ((x > 0) if c.log_x else True)
            ok_y = np.isfinite(y) & ((y > 0) if c.log_y else True)
            inside = ~inside & ok_x & ok_y
        return pd.Series(inside, index=df.index)
    if c.value is None:
        raise ValueError(f"Criterion on '{c.metric}': needs a value")
    return evaluate(c, df[c.metric]).fillna(False).astype(bool)


def evaluate(criterion: Criterion, values: pd.Series) -> pd.Series:
    if criterion.op == "<":
        return values < criterion.value
    if criterion.op == ">":
        return values > criterion.value
    if criterion.op == "between":
        if criterion.value2 is None:
            raise ValueError(f"Criterion on '{criterion.metric}': 'between' needs value2")
        return (values > criterion.value) & (values < criterion.value2)
    raise ValueError(f"Criterion on '{criterion.metric}': op must be '<', '>' or 'between'")


def find_hits(df: pd.DataFrame, settings: ScreeningSettings, has_calibration: bool) -> pd.DataFrame:
    """Add 'valid', 'pass_<metric>' and 'hit' columns. AND/OR is applied to booleans (fixes issue I7)."""
    df = df.copy()
    df["valid"] = validity(df, settings, has_calibration)
    if settings.random_hits:
        rng = np.random.default_rng(settings.random_seed)
        hits = rng.choice(len(df), size=min(settings.random_hits, len(df)), replace=False)
        df["hit"] = False
        df.loc[df.index[hits], "hit"] = True
        log.info("Random hits: %d", df["hit"].sum())
        return df
    and_passes, or_passes = [], []
    for k, crit in enumerate(settings.criteria):
        for metric in (crit.metric, crit.metric2) if is_gate(crit) else (crit.metric,):
            if metric not in df.columns:
                known = ", ".join([*METRICS, *CELL_MEASURES])
                raise ValueError(f"Unknown or unavailable metric '{metric}'. Known metrics: {known}")
        col = f"pass_{k + 1}_{crit.metric}" + (f"_{crit.metric2}_gate" if is_gate(crit) else "")
        df[col] = passes(crit, df)  # NaN never passes
        logic = (crit.logic or settings.logic).upper()
        (and_passes if logic == "AND" else or_passes).append(df[col])
    if not and_passes and not or_passes:
        df["hit"] = False
    else:
        # AND criteria must all pass; of the OR criteria at least one must pass (issue I7: on booleans)
        ok = pd.concat(and_passes, axis=1).all(axis=1) if and_passes else pd.Series(True, index=df.index)
        if or_passes:
            ok &= pd.concat(or_passes, axis=1).any(axis=1)
        df["hit"] = df["valid"] & ok
    n_valid = int(df["valid"].sum())
    log.info("Screening: %d hits in %d cells (%.1f %%; %d valid)", df["hit"].sum(), len(df),
             100 * df["hit"].mean() if len(df) else 0, n_valid)
    if len(df) >= 10 and n_valid < 0.2 * len(df):
        log.warning("Only %d of %d cells pass the quality gates: check their ranges (Screening, advanced settings: "
                    "Quality gates; or in the dashboard)", n_valid, len(df))
    return df


def manual_hits(path, image: str, cells: pd.Series) -> pd.Series:
    """Hits from a hand-made list (TSV with 'cell' and optionally 'image'; rows of other images are ignored)."""
    table = pd.read_csv(path, sep="\t")
    if "cell" not in table.columns:
        raise ValueError(f"{path}: a 'cell' column is required")
    if "image" in table.columns:
        table = table[table["image"].astype(str) == str(image)]
    hits = cells.isin(table["cell"].astype(int))
    log.info("Manual hits (%s): %d cells", Path(path).name, hits.sum())
    return hits


def classify_additional(intensity: pd.Series, threshold: float | None = None) -> tuple[pd.Series, float]:
    """Positive/negative cells from the additional channel: Otsu on log10(intensity), or a manual threshold."""
    values = intensity.to_numpy(dtype=float)
    positive = values[np.isfinite(values) & (values > 0)]
    if threshold is None:
        if positive.size < 2:
            return pd.Series(0, index=intensity.index), np.nan
        threshold = float(10 ** threshold_otsu(np.log10(positive)))
    cls = (intensity > threshold).astype(int)
    log.info("Additional channel classification: threshold %.3g, %d positive cells", threshold, cls.sum())
    return cls, threshold


def sort_hits(hits: pd.DataFrame, settings: ScreeningSettings) -> pd.DataFrame:
    if settings.sort_by is None:
        return hits
    if settings.sort_by not in hits.columns:
        log.warning("Cannot sort hits on '%s': column not present", settings.sort_by)
        return hits
    return hits.sort_values(settings.sort_by, ascending=not settings.sort_descending, kind="stable")
