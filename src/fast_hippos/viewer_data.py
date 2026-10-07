"""8-bit encoded image data for the HTML dashboard: an embedded overview plus (for large images) a pyramid of
lazily loaded tiles.

Encoding per pixel: R = lifetime code (0 = no lifetime, 1..255 = lo..hi), G = intensity (0..255).
Tiles are written as small JavaScript files ``FHTile(key, dataURL)`` so that they can be loaded with
<script> tags from a dashboard opened straight from disk (file://), where fetch() and reading pixels of
<img> files are blocked by the browser.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

log = logging.getLogger(__name__)
TILE = 512


@dataclass
class ViewerData:
    lifetime8: np.ndarray  # (F, h, w) uint8, overview level
    intensity8: np.ndarray  # (F, h, w) uint8
    projection8: np.ndarray  # (h, w) uint8
    labels: np.ndarray  # (h, w) int32 (nearest-neighbour down-sampled)
    frames: np.ndarray  # original frame index of each viewer frame
    factor: int  # down-sampling factor of the overview (power of 2)
    lo: float
    hi: float
    tiles: dict = field(default_factory=dict)  # pyramid levels below the overview (see write_tiles)

    def save(self, path) -> None:
        arrays = {k: getattr(self, k) for k in ("lifetime8", "intensity8", "projection8", "labels", "frames")}
        meta = {"factor": self.factor, "lo": self.lo, "hi": self.hi, "tiles": self.tiles}
        np.savez_compressed(path, meta=np.array(json.dumps(meta)), **arrays)

    @classmethod
    def load(cls, path) -> ViewerData:
        with np.load(path) as z:
            if "meta" not in z.files:  # files written by version 0.1.0.dev0 before tiling
                return cls(**{k: (z[k] if z[k].ndim else z[k].item()) for k in z.files})
            meta = json.loads(str(z["meta"]))
            return cls(**{k: z[k] for k in ("lifetime8", "intensity8", "projection8", "labels", "frames")}, **meta)


def _half(stack: np.ndarray) -> np.ndarray:
    """NaN-aware 2x2 block mean over the last two axes (odd edges dropped)."""
    h, w = stack.shape[-2] // 2 * 2, stack.shape[-1] // 2 * 2
    s = stack[..., :h, :w]
    blocks = s.reshape(s.shape[:-2] + (h // 2, 2, w // 2, 2))
    finite = np.isfinite(blocks)
    total = np.where(finite, blocks, 0).sum(axis=(-3, -1), dtype=np.float32)
    count = finite.sum(axis=(-3, -1))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / count, np.nan).astype(np.float32)


def _nan_box(stack: np.ndarray, rxy: float, rt: float) -> np.ndarray:
    """NaN-aware box mean with radii (pixels, frames) by normalized convolution; small holes are filled."""
    size = (2 * round(rt) + 1, 2 * round(rxy) + 1, 2 * round(rxy) + 1)
    if size == (1, 1, 1):
        return stack
    finite = np.isfinite(stack)
    total = ndi.uniform_filter(np.where(finite, stack, 0).astype(np.float32), size, mode="nearest")
    count = ndi.uniform_filter(finite.astype(np.float32), size, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(count > 0.2, total / count, np.nan).astype(np.float32)
    out[~finite & (count <= 0.5)] = np.nan
    return out


def _to8(x: np.ndarray, lo: float, hi: float, reserve_zero: bool) -> np.ndarray:
    scaled = (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)
    scaled = np.clip(np.nan_to_num(scaled, nan=0), 0, 1)
    if reserve_zero:
        out = 1 + np.round(scaled * 254)
        return np.where(np.isfinite(x), out, 0).astype(np.uint8)
    return np.round(scaled * 255).astype(np.uint8)


def _percentiles(x: np.ndarray, q, step: int):
    sample = x[..., ::step, ::step]
    sample = sample[np.isfinite(sample)]
    return np.percentile(sample, q) if sample.size else None


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
    tiles_dir: Path | None = None,
) -> ViewerData:
    """Encode the image data. If the image is larger than ``max_size`` and ``tiles_dir`` is given, the levels
    between full resolution and the overview are written there as tiles."""
    t, h, w = intensity.shape
    n_levels = max(0, math.ceil(math.log2(max(h, w) / max_size))) if max(h, w) > max_size else 0
    f = 2**n_levels
    stride = max(1, math.ceil((h // f) * (w // f) * t / 1e6 / max_megapixels))
    frames = np.arange(0, t, stride)

    tau = lifetime[frames].astype(np.float32)
    tau[~np.isfinite(tau) | (tau == 0)] = np.nan
    tau = _nan_box(tau, smooth_xy, smooth_t / stride)
    inten = intensity[frames].astype(np.float32)
    proj = projection.astype(np.float32)
    step = max(1, int(math.sqrt(h * w / 1e6)))
    dmin, dmax = display_range
    span = dmax - dmin
    p = _percentiles(tau, [0.5, 99.5], step)
    lo, hi = (min(dmin - 0.25 * span, p[0]), max(dmax + 0.25 * span, p[1])) if p is not None else (dmin, dmax)
    ilo, ihi = _percentiles(inten, [0.2, 99.8], step) if _percentiles(inten, [50], step) is not None else (0, 1)
    plo, phi = _percentiles(proj, [0.2, 99.8], step) if _percentiles(proj, [50], step) is not None else (0, 1)
    lab = labels.astype(np.int32)

    tiles: dict = {}
    for level in range(n_levels):
        if tiles_dir is not None:
            meta = _write_level(Path(tiles_dir), level, tau, inten, proj, lab, (lo, hi), (ilo, ihi), (plo, phi))
            tiles.setdefault("levels", []).append(meta)
        hh, ww = lab.shape[0] // 2 * 2, lab.shape[1] // 2 * 2
        tau, inten, proj, lab = _half(tau), _half(inten), _half(proj[np.newaxis])[0], lab[:hh:2, :ww:2]
    if tiles:
        tiles |= {"tile": TILE, "path": Path(tiles_dir).name}
    return ViewerData(
        lifetime8=_to8(tau, lo, hi, True),
        intensity8=_to8(inten, ilo, ihi, False),
        projection8=_to8(proj, plo, phi, False),
        labels=lab,
        frames=frames,
        factor=f,
        lo=float(lo),
        hi=float(hi),
        tiles=tiles,
    )


def _write_level(tiles_dir: Path, level: int, tau, inten, proj, lab, trange, irange, prange) -> dict:
    d = tiles_dir / f"L{level}"
    d.mkdir(parents=True, exist_ok=True)
    nf, h, w = tau.shape
    ny, nx = math.ceil(h / TILE), math.ceil(w / TILE)
    tau8, int8, proj8 = _to8(tau, *trange, True), _to8(inten, *irange, False), _to8(proj, *prange, False)
    jobs = []
    for ty in range(ny):
        for tx in range(nx):
            sl = (slice(ty * TILE, (ty + 1) * TILE), slice(tx * TILE, (tx + 1) * TILE))
            jobs.append((d / f"lab_{ty}_{tx}.js", f"L{level}/lab_{ty}_{tx}", _label_rgb(lab[sl])))
            jobs.append((d / f"p_{ty}_{tx}.js", f"L{level}/p_{ty}_{tx}", proj8[sl]))
            for fi in range(nf):
                r, g = tau8[fi][sl], int8[fi][sl]
                jobs.append((d / f"t{fi}_{ty}_{tx}.js", f"L{level}/t{fi}_{ty}_{tx}", np.dstack([r, g, np.zeros_like(r)])))
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda job: job[0].write_text(f'FHTile("{job[1]}","{png_data_url(job[2])}");', encoding="ascii"), jobs))
    log.info("Viewer tiles: level %d, %d x %d tiles x %d frames", level, nx, ny, nf)
    return {"level": level, "factor": 2**level, "width": w, "height": h, "nx": nx, "ny": ny}


def _label_rgb(labels: np.ndarray) -> np.ndarray:
    lab = labels.astype(np.uint32)
    return np.dstack([lab & 255, (lab >> 8) & 255, (lab >> 16) & 255]).astype(np.uint8)


def png_data_url(arr: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", compress_level=6)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def frame_urls(v: ViewerData) -> list[str]:
    """One RGB PNG per frame: R = lifetime code, G = intensity, B = 0."""
    zeros = np.zeros_like(v.lifetime8[0])
    return [png_data_url(np.dstack([v.lifetime8[i], v.intensity8[i], zeros])) for i in range(len(v.frames))]


def labels_url(labels: np.ndarray) -> str:
    """Label image as RGB PNG: id = R + 256 G + 65536 B."""
    return png_data_url(_label_rgb(labels))


def float_b64(arr: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(arr, dtype="<f4").tobytes()).decode("ascii")
