"""Down-sampled, 8-bit encoded image data for the HTML dashboard."""

from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


@dataclass
class ViewerData:
    lifetime8: np.ndarray  # (F, h, w) uint8; 0 = no lifetime, 1..255 = lo..hi
    intensity8: np.ndarray  # (F, h, w) uint8
    projection8: np.ndarray  # (h, w) uint8
    labels: np.ndarray  # (h, w) int32 (nearest-neighbour down-sampled)
    frames: np.ndarray  # original frame index of each viewer frame
    factor: int  # down-sampling factor
    lo: float
    hi: float

    def save(self, path) -> None:
        np.savez_compressed(path, **{k: getattr(self, k) for k in self.__dataclass_fields__})

    @classmethod
    def load(cls, path) -> ViewerData:
        with np.load(path) as z:
            return cls(**{k: (z[k] if z[k].ndim else z[k].item()) for k in z.files})


def _block_nanmean(stack: np.ndarray, f: int) -> np.ndarray:
    if f == 1:
        return stack
    t, h, w = stack.shape
    h2, w2 = h // f, w // f
    blocks = stack[:, : h2 * f, : w2 * f].reshape(t, h2, f, w2, f)
    finite = np.isfinite(blocks)
    total = np.where(finite, blocks, 0).sum(axis=(2, 4))
    count = finite.sum(axis=(2, 4))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / count, np.nan)


def _nan_box(stack: np.ndarray, rxy: float, rt: float) -> np.ndarray:
    """NaN-aware box mean with radii (frames, pixels): normalized convolution."""
    size = (2 * round(rt) + 1, 2 * round(rxy) + 1, 2 * round(rxy) + 1)
    if size == (1, 1, 1):
        return stack
    finite = np.isfinite(stack)
    total = ndi.uniform_filter(np.where(finite, stack, 0).astype(np.float32), size, mode="nearest")
    count = ndi.uniform_filter(finite.astype(np.float32), size, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(count > 0.2, total / count, np.nan)
    return np.where(finite | (count > 0.5), out, np.nan)


def _to8(x: np.ndarray, lo: float, hi: float, reserve_zero: bool) -> np.ndarray:
    scaled = (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)
    scaled = np.clip(np.nan_to_num(scaled, nan=0), 0, 1)
    if reserve_zero:
        out = 1 + np.round(scaled * 254)
        return np.where(np.isfinite(x), out, 0).astype(np.uint8)
    return np.round(scaled * 255).astype(np.uint8)


def prepare(
    intensity: np.ndarray,
    lifetime: np.ndarray,
    projection: np.ndarray,
    labels: np.ndarray,
    display_range: tuple[float, float],
    smooth_xy: float,
    smooth_t: float,
    max_size: int = 1024,
    max_megapixels: float = 200.0,
) -> ViewerData:
    t, h, w = intensity.shape
    f = max(1, math.ceil(max(h, w) / max_size))
    frames_total = (h // f) * (w // f) * t / 1e6
    stride = max(1, math.ceil(frames_total / max_megapixels))
    frames = np.arange(0, t, stride)
    inten = _block_nanmean(intensity[frames].astype(np.float32), f)
    tau = lifetime[frames].astype(np.float32)
    tau = np.where(np.isfinite(tau) & (tau != 0), tau, np.nan)
    tau = _block_nanmean(tau, f)
    tau = _nan_box(tau, smooth_xy / f, smooth_t / stride)
    proj = _block_nanmean(projection[np.newaxis].astype(np.float32), f)[0]
    lab = labels[: (h // f) * f : f, : (w // f) * f : f]

    valid = tau[np.isfinite(tau)]
    dmin, dmax = display_range
    span = dmax - dmin
    if valid.size:
        p1, p99 = np.percentile(valid, [0.5, 99.5])
        lo, hi = min(dmin - 0.25 * span, p1), max(dmax + 0.25 * span, p99)
    else:
        lo, hi = dmin, dmax

    pos = inten[np.isfinite(inten)]
    ilo, ihi = (np.percentile(pos, [0.2, 99.8]) if pos.size else (0, 1))
    pp = proj[np.isfinite(proj)]
    plo, phi = (np.percentile(pp, [0.2, 99.8]) if pp.size else (0, 1))
    return ViewerData(
        lifetime8=_to8(tau, lo, hi, True),
        intensity8=_to8(inten, ilo, ihi, False),
        projection8=_to8(proj, plo, phi, False),
        labels=lab.astype(np.int32),
        frames=frames,
        factor=f,
        lo=float(lo),
        hi=float(hi),
    )


def png_data_url(arr: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", optimize=False, compress_level=6)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def frame_urls(v: ViewerData) -> list[str]:
    """One RGB PNG per frame: R = lifetime code, G = intensity, B = 0."""
    zeros = np.zeros_like(v.lifetime8[0])
    return [png_data_url(np.dstack([v.lifetime8[i], v.intensity8[i], zeros])) for i in range(len(v.frames))]


def labels_url(labels: np.ndarray) -> str:
    """Label image as RGB PNG: id = R + 256 G + 65536 B."""
    lab = labels.astype(np.uint32)
    rgb = np.dstack([lab & 255, (lab >> 8) & 255, (lab >> 16) & 255]).astype(np.uint8)
    return png_data_url(rgb)


def float_b64(arr: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(arr, dtype="<f4").tobytes()).decode("ascii")
