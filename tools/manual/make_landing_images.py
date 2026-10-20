"""Images of the home page of the manual, from the example run (example_run in the example folder; see
make_example_data.py): the lifetime movie of a part of example_screen_1, in which the hits are outlined once the
response is in, as one WebP per frame in manual/images/landing (the size of the image; the page scales it up), with
movie.json (timing, labels, colour range) and colorbar.png for the player of the home page (manual/assets/manual.js),
which writes the label and the colour scale as text over the frames, so that they stay sharp; and a close-up of the
screenshot experiment.png (screenshots.py) for the card of the experiment overview.

    python tools/manual/make_landing_images.py [C:/PythonProjects/FAST-HIPPOS/data/manual]

The colours are made as the dashboard makes them (colour = lifetime through the colour scale, brightness =
intensity), with the default spatial smoothing (3 x 3 px) and a time smoothing of ± 2 frames.
"""

import base64
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage as ndi

from fast_hippos.dashboard import _luts
from fast_hippos.viewer_data import ViewerData

OUT = Path(__file__).resolve().parents[2] / "manual" / "images"
DEFAULT_EXAMPLE = Path("C:/PythonProjects/FAST-HIPPOS/data/manual")
W, H = 480, 300  # the part of the image shown (pixels of the image)
BRIGHT = 10 ** 0.45
REVEAL = 12  # the hits are outlined from this frame on (the response is in by then)


def smoothed(codes: np.ndarray, rxy: int, rt: int) -> np.ndarray:
    """The NaN-aware mean of the dashboard (viewer.js smoothCodes) over a (2 rt + 1, 2 rxy + 1, 2 rxy + 1) box."""
    v = codes.astype(np.float32)
    have = (codes > 0).astype(np.float32)
    size = (2 * rt + 1, 2 * rxy + 1, 2 * rxy + 1)
    s, c = ndi.uniform_filter(v, size, mode="nearest"), ndi.uniform_filter(have, size, mode="nearest")
    out = np.where(c > 0, s / np.maximum(c, 1e-9), 0)
    out[(c <= 0.2) | ((codes == 0) & (c <= 0.5))] = 0
    return np.round(out).astype(np.uint8)


def colour(codes, inten, v: ViewerData, dmin: float, dmax: float, lut: np.ndarray) -> np.ndarray:
    val = v.lo + (codes.astype(np.float32) - 1) / 254 * (v.hi - v.lo)
    k = np.clip(np.round((val - dmin) / (dmax - dmin) * 255), 0, 255).astype(int)
    g = np.minimum(1, inten.astype(np.float32) / 255 * BRIGHT)[..., None]
    rgb = lut[k] * g
    grey = np.repeat(g * 140, 3, -1)
    rgb[codes == 0] = grey[codes == 0]
    return rgb.clip(0, 255).astype(np.uint8)


def best_window(hits: pd.DataFrame, shape) -> tuple[int, int]:
    """The top-left corner of the W x H window with the most hits (away from the edges)."""
    best, corner = -1, (0, 0)
    for y in range(0, shape[0] - H, 20):
        for x in range(0, shape[1] - W, 20):
            n = ((hits.centroid_x > x + 20) & (hits.centroid_x < x + W - 20) & (hits.centroid_y > y + 20)
                 & (hits.centroid_y < y + H - 20)).sum()
            if n > best:
                best, corner = n, (y, x)
    return corner


def main(example: Path) -> None:
    run = example / "example_run" / "example_screen_1"
    v = ViewerData.load(run / "viewer.npz")
    assert v.factor == 1 and v.smoothed_xy == 0, "needs a run made with the current version (full resolution, unsmoothed)"
    settings = json.loads((example / "example_run" / "settings_used.json").read_text())
    dmin, dmax = settings["display"]["min_lifetime"], settings["display"]["max_lifetime"]
    lut = np.frombuffer(base64.b64decode(_luts()[settings["display"].get("lut") or "turbo"]), np.uint8).reshape(256, 3)
    events = json.loads((run / "events.json").read_text())
    cells = pd.read_csv(run / "cells.tsv", sep="\t")
    hits = cells[cells.hit.astype(bool)]
    y0, x0 = best_window(hits, v.labels.shape)
    sl = (slice(y0, y0 + H), slice(x0, x0 + W))
    lab = v.labels[sl]
    hit_labels = np.isin(lab, hits.cell.to_numpy())
    edge = hit_labels & (ndi.grey_erosion(np.where(hit_labels, lab, 0), size=3) != lab)
    codes = smoothed(v.lifetime8, 1, 2)
    movie = OUT / "landing"
    movie.mkdir(exist_ok=True)
    for old in movie.glob("f*.webp"):
        old.unlink()
    labels, size = [], 0
    stim, cal = events.get("stimulation"), events.get("calibration")
    for f in range(len(v.frames)):
        rgb = colour(codes[f][sl], v.intensity8[f][sl], v, dmin, dmax, lut)
        t = int(v.frames[f])
        if t >= REVEAL:
            rgb[edge] = (255, 79, 176)
        Image.fromarray(rgb).save(movie / f"f{f:02d}.webp", quality=76, method=6)
        size += (movie / f"f{f:02d}.webp").stat().st_size
        labels.append("baseline" if stim is None or t < stim else "hits found" if t >= REVEAL and (cal is None or t < cal)
                      else "stimulated" if cal is None or t < cal else "calibration")
    durations = [700 if (stim is not None and int(t) == stim) else 1200 if int(t) == REVEAL else 230 for t in v.frames]
    durations[-1] = 1600
    Image.fromarray(lut[None, :, :]).save(movie / "colorbar.png")
    n = len(v.frames)
    (movie / "movie.json").write_text(json.dumps({
        "n": n, "frames": [int(t) for t in v.frames], "durations": durations, "labels": labels,
        "stimulation": stim, "calibration": cal, "reveal": REVEAL, "min": dmin, "max": dmax, "unit": "Lifetime (ns)",
        "still": next((k for k, t in enumerate(v.frames) if t >= REVEAL + 4), n - 1),  # without animation: hits found
    }, indent=1))
    print(f"landing/: {n} frames, {size // 1024} kB,",
          f"{len(hits[(hits.centroid_x > x0) & (hits.centroid_x < x0 + W) & (hits.centroid_y > y0) & (hits.centroid_y < y0 + H)])} hits")


def experiment_closeup() -> None:
    """The images table and the response of the experiment overview, large enough for a card on the home page."""
    im = Image.open(OUT / "experiment.png")
    w = round(im.width * 0.52)
    im.crop((0, 0, w, round(w * 10 / 16))).save(OUT / "landing_experiment.png", optimize=True)
    print("landing_experiment.png")


if __name__ == "__main__":
    experiment_closeup()
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXAMPLE)
