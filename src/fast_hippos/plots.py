"""Static PNG figures (for reports; the interactive views are in the HTML dashboard)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .events import Events


def traces(
    path: Path,
    kymo: np.ndarray,
    frame_interval: float,
    events: Events,
    ylabel: str,
    ylim: tuple[float, float] | None,
    hits: np.ndarray | None = None,
    title: str = "",
) -> None:
    t = np.arange(kymo.shape[0]) * frame_interval
    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=120)
    n = kymo.shape[1]
    colors = plt.get_cmap("hsv")(np.linspace(0, 1, max(n, 1), endpoint=False))
    alpha = 0.6 if n < 200 else 0.25
    for i in range(n):
        if hits is not None and hits[i]:
            continue
        ax.plot(t, kymo[:, i], lw=0.6, color="0.7" if hits is not None else colors[i], alpha=alpha)
    if hits is not None:
        for i in np.flatnonzero(hits):
            ax.plot(t, kymo[:, i], lw=0.9, color="#c0389a", alpha=0.8)
    with np.errstate(invalid="ignore"):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            ax.plot(t, np.nanmean(kymo, axis=1), color="black", lw=2.5, label="mean")
    for name, sl, color in (("baseline", events.baseline, "#3366cc"), ("response", events.response, "#cc6633")):
        if sl.stop > sl.start and not (name == "baseline" and events.baseline_only):
            ax.axvspan(sl.start * frame_interval, (sl.stop - 1) * frame_interval, color=color, alpha=0.08, lw=0)
    for frame, label in ((events.stimulation, "stimulation"), (events.calibration, "calibration")):
        if frame is not None:
            ax.axvline(frame * frame_interval, color="0.3", ls="--", lw=1)
            ax.text(frame * frame_interval, 1.01, label, transform=ax.get_xaxis_transform(), ha="center", fontsize=8)
    ax.set_xlabel("time (s)")
    ax.set_ylabel(ylabel)
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_xlim(t[0], t[-1] if len(t) > 1 else 1)
    ax.grid(alpha=0.3)
    suffix = f", {int(hits.sum())} hits" if hits is not None else ""
    ax.set_title(f"{title}  ({n} cells{suffix})", fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def hit_positions(path: Path, chunks: list[pd.DataFrame], tiles: list[tuple[float, float, float, float]]) -> None:
    """Hit map in mm, y pointing up (plotted as -abs_y, as in the Fiji macro).

    ``tiles``: (x0, y0, width, height) in m, in the same (abs) frame as the hit positions.
    """
    fig, ax = plt.subplots(figsize=(7, 7), dpi=120)
    for x0, y0, w, h in tiles:
        ax.add_patch(plt.Rectangle((x0 * 1e3, -(y0 + h) * 1e3), w * 1e3, h * 1e3, fill=False, ec="0.6", lw=1))
    colors = plt.get_cmap("tab10")
    for k, chunk in enumerate(chunks):
        ax.plot(
            chunk["abs_x_m"] * 1e3, -chunk["abs_y_m"] * 1e3, "-o", ms=3, lw=0.6, color=colors(k % 10),
            label=f"hits {chunk['rank'].min()}-{chunk['rank'].max()}",
        )
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_aspect("equal")
    ax.autoscale_view()
    if chunks:
        ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
