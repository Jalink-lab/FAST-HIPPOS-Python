"""Drift correction and bidirectional-scan phase correction, applied to the raw (T, C, Y, X) data
before the lifetime calculation, so that intensity and lifetime stay aligned."""

from __future__ import annotations

import logging

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


def estimate_bidirectional_shift(reg: np.ndarray) -> float:
    """Horizontal offset (pixels, subpixel) between odd and even scan lines of a (T, Y, X) stack."""
    img = np.nan_to_num(reg.astype(np.float64)).sum(axis=0)
    rows = (img.shape[0] // 2) * 2
    even, odd = img[0:rows:2], img[1:rows:2]
    shift, _, _ = phase_cross_correlation(even, odd, upsample_factor=20, normalization=None)
    return float(shift[1])


def correct_bidirectional(data: np.ndarray, channels: list[int]) -> tuple[np.ndarray, float]:
    """Shift odd lines by +s/2 and even lines by -s/2 (cubic interpolation) to align both scan directions."""
    s = estimate_bidirectional_shift(registration_image(data, channels))
    log.info("Bidirectional phase correction: %.2f px", s)
    out = data.copy()
    out[..., 0::2, :] = ndi.shift(data[..., 0::2, :], (0, 0, 0, -s / 2), order=3, mode="nearest")
    out[..., 1::2, :] = ndi.shift(data[..., 1::2, :], (0, 0, 0, s / 2), order=3, mode="nearest")
    return out, s


def _local_variance(img: np.ndarray, radius: int) -> np.ndarray:
    size = 2 * radius + 1
    mean = ndi.uniform_filter(img, size)
    return ndi.uniform_filter(img * img, size) - mean * mean
