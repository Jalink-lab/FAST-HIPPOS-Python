"""Drift correction and bidirectional-scan phase correction, applied to the raw (T, C, Y, X) data
before the lifetime calculation, so that intensity and lifetime stay aligned."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from scipy import fft as sfft
from scipy import ndimage as ndi
from skimage.registration import phase_cross_correlation

log = logging.getLogger(__name__)


def registration_image(data: np.ndarray, channels: list[int]) -> np.ndarray:
    """Sum of the given 1-based channels, as (T, Y, X)."""
    return np.nansum(data[:, [c - 1 for c in channels]], axis=1)


def _spectrum(image: np.ndarray) -> np.ndarray:
    return sfft.rfft2(image.astype(np.float32, copy=False), workers=-1)


def _gauss(shape: tuple[int, int], sigma: float, cache: dict) -> np.ndarray | None:
    """Fourier transform of a periodic Gaussian of sigma pixels, for the half spectrum of rfft2 (None for 0). Blurring
    the cross-correlation is then a multiplication, whatever sigma is."""
    if sigma <= 0:
        return None
    if sigma not in cache:
        fy = sfft.fftfreq(shape[0])[:, None]
        fx = sfft.rfftfreq(shape[1])[None, :]
        cache[sigma] = np.exp(-2 * np.pi**2 * sigma**2 * (fy**2 + fx**2)).astype(np.float32)
    return cache[sigma]


def _cross_correlation(ref_f: np.ndarray, mov_f: np.ndarray, shape, g: np.ndarray | None) -> np.ndarray:
    """The (blurred) cross-correlation image of two frames, from their spectra (float32, periodic)."""
    prod = ref_f * np.conj(mov_f)
    if g is not None:
        prod *= g
    return sfft.irfft2(prod, s=shape, workers=-1)


def _peak(cc: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
    """The shift (dy, dx) of the highest point of a cross-correlation image, and that point."""
    idx = np.unravel_index(int(np.argmax(cc)), cc.shape)
    shift = np.array(idx, dtype=float)
    size = np.array(cc.shape)
    shift[shift > size // 2] -= size[shift > size // 2]
    return shift, idx


def _peak_shift(ref_f: np.ndarray, mov_f: np.ndarray, shape, blur_sigma: float, cache: dict | None = None) -> np.ndarray:
    """The shift from the spectra of the reference and the moving frame: the peak of their cross-correlation, after
    blurring the cross-correlation image with blur_sigma pixels."""
    return _peak(_cross_correlation(ref_f, mov_f, shape, _gauss(shape, blur_sigma, {} if cache is None else cache)))[0]


def cross_correlation_shift(reference: np.ndarray, moving: np.ndarray, blur_sigma: float = 0.0) -> np.ndarray:
    """(dy, dx) that registers `moving` onto `reference`: the peak of their cross-correlation, after blurring the
    cross-correlation image with blur_sigma (pixels; 0 = none), as the Fiji macro does to find the peak robustly.
    Without blur the same as skimage's phase_cross_correlation(normalization=None)."""
    return _peak_shift(_spectrum(reference), _spectrum(moving), reference.shape, blur_sigma)


def estimate_drift(
    reg: np.ndarray, reference: str = "first", edge_detect: bool = False, blur_sigma: float = 2.0
) -> np.ndarray:
    """Per-frame (dy, dx) shifts (T, 2) that register each frame onto the reference frame. Every frame is
    transformed once; per frame one cross-correlation image is made (and blurred, in the Fourier domain)."""
    reg = np.nan_to_num(reg.astype(np.float32))
    if edge_detect:
        reg = np.stack([_local_variance(f, 2) for f in reg])
    n, shape = reg.shape[0], reg.shape[1:]
    cache: dict = {}
    shifts = np.zeros((n, 2))
    if reference == "previous":
        prev = _spectrum(reg[0])
        for t in range(1, n):
            cur = _spectrum(reg[t])
            shifts[t] = shifts[t - 1] + _peak_shift(prev, cur, shape, blur_sigma, cache)
            prev = cur
    else:
        ref = _spectrum(reg[0] if reference == "first" else reg[-1])
        for t in range(n):
            shifts[t] = _peak_shift(ref, _spectrum(reg[t]), shape, blur_sigma, cache)
    return np.round(shifts)


def apply_shifts(data: np.ndarray, shifts: np.ndarray) -> np.ndarray:
    """Translate every frame of a (T, C, Y, X) array by integer shifts; uncovered pixels become 0."""
    out = np.zeros_like(data)
    for t, (dy, dx) in enumerate(shifts.astype(int)):
        out[t] = ndi.shift(data[t], (0, dy, dx), order=0, mode="constant", cval=0)
    return out


def correct_drift(data: np.ndarray, channels: list[int], reference="first", edge_detect=False, blur_sigma: float = 2.0):
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


def estimate_bidirectional_shift(reg: np.ndarray, axis: str = "y") -> float:
    """Offset (pixels, subpixel) between the even and odd scan lines of a (Y, X) image or (T, Y, X) stack.
    axis "y": the fast scan axis is vertical, so the scan lines are columns, offset along y; "x": rows, along x."""
    img = reg if reg.ndim == 2 else np.nansum(reg, axis=0, dtype=np.float32)
    img = np.nan_to_num(img.astype(np.float32, copy=False))
    # one common factor for all lines (does not change the offset): keeps the products in scikit-image's error
    # estimate of large summed images from overflowing
    mean = float(np.abs(img).mean())
    if mean > 0:
        img = img / mean
    if axis == "y":
        img = img.T  # columns become rows
    rows = (img.shape[0] // 2) * 2
    even, odd = img[0:rows:2], img[1:rows:2]
    shift, _, _ = phase_cross_correlation(even, odd, upsample_factor=20, normalization=None)
    return float(shift[1])


MIN_BIDIRECTIONAL_SHIFT = 0.05  # px; smaller phase shifts are left alone


def shift_x(a: np.ndarray, d: float) -> np.ndarray:
    """out[..., x] = a[..., x - d]: subpixel shift along the last axis only."""
    return shift_along(a, d, -1)


def shift_along(a: np.ndarray, d: float, axis: int) -> np.ndarray:
    """out = a shifted by d pixels along one axis only, by cubic (Catmull-Rom) interpolation with 4 taps; edges
    are extended. (ndi.shift on the 4-D stack interpolated over all axes: 4^4 taps, minutes.)"""
    a = np.moveaxis(a, axis, -1)
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
    return np.moveaxis(out, -1, axis)


def correct_bidirectional(data: np.ndarray, channels: list[int], axis: str = "y") -> tuple[np.ndarray, float]:
    """Shift the even scan lines by -s/2 and the odd ones by +s/2 to align both scan directions. axis "y": the
    scan lines are columns (fast scan axis vertical), shifted along y; "x": rows, shifted along x.
    (Stitched images: tiles with an odd width swap even and odd lines, so their offsets cancel out here;
    tile-by-tile correction is done by the stitching, see stitch.py.)"""
    s = estimate_bidirectional_shift(summed_image(data, channels), axis)
    if abs(s) < MIN_BIDIRECTIONAL_SHIFT:
        log.info("Bidirectional phase correction (along %s): %.2f px, not applied", axis, s)
        return data, s
    log.info("Bidirectional phase correction (along %s): %.2f px", axis, s)
    return apply_bidirectional(data, s, axis), s


def apply_bidirectional(data: np.ndarray, s: float, axis: str = "y") -> np.ndarray:
    """Shift the even scan lines of a (T, C, Y, X) stack by -s/2 and the odd ones by +s/2 (float32 result)."""
    out = np.empty(data.shape, np.float32)
    lines = (lambda k: (..., slice(None), slice(k, None, 2))) if axis == "y" else (lambda k: (..., slice(k, None, 2), slice(None)))
    along = -2 if axis == "y" else -1

    def frame(t):  # per frame (in threads; NumPy releases the GIL): little extra memory
        f = data[t].astype(np.float32)
        out[t][lines(0)] = shift_along(f[lines(0)], -s / 2, along)
        out[t][lines(1)] = shift_along(f[lines(1)], s / 2, along)

    with ThreadPoolExecutor(min(8, os.cpu_count() or 4)) as pool:
        list(pool.map(frame, range(data.shape[0])))
    return out


def _local_variance(img: np.ndarray, radius: int) -> np.ndarray:
    size = 2 * radius + 1
    mean = ndi.uniform_filter(img, size)
    return ndi.uniform_filter(img * img, size) - mean * mean
