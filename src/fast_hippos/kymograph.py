"""Per-cell traces. A kymograph is a (T, N) float array: row = frame, column = cell (label - 1)."""

from __future__ import annotations

import warnings

import numpy as np

from .config import Modality


def _per_label_sums(values: np.ndarray, labels: np.ndarray, n_labels: int) -> np.ndarray:
    """Sum of a (T, Y, X) array per frame and label -> (T, n_labels + 1); column 0 is background."""
    t = values.shape[0]
    index = labels.ravel()[np.newaxis, :] + (n_labels + 1) * np.arange(t)[:, np.newaxis]
    sums = np.bincount(index.ravel(), weights=values.reshape(t, -1).ravel(), minlength=t * (n_labels + 1))
    return sums.reshape(t, n_labels + 1)


def pooled(numerator: np.ndarray, denominator: np.ndarray, labels: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """sum(numerator) / sum(denominator) per cell and frame, over valid pixels."""
    n = int(labels.max())
    num = _per_label_sums(np.where(valid, numerator, 0).astype(np.float64), labels, n)
    den = _per_label_sums(np.where(valid, denominator, 0).astype(np.float64), labels, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (num / den)[:, 1:].astype(np.float32)


def weighted_lifetime(intensity: np.ndarray, lifetime: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Intensity-weighted mean lifetime per cell and frame: sum(tau * I) / sum(I) (the Fiji estimator).

    For mean-arrival-time lifetimes (Fast FLIM, TauContrast) this equals the lifetime of the pooled
    photons of the cell.
    """
    valid = np.isfinite(lifetime) & np.isfinite(intensity)
    return pooled(lifetime * intensity, intensity, labels, valid)


def cell_values(intensity: np.ndarray, lifetime: np.ndarray, labels: np.ndarray, modality: Modality) -> np.ndarray:
    """Per-cell lifetime / ratio / intensity, pooling the underlying signals of all pixels of the cell.

    - TCSPC (2 fitted components): sum(A1 tau1 + A2 tau2) / sum(A1 + A2), i.e. the amplitude-weighted
      lifetime of the cell's summed amplitudes (= fitting the summed decay with fixed tau1, tau2).
      The Fiji macro averaged per-pixel lifetimes weighted by intensity; since a pixel's intensity grows
      with its own lifetime, that estimate is biased upward by pixel noise and heterogeneity
      (SPEC issue I19). A1 + A2 = I / tau per pixel.
    - Ratio: sum(C1) / sum(C2), with C1 = I r / (1 + r) and C2 = I / (1 + r).
    - Fast FLIM / TauContrast / FD-FLIM: sum(I tau) / sum(I).
    - Intensity: mean intensity.
    """
    valid = np.isfinite(lifetime) & np.isfinite(intensity) & (lifetime != 0)
    if modality == Modality.TCSPC:
        with np.errstate(divide="ignore", invalid="ignore"):
            return pooled(intensity, intensity / lifetime, labels, valid)
    if modality == Modality.RATIO:
        return pooled(intensity * lifetime / (1 + lifetime), intensity / (1 + lifetime), labels, valid)
    if modality == Modality.INTENSITY:
        return mean_intensity(intensity, labels)
    return weighted_lifetime(intensity, lifetime, labels)


def mean_intensity(stack: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Mean of a (T, Y, X) stack per cell and frame (NaN pixels ignored)."""
    n = int(labels.max())
    finite = np.isfinite(stack)
    total = _per_label_sums(np.where(finite, stack, 0).astype(np.float64), labels, n)
    count = _per_label_sums(finite.astype(np.float64), labels, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (total / count)[:, 1:].astype(np.float32)


def smooth_time(kymo: np.ndarray, radius: float) -> np.ndarray:
    """NaN-aware box mean along time with window 2*radius + 1 (edges: nearest).

    Sums in the same order as the dashboard (templates/screening.js), so both give identical values.
    """
    r = int(radius)
    if r <= 0:
        return kymo
    t = kymo.shape[0]
    total = np.zeros(kymo.shape, np.float64)
    count = np.zeros(kymo.shape, np.float64)
    for k in range(-r, r + 1):
        shifted = kymo[np.clip(np.arange(t) + k, 0, t - 1)].astype(np.float64)
        finite = np.isfinite(shifted)
        total += np.where(finite, shifted, 0)
        count += finite
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(count > 0, total / count, np.nan).astype(np.float32)


def population_mean(kymo: np.ndarray) -> np.ndarray:
    """Mean over cells per frame (NaN-aware; all-NaN frames give NaN)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(kymo, axis=1)


def population_std(kymo: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanstd(kymo, axis=1)
