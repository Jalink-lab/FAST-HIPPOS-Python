"""Per-modality conversion of raw channels to an intensity stack and a lifetime (or ratio) stack.

All functions return ``(intensity, lifetime)`` as float32 (T, Y, X) arrays. Pixels without a valid
lifetime are NaN (the Fiji macro used 0 for TCSPC and NaN for ratio/intensity; NaN is used throughout here).
"""

from __future__ import annotations

import numpy as np

from .config import FDFLIMSettings, InputSettings, Modality
from .io import ImageData

UNITS = {
    Modality.TCSPC: "Lifetime (ns)",
    Modality.FAST_FLIM: "Lifetime (ns)",
    Modality.TAU_CONTRAST: "Lifetime (ns)",
    Modality.FD_FLIM: "Lifetime (ns)",
    Modality.RATIO: "Ratio (ch1 / ch2)",
    Modality.INTENSITY: "Intensity",
}


def compute(image: ImageData, settings: InputSettings, fd: FDFLIMSettings | None = None):
    m = settings.modality
    c = settings.intensity_channel
    if m == Modality.TCSPC:
        return tcspc(image.channel(c), image.channel(c + 1), settings.tau1, settings.tau2)
    if m == Modality.TAU_CONTRAST:
        return tau_contrast(image.channel(c), image.channel(c + 1))
    if m == Modality.FAST_FLIM:
        return fast_flim(image.channel(c), image.channel(c + 1))
    if m == Modality.RATIO:
        return ratio(image.channel(c), image.channel(c + 1))
    if m == Modality.INTENSITY:
        return intensity_only(image.channel(c))
    if m == Modality.FD_FLIM:
        if fd is None or fd.reference is None:
            raise ValueError("FD-FLIM requires [fdflim] reference, phases, frequency_mhz and tau_ref")
        from .io import iter_images

        reference = next(iter_images(fd.reference)).channel(1)
        background = next(iter_images(fd.background)).channel(1) if fd.background else None
        return fd_flim(image.channel(c), reference, fd.phases, fd.frequency_mhz, fd.tau_ref, fd.lifetime_from, background)
    raise ValueError(f"Unknown modality {m}")


def tcspc(a1: np.ndarray, a2: np.ndarray, tau1: float, tau2: float):
    """Two fitted component amplitudes -> intensity A1*tau1 + A2*tau2 and amplitude-weighted lifetime."""
    a1 = a1.astype(np.float32)
    a2 = a2.astype(np.float32)
    intensity = a1 * tau1 + a2 * tau2
    amp = a1 + a2
    with np.errstate(divide="ignore", invalid="ignore"):
        lifetime = np.where(amp != 0, intensity / amp, np.nan).astype(np.float32)
    return intensity, lifetime


def tau_contrast(intensity: np.ndarray, coded: np.ndarray):
    """LAS X TauContrast: 8-bit lifetime code 0..255 -> -1..~23.7 ns."""
    lifetime = coded.astype(np.float32) * 0.097 - 1.0
    lifetime[coded == 0] = np.nan
    return intensity.astype(np.float32), lifetime


def fast_flim(intensity: np.ndarray, lifetime_ps: np.ndarray):
    lifetime = lifetime_ps.astype(np.float32) * 1e-3
    lifetime[lifetime_ps == 0] = np.nan
    return intensity.astype(np.float32), lifetime


def ratio(c1: np.ndarray, c2: np.ndarray):
    c1 = c1.astype(np.float32)
    c2 = c2.astype(np.float32)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where((c1 > 0) & (c2 > 0), c1 / c2, np.nan).astype(np.float32)
    return c1 + c2, r


def intensity_only(img: np.ndarray):
    img = img.astype(np.float32)
    return img, np.where(img > 0, img, np.nan).astype(np.float32)


def phase_modulation(stack: np.ndarray, phases: int):
    """First-harmonic phase delay (rad) and modulation of a (..., P, Y, X) phase stack."""
    k = np.arange(phases)
    w = np.exp(-2j * np.pi * k / phases).reshape((phases, 1, 1))
    f1 = (stack * w).sum(axis=-3)
    dc = stack.sum(axis=-3)
    with np.errstate(divide="ignore", invalid="ignore"):
        mod = 2 * np.abs(f1) / dc
    return -np.angle(f1), mod, dc / phases


def fd_flim(
    stack: np.ndarray,
    reference: np.ndarray,
    phases: int,
    frequency_mhz: float,
    tau_ref: float,
    lifetime_from: str = "phase",
    background: np.ndarray | None = None,
):
    """Frequency-domain FLIM. ``stack`` is (T*P, Y, X) with the phases of each time point consecutive.

    The reference (P, Y, X) of known lifetime ``tau_ref`` calibrates the instrument phase and modulation.
    Returns intensity (DC) and the phase or modulation lifetime in ns.
    """
    if stack.shape[0] % phases:
        raise ValueError(f"Number of frames ({stack.shape[0]}) is not a multiple of phases ({phases})")
    stack = stack.astype(np.float64)
    reference = reference.astype(np.float64)
    if background is not None:
        bg = background.astype(np.float64).mean(axis=0) if background.ndim == 3 else background
        stack = stack - bg
        reference = reference - bg
    stack = stack.reshape((-1, phases) + stack.shape[1:])
    omega = 2 * np.pi * frequency_mhz * 1e6 * 1e-9  # rad/ns
    phi_ref, mod_ref, _ = phase_modulation(reference[:phases], phases)
    phi_ref_true = np.arctan(omega * tau_ref)
    mod_ref_true = 1 / np.sqrt(1 + (omega * tau_ref) ** 2)
    phi, mod, dc = phase_modulation(stack, phases)
    phi = phi - (phi_ref - phi_ref_true)
    with np.errstate(divide="ignore", invalid="ignore"):
        mod = mod / (mod_ref / mod_ref_true)
        if lifetime_from == "phase":
            tau = np.tan(phi) / omega
        elif lifetime_from == "modulation":
            tau = np.sqrt(1 / mod**2 - 1) / omega
        else:
            raise ValueError("lifetime_from must be 'phase' or 'modulation'")
    tau = np.where(np.isfinite(tau) & (dc > 0), tau, np.nan)
    return dc.astype(np.float32), tau.astype(np.float32)
