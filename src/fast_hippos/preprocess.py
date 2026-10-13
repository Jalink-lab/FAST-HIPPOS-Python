"""Drift correction and bidirectional-scan phase correction, applied to the raw (T, C, Y, X) data
before the lifetime calculation, so that intensity and lifetime stay aligned."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from scipy import ndimage as ndi
from skimage.registration import phase_cross_correlation

log = logging.getLogger(__name__)


def registration_image(data: np.ndarray, channels: list[int]) -> np.ndarray:
    """Sum of the given 1-based channels, as (T, Y, X)."""
    return np.nansum(data[:, [c - 1 for c in channels]], axis=1)


def estimate_drift(
    reg: np.ndarray, reference: str = "first", edge_detect: bool = False, blur_sigma: float = 4.0
) -> np.ndarray:
    """Per-frame (dy, dx) shifts (T, 2) that register each frame onto the reference frame."""
    reg = np.nan_to_num(reg.astype(np.float32))
    if edge_detect:
        reg = np.stack([_local_variance(f, 2) for f in reg])
    if blur_sigma > 0:
        # blurring both images is equivalent to blurring the cross-correlation (as in the Fiji macro)
        reg = ndi.gaussian_filter(reg, sigma=(0, blur_sigma / np.sqrt(2), blur_sigma / np.sqrt(2)))
    n = reg.shape[0]
    shifts = np.zeros((n, 2))
    if reference == "previous":
        for t in range(1, n):
            shift, _, _ = phase_cross_correlation(reg[t - 1], reg[t], normalization=None)
            shifts[t] = shifts[t - 1] + shift
    else:
        ref = reg[0] if reference == "first" else reg[-1]
        for t in range(n):
            shifts[t], _, _ = phase_cross_correlation(ref, reg[t], normalization=None)
    return np.round(shifts)


def apply_shifts(data: np.ndarray, shifts: np.ndarray) -> np.ndarray:
    """Translate every frame of a (T, C, Y, X) array by integer shifts; uncovered pixels become 0."""
    out = np.zeros_like(data)
    for t, (dy, dx) in enumerate(shifts.astype(int)):
        out[t] = ndi.shift(data[t], (0, dy, dx), order=0, mode="constant", cval=0)
    return out


def correct_drift(data: np.ndarray, channels: list[int], reference="first", edge_detect=False, blur_sigma=4.0):
    if data.shape[0] < 2:
        return data, np.zeros((data.shape[0], 2))
    shifts = estimate_drift(registration_image(data, channels), reference, edge_detect, blur_sigma)
    log.info("Drift correction: max shift %.0f px", np.abs(shifts).max())
    return apply_shifts(data, shifts), shifts


def summed_image(data: np.ndarray, channels: list[int]) -> np.ndarray:
    """Sum over all frames of the given 1-based channels of a (T, C, Y, X) stack, as one float32 image. In one
    pass per channel, without intermediate copies of the stack (10x faster than registration_image().sum())."""
    img = np.zeros(data.shape[-2:], np.float32)
    for c in channels:
        frames = data[:, c - 1]  # a view
        if np.issubdtype(frames.dtype, np.floating):  # e.g. lifetime images with NaN gaps
            img += np.nansum(frames, axis=0, dtype=np.float32)
        else:
            img += frames.sum(axis=0, dtype=np.float32)
    return img


def estimate_bidirectional_shift(reg: np.ndarray) -> float:
    """Horizontal offset (pixels, subpixel) between odd and even scan lines of a (Y, X) image or (T, Y, X) stack."""
    img = reg if reg.ndim == 2 else np.nansum(reg, axis=0, dtype=np.float32)
    img = np.nan_to_num(img.astype(np.float32, copy=False))
    rows = (img.shape[0] // 2) * 2
    even, odd = img[0:rows:2], img[1:rows:2]
    shift, _, _ = phase_cross_correlation(even, odd, upsample_factor=20, normalization=None)
    return float(shift[1])


MIN_BIDIRECTIONAL_SHIFT = 0.05  # px; smaller phase shifts are left alone


def shift_x(a: np.ndarray, d: float) -> np.ndarray:
    """out[..., x] = a[..., x - d]: subpixel shift along the last axis only, by cubic (Catmull-Rom) interpolation
    with 4 taps; edges are extended. (ndi.shift on the 4-D stack interpolated over all axes: 4^4 taps, minutes.)"""
    t = -d
    n = int(np.floor(t))
    u = t - n
    w = [(-u**3 + 2 * u**2 - u) / 2, (3 * u**3 - 5 * u**2 + 2) / 2, (-3 * u**3 + 4 * u**2 + u) / 2, (u**3 - u**2) / 2]
    p = abs(n) + 2
    padded = np.pad(a, [(0, 0)] * (a.ndim - 1) + [(p, p)], mode="edge")
    width = a.shape[-1]
    out = np.zeros(a.shape, np.float32)
    for m, wm in zip(range(-1, 3), w, strict=True):
        start = p + n + m
        out += np.float32(wm) * padded[..., start : start + width]
    return out


def correct_bidirectional(data: np.ndarray, channels: list[int]) -> tuple[np.ndarray, float]:
    """Shift even lines by -s/2 and odd lines by +s/2 along x to align both scan directions."""
    s = estimate_bidirectional_shift(summed_image(data, channels))
    if abs(s) < MIN_BIDIRECTIONAL_SHIFT:
        log.info("Bidirectional phase correction: %.2f px, not applied", s)
        return data, s
    log.info("Bidirectional phase correction: %.2f px", s)
    out = np.empty(data.shape, np.float32)

    def frame(t):  # per frame (in threads; NumPy releases the GIL): little extra memory
        f = data[t].astype(np.float32)
        out[t, ..., 0::2, :] = shift_x(f[..., 0::2, :], -s / 2)
        out[t, ..., 1::2, :] = shift_x(f[..., 1::2, :], s / 2)

    with ThreadPoolExecutor(min(8, os.cpu_count() or 4)) as pool:
        list(pool.map(frame, range(data.shape[0])))
    return out, s


def _local_variance(img: np.ndarray, radius: int) -> np.ndarray:
    size = 2 * radius + 1
    mean = ndi.uniform_filter(img, size)
    return ndi.uniform_filter(img * img, size) - mean * mean
