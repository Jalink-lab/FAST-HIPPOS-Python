"""Stimulation / calibration detection and analysis windows.

Frame convention: ``stimulation`` and ``calibration`` are the 0-based indices of the *first* frame with
the respective stimulus. (The Fiji macro stored the last frame before the transition; the windows below
reproduce its 1-frame margins: the last frame before each transition is excluded from the preceding window.)
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks

from .config import EventSettings

log = logging.getLogger(__name__)


@dataclass
class Events:
    n_frames: int
    stimulation: int | None = None
    calibration: int | None = None
    baseline_only: bool = False
    detected: bool = False  # True if found automatically
    margin: int = 1

    @property
    def baseline(self) -> slice:
        if self.baseline_only or (self.stimulation is None and self.calibration is None):
            return slice(0, self.n_frames)
        first = self.stimulation if self.stimulation is not None else self.calibration
        return slice(0, max(first - self.margin, 1))

    @property
    def response(self) -> slice:
        if self.baseline_only or self.stimulation is None:
            return slice(0, 0)
        end = self.calibration - self.margin if self.calibration is not None else self.n_frames
        return slice(self.stimulation, max(end, self.stimulation + 1))

    @property
    def calibration_window(self) -> slice:
        if self.baseline_only or self.calibration is None:
            return slice(0, 0)
        return slice(self.calibration, self.n_frames)

    def to_dict(self) -> dict:
        return {
            "n_frames": self.n_frames,
            "stimulation": self.stimulation,
            "calibration": self.calibration,
            "baseline_only": self.baseline_only,
            "detected": self.detected,
            "margin": self.margin,
            "baseline": [self.baseline.start, self.baseline.stop],
            "response": [self.response.start, self.response.stop],
            "calibration_window": [self.calibration_window.start, self.calibration_window.stop],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Events:
        return cls(d["n_frames"], d["stimulation"], d["calibration"], d["baseline_only"], d["detected"], d["margin"])


def second_derivative(trace: np.ndarray) -> np.ndarray:
    """Centered second difference; d2[i] = a[i+1] - 2 a[i] + a[i-1], edges 0, NaNs interpolated first."""
    a = np.asarray(trace, dtype=float).copy()
    finite = np.isfinite(a)
    if not finite.all() and finite.any():
        a[~finite] = np.interp(np.flatnonzero(~finite), np.flatnonzero(finite), a[finite])
    d2 = np.zeros_like(a)
    if a.size >= 3:
        d2[1:-1] = a[2:] - 2 * a[1:-1] + a[:-2]
    return d2


def noise_sigma(x: np.ndarray) -> float:
    """Robust standard deviation (1.4826 * median absolute deviation), ignoring the zero edges."""
    core = x[1:-1] if x.size > 2 else x
    sigma = 1.4826 * float(np.median(np.abs(core - np.median(core))))
    return sigma if sigma > 0 else float(np.std(core))


def detect(mean_trace: np.ndarray, sensitivity: float) -> tuple[int | None, int | None]:
    """Find up to two upward transitions in the population-mean trace.

    A step up between frames i and i+1 gives a positive peak of the second derivative at i, so the
    transition frame is peak + 1. Peaks need a prominence of at least sensitivity * sigma, with sigma a
    robust (MAD-based) noise estimate of d2; the two highest are taken and ordered in time
    (first = stimulation, second = calibration).

    The Fiji macro used std(d2), which is dominated by the transitions themselves: a large calibration
    step can hide a clear stimulation (SPEC issue I17).
    """
    d2 = second_derivative(mean_trace)
    tol = sensitivity * noise_sigma(d2)
    peaks, _props = find_peaks(d2, prominence=max(0, tol))
    if peaks.size == 0:
        return None, None
    top = peaks[np.argsort(d2[peaks])[::-1][:2]] + 1
    top = np.sort(top)
    if top.size == 1:
        return int(top[0]), None
    return int(top[0]), int(top[1])


def determine(mean_trace: np.ndarray, settings: EventSettings) -> Events:
    n = len(mean_trace)
    if settings.baseline_only or n < 2:
        log.info("Baseline-only mode")
        return Events(n, baseline_only=True, margin=settings.margin)
    if settings.stimulation_frame is not None or settings.calibration_frame is not None:
        ev = Events(n, settings.stimulation_frame, settings.calibration_frame, margin=settings.margin)
        log.info("Manual stimulation / calibration frames: %s / %s", ev.stimulation, ev.calibration)
        return ev
    s, c = detect(mean_trace, settings.sensitivity)
    if s is None:
        log.warning("No stimulation or calibration detected; treating the whole trace as baseline")
        return Events(n, baseline_only=True, detected=True, margin=settings.margin)
    if c is None:
        log.warning("Only one transition detected (frame %d); assuming it is the stimulation", s)
    else:
        log.info("Detected stimulation at frame %d and calibration at frame %d", s, c)
    return Events(n, s, c, detected=True, margin=settings.margin)


def response_order(kymo: np.ndarray, events: Events) -> np.ndarray:
    """Cell indices sorted on mean response (whole trace when there is no response window), ascending."""
    win = events.response if events.response.stop > events.response.start else slice(0, events.n_frames)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        response = np.nanmean(kymo[win], axis=0)
    return np.argsort(np.nan_to_num(response, nan=-np.inf), kind="stable")
