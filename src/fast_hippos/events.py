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


def cell_noise_sigma(kymo: np.ndarray) -> float:
    """Noise of the second derivative of the population mean, from the cells: per frame the robust spread over the
    cells of their own second differences, divided by sqrt(number of cells); the median over the frames. Unlike
    noise_sigma it does not depend on the number of frames. (T, N) kymograph; 0 if it cannot be estimated."""
    k = np.asarray(kymo, dtype=float)
    if k.ndim != 2 or k.shape[0] < 3:
        return 0.0
    d2 = k[2:] - 2 * k[1:-1] + k[:-2]  # (T - 2, N)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # frames without finite values
        mad = np.nanmedian(np.abs(d2 - np.nanmedian(d2, axis=1, keepdims=True)), axis=1)
        sigma = 1.4826 * mad / np.sqrt(np.maximum(np.isfinite(d2).sum(axis=1), 1))
        value = float(np.nanmedian(sigma))
    return value if np.isfinite(value) else 0.0


def transitions(mean_trace: np.ndarray, sensitivity: float, kymo: np.ndarray | None = None) -> list[int]:
    """All upward transitions (frames) that stand out from the noise, strongest first (see detect)."""
    d2 = second_derivative(mean_trace)
    sigma = noise_sigma(d2)
    if kymo is not None:
        sigma = max(sigma, cell_noise_sigma(kymo))
    peaks, _props = find_peaks(d2, prominence=max(0, sensitivity * sigma))
    return [int(p) + 1 for p in peaks[np.argsort(d2[peaks])[::-1]]]


def detect(mean_trace: np.ndarray, sensitivity: float, kymo: np.ndarray | None = None) -> tuple[int | None, int | None]:
    """Find up to two upward transitions in the population-mean trace.

    A step up between frames i and i+1 gives a positive peak of the second derivative at i, so the
    transition frame is peak + 1. Peaks need a prominence of at least sensitivity * sigma, with sigma a
    robust (MAD-based) noise estimate of d2; the two highest are taken and ordered in time
    (first = stimulation, second = calibration).

    The Fiji macro used std(d2), which is dominated by the transitions themselves: a large calibration
    step can hide a clear stimulation (SPEC issue I17).

    With few frames the MAD of d2 rests on a handful of values and can be close to 0 (5 frames: 3 values), so that
    a flat trace shows a "transition". With the kymograph, sigma is at least the noise expected from the cells
    (cell_noise_sigma). The larger of the two is used: noise that all cells share (e.g. laser drift) is only in the
    first.
    """
    top = sorted(transitions(mean_trace, sensitivity, kymo)[:2])
    if not top:
        return None, None
    if len(top) == 1:
        return top[0], None
    return top[0], top[1]


def determine(mean_trace: np.ndarray, settings: EventSettings, kymo: np.ndarray | None = None) -> Events:
    """Events from the settings, or detected in the population-mean trace (kymo: (T, N) cell traces, for the noise
    floor, see detect)."""
    n = len(mean_trace)
    if settings.baseline_only or n < 2:
        log.info("Baseline-only mode")
        return Events(n, baseline_only=True, margin=settings.margin)
    s_set, c_set, no_cal = settings.stimulation_frame, settings.calibration_frame, settings.no_calibration
    if no_cal:
        c_set = None
    if s_set is not None and (c_set is not None or no_cal):
        ev = Events(n, s_set, c_set, margin=settings.margin)
        log.info("Stimulation frame %s, calibration frame %s (set)", s_set, "none" if no_cal else c_set)
        return ev
    if s_set is not None or c_set is not None:  # one frame set: the other is detected
        found = transitions(mean_trace, settings.sensitivity, kymo)
        if s_set is not None:
            c = next((f for f in found if f > s_set + settings.margin), None)
            log.info("Stimulation frame %d (set); %s", s_set,
                     f"calibration detected at frame {c}" if c is not None else "no calibration detected after it")
            return Events(n, s_set, c, margin=settings.margin)
        s = next((f for f in found if f < c_set - settings.margin), None)
        if s is None:
            log.warning("Calibration frame %d (set); no stimulation detected before it", c_set)
        else:
            log.info("Calibration frame %d (set); stimulation detected at frame %d", c_set, s)
        return Events(n, s, c_set, margin=settings.margin)
    if no_cal:  # only the stimulation: the strongest transition
        found = transitions(mean_trace, settings.sensitivity, kymo)
        if not found:
            log.warning("No stimulation detected; treating the whole trace as baseline")
            return Events(n, baseline_only=True, detected=True, margin=settings.margin)
        log.info("Detected stimulation at frame %d (no calibration)", found[0])
        return Events(n, found[0], None, detected=True, margin=settings.margin)
    s, c = detect(mean_trace, settings.sensitivity, kymo)
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
