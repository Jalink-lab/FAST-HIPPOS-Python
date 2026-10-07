"""Per-cell response metrics, validity gates and hit criteria."""

from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd
from skimage.filters import threshold_otsu

from .config import METRICS, Criterion, ScreeningSettings
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
    if r1 <= r0 or w < 0:
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
    df["baseline_mean"] = base
    df["baseline_dev_pop"] = base - pop_baseline

    resp = kymo[events.response]
    if resp.shape[0] > 0:
        timed = kymo[timed_window(events, settings)]
        diff = resp - base
        df["response_mean_abs"] = _nan(np.nanmean, timed)
        df["response_mean_diff"] = df["response_mean_abs"] - base
        df["response_max_abs"] = _nan(np.nanmax, resp)
        df["response_max_diff"] = df["response_max_abs"] - base
        df["response_max_diff_pop"] = df["response_max_abs"] - pop_baseline
        with np.errstate(divide="ignore", invalid="ignore"):
            df["response_fraction"] = df["response_mean_diff"] / df["response_max_diff"]
        reached = np.nan_to_num(diff, nan=-np.inf) >= settings.rise_time_fraction * df["response_max_diff"].to_numpy()
        first = np.argmax(reached, axis=0).astype(float) + 1
        first[~reached.any(axis=0)] = np.nan
        df["rise_time_frames"] = first
        half = resp.shape[0] // 2
        with np.errstate(divide="ignore", invalid="ignore"):
            df["rapid_response_ratio"] = _nan(np.nanmean, diff[half:]) / _nan(np.nanmean, diff[:half]) if half else np.nan
    else:
        for col in ["response_mean_abs", "response_mean_diff", "response_max_abs", "response_max_diff", "response_max_diff_pop", "response_fraction", "rise_time_frames", "rapid_response_ratio"]:
            df[col] = np.nan

    cal = kymo[events.calibration_window]
    df["calibration_mean"] = _nan(np.nanmean, cal) if cal.shape[0] else np.nan
    df["calibration_diff"] = df["calibration_mean"] - base

    if additional is not None:
        if settings.additional_channel_metric == "first":
            df["additional_intensity"] = additional[0]
        else:
            df["additional_intensity"] = _nan(np.nanmean, additional)
    df.attrs["population_baseline"] = pop_baseline
    return df


def validity(df: pd.DataFrame, settings: ScreeningSettings, has_calibration: bool) -> pd.Series:
    """Gates that every hit must pass. NaN values fail (the macro's `== NaN` test never did; issue I4)."""
    valid = pd.Series(True, index=df.index)
    if settings.baseline_calibration_diff is not None:
        if has_calibration:
            lo, hi = settings.baseline_calibration_diff
            valid &= df["calibration_diff"].between(lo, hi)
        else:
            log.warning("No calibration window: baseline-calibration gate skipped")
    if settings.max_baseline_deviation is not None:
        valid &= df["baseline_dev_pop"].abs() <= settings.max_baseline_deviation
    valid &= df["baseline_mean"].notna()
    return valid


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
    passes = []
    for crit in settings.criteria:
        if crit.metric not in df.columns:
            known = ", ".join(METRICS)
            raise ValueError(f"Unknown or unavailable metric '{crit.metric}'. Known metrics: {known}")
        col = f"pass_{crit.metric}"
        df[col] = evaluate(crit, df[crit.metric]).fillna(False)  # NaN never passes
        passes.append(df[col])
    if not passes:
        df["hit"] = False
    else:
        combined = pd.concat(passes, axis=1)
        df["hit"] = df["valid"] & (combined.all(axis=1) if settings.logic.upper() == "AND" else combined.any(axis=1))
    log.info("Screening: %d hits in %d cells (%.1f %%)", df["hit"].sum(), len(df), 100 * df["hit"].mean() if len(df) else 0)
    return df


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
