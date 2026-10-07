"""Synthetic 2-component TCSPC time-lapses with known ground truth, for tests and demos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

from .io import ImageData, write_tiff


@dataclass
class Truth:
    labels: np.ndarray
    lifetimes: np.ndarray  # (T, N) true weighted lifetime per cell
    stimulation: int
    calibration: int
    responders: np.ndarray  # (N,) bool
    additional: np.ndarray  # (N,) mean intensity in the additional channel


def make_timelapse(
    size: int = 256,
    n_frames: int = 60,
    stimulation: int = 15,
    calibration: int = 45,
    cell_radius: float = 9.0,
    tau1: float = 0.6,
    tau2: float = 3.4,
    photons: float = 40.0,
    responder_fraction: float = 0.5,
    drift: float = 0.0,
    seed: int = 0,
    pixel_size: float = 0.5,
    frame_interval: float = 5.0,
) -> tuple[ImageData, Truth]:
    """Cells on a jittered grid. Lifetime: baseline ~2.5 ns, responders rise ~0.4 ns after stimulation
    (some slowly), calibration to ~3.2 ns for all. Channels: A1, A2 (amplitudes), additional channel."""
    rng = np.random.default_rng(seed)
    spacing = int(cell_radius * 2.6)
    yy, xx = np.mgrid[0:size, 0:size]
    labels = np.zeros((size, size), np.int32)
    profile = np.zeros((size, size), np.float32)
    n = 0
    for cy in range(spacing // 2, size - spacing // 2, spacing):
        for cx in range(spacing // 2, size - spacing // 2, spacing):
            if rng.random() < 0.15:
                continue
            y0, x0 = cy + rng.normal(0, 2), cx + rng.normal(0, 2)
            a, b = cell_radius * rng.uniform(0.8, 1.2), cell_radius * rng.uniform(0.7, 1.1)
            th = rng.uniform(0, np.pi)
            u = (xx - x0) * np.cos(th) + (yy - y0) * np.sin(th)
            v = -(xx - x0) * np.sin(th) + (yy - y0) * np.cos(th)
            r2 = (u / a) ** 2 + (v / b) ** 2
            inside = (r2 <= 1) & (labels == 0)
            n += 1
            labels[inside] = n
            profile[inside] = (1.2 - 0.5 * r2[inside]) * rng.uniform(0.5, 1.5)
    t = np.arange(n_frames)[:, None]
    base = rng.normal(2.5, 0.05, n)
    responders = rng.random(n) < responder_fraction
    amplitude = np.where(responders, rng.normal(0.4, 0.08, n), rng.normal(0.03, 0.02, n))
    rate = np.where(rng.random(n) < 0.3, 0.08, 0.6)  # some slow responders
    rise = np.clip(t - stimulation + 1, 0, None)
    lifetimes = base + amplitude * (1 - np.exp(-rate * rise))
    lifetimes = np.where(t >= calibration, rng.normal(3.2, 0.03, n), lifetimes).astype(np.float32)

    tau_map = np.zeros((n_frames, size, size), np.float32)
    lut = np.concatenate([[0], np.arange(n)])
    for f in range(n_frames):
        tau_map[f] = np.where(labels > 0, lifetimes[f][lut[labels]], 0)
    brightness = photons * profile[None] + 0.5  # background
    frac2 = np.clip((tau_map - tau1) / (tau2 - tau1), 0, 1)
    tau_eff = np.where(labels > 0, tau_map, 2.0)
    total_amp = brightness / tau_eff
    a2 = rng.poisson(total_amp * np.where(labels > 0, frac2, 0.5)).astype(np.float32)
    a1 = rng.poisson(total_amp * np.where(labels > 0, 1 - frac2, 0.5)).astype(np.float32)
    additional_level = np.where(rng.random(n) < 0.3, 200.0, 20.0) * rng.uniform(0.7, 1.3, n)
    add = np.where(labels > 0, additional_level[lut[labels]], 2.0)[None].repeat(n_frames, 0)
    add = rng.poisson(add).astype(np.float32)
    data = np.stack([a1, a2, add], axis=1)
    if drift:
        for f in range(n_frames):
            data[f] = ndi.shift(data[f], (0, drift * f, -drift * f / 2), order=0)
    image = ImageData(data, "synthetic", Path("synthetic.tif"), pixel_size, frame_interval)
    return image, Truth(labels, lifetimes, stimulation, calibration, responders, additional_level)


def save_tiff(image: ImageData, path: Path, info: str | None = None) -> Path:
    write_tiff(path, image.data, "TCYX", image.pixel_size, image.frame_interval, info)
    return path
