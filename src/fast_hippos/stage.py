"""Stage geometry: tile layout, absolute cell positions, hit path optimization and Leica .rgn files.

Stage positions are (n, 2) arrays of (X, Y) in metres, as read from the .lif metadata.
Conversion to the coordinate frame of the .rgn file swaps and negates the axes (as in the Fiji macro,
validated on the Leica Stellaris stage):

    abs_x = -stage_Y - tile_width/2  + x_px * pixel_size
    abs_y = -stage_X - tile_height/2 + y_px * pixel_size
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from skimage import morphology

log = logging.getLogger(__name__)


@dataclass
class StageInfo:
    positions: np.ndarray  # (n_tiles, 2) X, Y in m
    n_tiles: tuple[int, int]  # (nx, ny)
    tile_size: tuple[float, float] | None = None  # (w, h) in m
    overlap: float = 0.0  # fraction

    @property
    def origin_tile(self) -> int:
        """Tile whose top-left corner is the image origin of a stitched image (scanning right-to-left
        when the overlap is negative)."""
        return self.n_tiles[0] - 1 if self.overlap < 0 else 0


def parse_stitched_info(info: str) -> StageInfo | None:
    """Parse the metadata block written by Stitch_tiles.ijm into the ImageJ 'Info' field."""
    lines = [ln.strip() for ln in info.splitlines()]
    if not lines or lines[0] != "Stitched image with tile layout:":
        return None
    nx, ny = (int(float(v)) for v in lines[1].split(","))
    positions = np.empty((0, 2))
    tile_size = None
    overlap = 0.0
    for key, value in zip(lines[2::2], lines[3::2], strict=False):
        if key == "Stage coordinates:":
            positions = np.array([float(v) for v in value.split(",")]).reshape(-1, 2)
        elif key == "Tile size (um):":
            w, h = (float(v) * 1e-6 for v in value.split(","))
            tile_size = (w, h)
        elif key == "overlap (%):":
            overlap = float(value) / 100
    return StageInfo(positions, (nx, ny), tile_size, overlap)


def stitched_info_block(stage: StageInfo) -> str:
    """Inverse of parse_stitched_info (used to keep the metadata on the saved labelmap)."""
    coords = ",".join(f"{v:.10g}" for v in stage.positions.ravel())
    text = f"Stitched image with tile layout:\n{stage.n_tiles[0]},{stage.n_tiles[1]}\nStage coordinates:\n{coords}\n"
    if stage.tile_size:
        text += f"Tile size (um):\n{stage.tile_size[0] * 1e6:.6g},{stage.tile_size[1] * 1e6:.6g}\n"
    text += f"overlap (%):\n{stage.overlap * 100:.6g}\n"
    return text


def read_positions_file(path: Path, n: int | None = None) -> np.ndarray:
    """Stage positions from a .lif file or a text file with x0, y0, x1, y1, ... (m; commas/newlines/tabs)."""
    if path.suffix.lower() == ".lif":
        from .io import lif_stage_positions

        return lif_stage_positions(path, n)
    values = [float(v) for v in path.read_text().replace(",", " ").split()]
    positions = np.array(values).reshape(-1, 2)
    return positions[:n] if n else positions


def tile_layout(positions: np.ndarray) -> tuple[int, int]:
    """(nx, ny) from the number of distinct stage positions. Image x runs along stage Y (see module doc)."""
    nx = len(np.unique(positions[:, 1]))
    ny = len(np.unique(positions[:, 0]))
    return nx, ny


def tile_size_from_image(width: int, height: int, pixel_size_um: float, n_tiles: tuple[int, int], overlap: float):
    nx, ny = n_tiles
    w = width / (nx - (nx - 1) * overlap) * pixel_size_um * 1e-6
    h = height / (ny - (ny - 1) * overlap) * pixel_size_um * 1e-6
    return w, h


def absolute_positions(xy_px: np.ndarray, stage_xy: np.ndarray, tile_size, pixel_size_um: float) -> np.ndarray:
    """(n, 2) pixel positions (x, y) within a tile/image -> (n, 2) absolute .rgn coordinates in m."""
    w, h = tile_size
    abs_x = -stage_xy[1] - w / 2 + xy_px[:, 0] * pixel_size_um * 1e-6
    abs_y = -stage_xy[0] - h / 2 + xy_px[:, 1] * pixel_size_um * 1e-6
    return np.column_stack([abs_x, abs_y])


def erode_labels(labels: np.ndarray, radius: int) -> np.ndarray:
    """Shrink every label by `radius` pixels, keeping label ids (labels that vanish are simply absent)."""
    out = labels.copy()
    for _ in range(radius):
        boundary = (
            (ndi.grey_erosion(out, size=3) != out) | (ndi.grey_dilation(out, size=3) != out)
        )
        out[boundary] = 0
    return out


def refined_positions(
    labels: np.ndarray, probability: np.ndarray, centroids_xy: np.ndarray, erosion: int = 2
) -> np.ndarray:
    """Probability-weighted centre of mass per cell inside the eroded label (centroid as fallback).

    As in the Fiji v0.9.5 Labkit step: p < 0.5 -> 0, opening with a disk of radius 1, then squared.
    Results are indexed by label id, so labels that vanish after erosion do not shift the others (issue I14).
    """
    p = np.where(probability >= 0.5, probability, 0).astype(np.float64)
    p = morphology.opening(p, morphology.disk(1)) ** 2
    eroded = erode_labels(labels, erosion)
    n = int(labels.max())
    idx = np.arange(1, n + 1)
    mass = ndi.sum_labels(p, eroded, idx)
    with np.errstate(invalid="ignore"):
        com = np.array(ndi.center_of_mass(p, eroded, idx), dtype=float).reshape(-1, 2)  # (y, x)
    out = centroids_xy.astype(float).copy()
    ok = (mass > 0) & np.isfinite(com).all(axis=1)
    out[ok] = com[ok][:, ::-1]
    log.info("Position refinement: %d of %d cells refined (rest: centroid)", ok.sum(), n)
    return out


# ---------------------------------------------------------------- path optimization


def nearest_neighbour_path(points: np.ndarray) -> np.ndarray:
    n = len(points)
    if n == 0:
        return np.array([], dtype=int)
    order = np.empty(n, dtype=int)
    visited = np.zeros(n, dtype=bool)
    current = int(np.argmin((points**2).sum(axis=1)))  # start closest to (0, 0)
    for k in range(n):
        order[k] = current
        visited[current] = True
        if k == n - 1:
            break
        d = ((points - points[current]) ** 2).sum(axis=1)
        d[visited] = np.inf
        current = int(np.argmin(d))
    return order


def path_length(points: np.ndarray, order: np.ndarray) -> float:
    p = points[order]
    return float(np.sqrt(((p[1:] - p[:-1]) ** 2).sum(axis=1)).sum())


def two_opt(points: np.ndarray, order: np.ndarray, max_time: float = 5.0, max_iterations: int = 100000) -> np.ndarray:
    """Improve an open path with 2-opt moves (longest segments first) until no move helps or time runs out."""
    order = order.copy()
    n = len(order)
    if n < 4:
        return order
    start = time.perf_counter()
    for _ in range(max_iterations):
        if time.perf_counter() - start > max_time:
            log.info("2-opt: time limit reached")
            break
        p = points[order]
        seg = np.sqrt(((p[1:] - p[:-1]) ** 2).sum(axis=1))  # seg[i] = |p[i] - p[i+1]|
        improved = False
        for i in np.argsort(seg)[::-1]:
            j = np.arange(n - 1)
            cur = seg[i] + seg[j]
            new = np.sqrt(((p[i] - p[j]) ** 2).sum(axis=1)) + np.sqrt(((p[i + 1] - p[j + 1]) ** 2).sum(axis=1))
            gain = cur - new
            gain[np.abs(j - i) < 2] = 0
            best = int(np.argmax(gain))
            if gain[best] > 1e-12:
                a, b = sorted((i, best))
                order[a + 1 : b + 1] = order[a + 1 : b + 1][::-1]
                improved = True
                break
        if not improved:
            break
    return order


def optimize_path(points: np.ndarray, max_time: float = 5.0) -> np.ndarray:
    """Visiting order of the points: nearest neighbour from the point closest to (0, 0), then 2-opt."""
    order = nearest_neighbour_path(points)
    length_nn = path_length(points, order)
    order = two_opt(points, order, max_time)
    if length_nn > 0:
        log.info(
            "Path optimization: %d points, %.1f mm (%.1f %% shorter than nearest neighbour)",
            len(points), 1e3 * path_length(points, order), 100 * (1 - path_length(points, order) / length_nn),
        )
    return order


# ---------------------------------------------------------------- .rgn


def write_rgn(path: Path, positions_m: np.ndarray) -> None:
    """Leica LAS X StageOverviewRegions file with one point per position (metres)."""
    items, stack = [], []
    for i, (x, y) in enumerate(positions_m):
        uid = str(uuid.uuid4())
        items.append(
            f"<Item{i}>\n<Number>{i + 1}</Number>\n<Tag>Cell_{i + 1}</Tag>\n<Identifier>{uid}</Identifier>\n"
            "<Type>Point</Type>\n<Fill>R:1,G:0,B:0,A:0</Fill>\n<Font />\n<Verticies>\n<Items>\n<Item0>\n"
            f"<X>{x:.10f}</X>\n<Y>{y:.10f}</Y>\n"
            "</Item0>\n</Items>\n</Verticies>\n<DecoratorColors>\n<Items />\n</DecoratorColors>\n"
            f"<ExtendedProperties>\n<Items />\n</ExtendedProperties>\n</Item{i}>\n"
        )
        stack.append(
            f'<Entry Identifier="{uid}" Begin="0.0000000000" End="0.0000000000" SectionCount="0" '
            'ReferenceX="0.0000000000" ReferenceY="0.0000000000" FocusStabilizerOffset="0.0000000000" '
            'FocusStabilizerOffsetFixed="false" StackValid="false" Marked="false" />\n'
        )
    text = (
        "<StageOverviewRegions>\n<Regions>\n<ShapeList>\n<Items>\n<Item0>\n<Name>hits</Name>\n"
        f"<Identifier>{uuid.uuid4()}</Identifier>\n<Type>CompoundShape</Type>\n<Font />\n<Verticies>\n<Items />\n"
        "</Verticies>\n<DecoratorColors>\n<Items />\n</DecoratorColors>\n<ExtendedProperties>\n<Items />\n"
        "</ExtendedProperties>\n<Children>\n<Items>\n"
        + "".join(items)
        + "</Items>\n</Children>\n</Item0>\n</Items>\n<FillMaskMode>None</FillMaskMode>\n"
        "<VertexUnitMode>Pixels</VertexUnitMode>\n</ShapeList>\n</Regions>\n<StackList>\n"
        + "".join(stack)
        + "</StackList>\n</StageOverviewRegions>\n"
    )
    path.write_text(text, encoding="utf-8")
