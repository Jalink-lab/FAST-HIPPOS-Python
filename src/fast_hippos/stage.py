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
    # Written by the Python stitching only (lines after the Fiji ones, which Fiji ignores):
    origin: tuple[float, float] | None = None  # stage (X, Y) in m whose tile corner is the image origin
    bidirectional: float | None = None  # px, bidirectional phase correction already applied per tile

    @property
    def origin_tile(self) -> int:
        """Tile whose top-left corner is the image origin of a stitched image (scanning right-to-left
        when the overlap is negative)."""
        return self.n_tiles[0] - 1 if self.overlap < 0 else 0

    @property
    def origin_xy(self) -> tuple[float, float]:
        """Stage (X, Y) in m of the image origin: given by the Python stitching, else that of the origin tile."""
        return self.origin if self.origin is not None else tuple(self.positions[self.origin_tile])


def parse_stitched_info(info: str) -> StageInfo | None:
    """Parse the metadata block written by Stitch_tiles.ijm into the ImageJ 'Info' field."""
    lines = [ln.strip() for ln in info.splitlines()]
    if not lines or lines[0] != "Stitched image with tile layout:":
        return None
    nx, ny = (int(float(v)) for v in lines[1].split(","))
    positions = np.empty((0, 2))
    tile_size = None
    overlap = 0.0
    origin = bidirectional = None
    for key, value in zip(lines[2::2], lines[3::2], strict=False):
        if key == "Stage coordinates:":
            positions = np.array([float(v) for v in value.split(",")]).reshape(-1, 2)
        elif key == "Tile size (um):":
            w, h = (float(v) * 1e-6 for v in value.split(","))
            tile_size = (w, h)
        elif key == "overlap (%):":
            overlap = float(value) / 100
        elif key == ORIGIN_KEY:
            x, y = (float(v) for v in value.split(","))
            origin = (x, y)
        elif key == BIDIRECTIONAL_KEY:
            bidirectional = float(value)
    return StageInfo(positions, (nx, ny), tile_size, overlap, origin, bidirectional)


ORIGIN_KEY = "Image origin (stage coordinates):"
BIDIRECTIONAL_KEY = "Bidirectional correction per tile (px):"


def stitched_info_block(stage: StageInfo) -> str:
    """Inverse of parse_stitched_info (used to keep the metadata on the saved labelmap). The Fiji lines come first
    and in the Fiji order (the macro reads them by line number); the Python-only lines follow."""
    coords = ",".join(f"{v:.10g}" for v in stage.positions.ravel())
    text = f"Stitched image with tile layout:\n{stage.n_tiles[0]},{stage.n_tiles[1]}\nStage coordinates:\n{coords}\n"
    if stage.tile_size:
        text += f"Tile size (um):\n{stage.tile_size[0] * 1e6:.6g},{stage.tile_size[1] * 1e6:.6g}\n"
    text += f"overlap (%):\n{stage.overlap * 100:.6g}\n"
    if stage.origin is not None:
        text += f"{ORIGIN_KEY}\n{stage.origin[0]:.10g},{stage.origin[1]:.10g}\n"
    if stage.bidirectional is not None:
        text += f"{BIDIRECTIONAL_KEY}\n{stage.bidirectional:.4g}\n"
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


def nearest_neighbour_path(points: np.ndarray, start: np.ndarray | None = None) -> np.ndarray:
    """Greedy route: from the point closest to `start` (default: stage origin (0, 0)), always to the nearest
    unvisited point."""
    n = len(points)
    if n == 0:
        return np.array([], dtype=int)
    origin = np.zeros(points.shape[1]) if start is None else np.asarray(start, dtype=float)
    order = np.empty(n, dtype=int)
    visited = np.zeros(n, dtype=bool)
    current = int(np.argmin(((points - origin) ** 2).sum(axis=1)))
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


def _neighbour_lists(points: np.ndarray, k: int) -> list[list[int]]:
    """For every point the indices of its k nearest other points, nearest first (the point itself excluded, also
    when another point lies at exactly the same place)."""
    from scipy.spatial import cKDTree

    n = len(points)
    k = min(k, n - 1)
    # candidates from the k-d tree, then ordered exactly as the dashboard does (squared distance as dx^2 + dy^2,
    # equal distances by index), so that both give the same routes, also for positions on a pixel grid (many ties)
    idx = cKDTree(points).query(points, min(k + 9, n))[1].tolist()
    xs, ys = points[:, 0].astype(float).tolist(), points[:, 1].astype(float).tolist()
    out = []
    for i, row in enumerate(idx):
        cand = sorted((((xs[j] - xs[i]) ** 2 + (ys[j] - ys[i]) ** 2), j) for j in row if j != i)
        out.append([j for _, j in cand[:k]])
    return out


def two_opt(points: np.ndarray, order: np.ndarray, max_time: float = 5.0, neighbours: int = 25,
            fixed_start: bool = True) -> np.ndarray:
    """Improve an open route with 2-opt moves until none helps or time runs out.

    Each point is only tried against its `neighbours` nearest points (a new edge to a far point never shortens a
    good route), and only points whose surroundings changed are tried again ("don't-look bits"). Work per sweep
    grows with n instead of n^2, so 5000 points converge in seconds. Moves that reverse the end of the route are
    included; with fixed_start the first point stays first (the route then starts where it was told to).
    """
    from collections import deque

    n = len(order)
    order = [int(i) for i in order]
    if n < 4:
        return np.asarray(order)
    xs, ys = points[:, 0].astype(float).tolist(), points[:, 1].astype(float).tolist()

    def d(a, b):
        return ((xs[a] - xs[b]) ** 2 + (ys[a] - ys[b]) ** 2) ** 0.5

    nbr = _neighbour_lists(points, neighbours)
    pos = [0] * n
    for i, c in enumerate(order):
        pos[c] = i

    def reverse(i, j):  # reverse order[i..j] (inclusive)
        order[i : j + 1] = order[i : j + 1][::-1]
        for t in range(i, j + 1):
            pos[order[t]] = t

    def improve(a):
        """First improving move that creates an edge from a to one of its neighbours; True if one was made."""
        i = pos[a]
        for side in (1, -1):  # break the edge to a's successor, or to its predecessor
            if not 0 <= i + side < n:
                continue
            b = order[i + side]
            dab = d(a, b)
            for c in nbr[a]:
                dac = d(a, c)
                if dac >= dab:
                    break  # neighbours are sorted: no gain possible from here on
                j = pos[c]
                if side == 1:  # new edges (a, c) and (b, c'), reversing b..c or c'..a
                    if j > i + 1:
                        e = order[j + 1] if j + 1 < n else None
                        gain = dab - dac + ((d(c, e) - d(b, e)) if e is not None else 0)
                        lo, hi = i + 1, j
                    elif j < i:
                        e = order[j + 1]
                        gain = dab - dac + d(c, e) - d(e, b)
                        lo, hi = j + 1, i
                    else:
                        continue
                else:  # side == -1: new edges (c, a) and (c', b), reversing b..c or c..b
                    if j < i - 1:
                        e = order[j - 1] if j > 0 else None
                        if e is None and fixed_start:
                            continue
                        gain = dab - dac + ((d(e, c) - d(e, b)) if e is not None else 0)
                        lo, hi = j, i - 1
                    elif j > i:
                        e = order[j - 1]
                        gain = dab - dac + d(e, c) - d(b, e)
                        lo, hi = i, j - 1
                    else:
                        continue
                if fixed_start and lo == 0:
                    continue
                if gain > 1e-12:
                    reverse(lo, hi)
                    for p in (a, b, c) + ((e,) if e is not None else ()):
                        if not queued[p]:
                            queued[p] = True
                            todo.append(p)
                    return True
        return False

    queued = [True] * n
    todo = deque(order)
    start = time.perf_counter()
    while True:
        while todo:
            if time.perf_counter() - start > max_time:
                log.info("2-opt: time limit reached")
                return np.asarray(order)
            a = todo.popleft()
            queued[a] = False
            if improve(a) and not queued[a]:
                queued[a] = True
                todo.append(a)
        # a reversal elsewhere can open a move for a point whose own edges did not change: sweep all points once
        # more, and stop only when a full sweep finds nothing
        swept = False
        for a in list(order):
            if time.perf_counter() - start > max_time:
                return np.asarray(order)
            if improve(a):
                swept = True
        if not swept:
            return np.asarray(order)


def or_opt(points: np.ndarray, order: np.ndarray, max_time: float = 5.0, neighbours: int = 25) -> np.ndarray:
    """Move stretches of 1-3 consecutive points (either way round) to a better place in the route, next to one of
    the nearest neighbours of their ends, until no move helps or time runs out. The first point stays first."""
    n = len(order)
    order = [int(i) for i in order]
    if n < 5:
        return np.asarray(order)
    xs, ys = points[:, 0].astype(float).tolist(), points[:, 1].astype(float).tolist()

    def d(a, b):
        return ((xs[a] - xs[b]) ** 2 + (ys[a] - ys[b]) ** 2) ** 0.5

    nbr = _neighbour_lists(points, neighbours)
    pos = {c: i for i, c in enumerate(order)}
    start = time.perf_counter()
    improved = True
    while improved and time.perf_counter() - start < max_time:
        improved = False
        for s in range(1, n):
            if time.perf_counter() - start > max_time:
                break
            for length in (1, 2, 3):
                t = s + length - 1
                if t >= n:
                    break
                seg = order[s : t + 1]
                p, q = order[s - 1], (order[t + 1] if t + 1 < n else None)
                removed = d(p, seg[0]) + ((d(seg[-1], q) - d(p, q)) if q is not None else 0)
                best, best_at = 1e-12, None
                for end in (seg[0], seg[-1]):
                    for u in nbr[end]:
                        iu = pos[u]
                        if s - 1 <= iu <= t:  # inside the stretch, or the point before it (same place)
                            continue
                        v = order[iu + 1] if iu + 1 < n else None
                        if v is not None and s <= pos[v] <= t:
                            continue
                        for first, last in ((seg[0], seg[-1]), (seg[-1], seg[0])):  # insert between u and v
                            added = d(u, first) + ((d(last, v) - d(u, v)) if v is not None else 0)
                            if removed - added > best:
                                best, best_at = removed - added, (u, first != seg[0])
                if best_at is not None:
                    u, flip = best_at
                    rest = order[:s] + order[t + 1 :]
                    k = rest.index(u) + 1
                    order = rest[:k] + (seg[::-1] if flip else seg) + rest[k:]
                    pos = {c: i for i, c in enumerate(order)}
                    improved = True
                    break
    return np.asarray(order)


def optimize_path(points: np.ndarray, max_time: float = 5.0, start: np.ndarray | None = None) -> np.ndarray:
    """Visiting order of the points: nearest neighbour from the point closest to `start` (default: stage
    origin), then alternately 2-opt and Or-opt while they improve the route (within max_time); the route keeps
    starting there."""
    order = nearest_neighbour_path(points, start)
    length_nn = path_length(points, order)
    deadline = time.perf_counter() + max_time
    order = two_opt(points, order, max_time, neighbours=25)
    while (left := deadline - time.perf_counter()) > 0:
        before = path_length(points, order)
        order = or_opt(points, order, left)
        order = two_opt(points, order, max(0.0, deadline - time.perf_counter()), neighbours=25)
        if path_length(points, order) > before - 1e-12 * max(1.0, before):
            break
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
