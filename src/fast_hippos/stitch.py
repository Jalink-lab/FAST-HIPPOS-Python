"""Stitching of tiles exported from LAS X (one TIFF per tile) into one image, by their stage positions.

LAS X can stitch a tile scan itself, but the result has a single stage position; the screening needs the position
of every tile. Those are in the Leica XML: in the MetaData/<name>.xml that LAS X writes next to exported TIFFs, and in
the .lif header. They are read once and kept in a small file next to the tiles (TILE_POSITIONS), so the .lif is not
needed afterwards.

Stage positions are given as Bio-Formats puts them in the OME-XML (and as Stitch_tiles.ijm writes them): the Leica
tile position (PosX, PosY), with X and Y swapped when SwapXY is set, then X negated when FlipX is set and Y when
FlipY is set. These are the positions stage.py works with (abs_x = -stage_Y, abs_y = -stage_X).

Placement: every tile goes where its stage position says, rounded to whole pixels. Nothing assumes a regular grid or
touching tiles, so irregular scans work, and tiles that overlap are allowed (for now a later tile simply covers an
earlier one; blending and registration of the overlap would go in `fuse` and `TileLayout.offsets_px`).
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile

from . import preprocess, stage
from .io import ImageData, _tcyx_shape, read_tiff

log = logging.getLogger(__name__)

TILE_POSITIONS = "tile_positions.tsv"  # written next to the tiles
_HEADER = "# FAST-HIPPOS tile positions. Stage X, Y (m) as in the OME-XML (Bio-Formats); pixel size in µm.\n"


@dataclass
class TileLayout:
    """Where the tiles of one tile scan are: stage positions, tile size and pixel size."""

    files: list[str]  # tile file names, in tile order
    positions: np.ndarray  # (n, 2) stage X, Y in m (OME-XML convention, see module doc)
    tile_px: tuple[int, int]  # (width, height) of one tile in pixels
    pixel_size: float  # µm
    source: str = ""  # where the positions came from

    @property
    def tile_size(self) -> tuple[float, float]:
        """(w, h) of one tile in m."""
        return self.tile_px[0] * self.pixel_size * 1e-6, self.tile_px[1] * self.pixel_size * 1e-6

    def _corners(self) -> np.ndarray:
        """(n, 2) top-left corner of every tile in the image frame (x right, y down), in m, up to a constant:
        image x runs along -stage Y and image y along -stage X (see stage.py)."""
        return np.column_stack([-self.positions[:, 1], -self.positions[:, 0]])

    def offsets_px(self) -> np.ndarray:
        """(n, 2) integer (x, y) pixel offset of every tile in the stitched image."""
        c = self._corners()
        return np.rint((c - c.min(axis=0)) / (self.pixel_size * 1e-6)).astype(int)

    @property
    def shape(self) -> tuple[int, int]:
        """(height, width) of the stitched image."""
        o = self.offsets_px()
        return int(o[:, 1].max()) + self.tile_px[1], int(o[:, 0].max()) + self.tile_px[0]

    @property
    def origin(self) -> tuple[float, float]:
        """Stage (X, Y) in m of a tile that would sit exactly at the origin of the stitched image."""
        c = self._corners().min(axis=0)
        return -c[1], -c[0]

    @property
    def n_tiles(self) -> tuple[int, int]:
        """(nx, ny): number of distinct tile columns and rows (positions within half a tile count as one)."""
        o = self.offsets_px()
        return _n_distinct(o[:, 0], self.tile_px[0] / 2), _n_distinct(o[:, 1], self.tile_px[1] / 2)

    @property
    def overlap(self) -> float:
        """Fraction of a tile that neighbouring tiles share (median over the neighbours along x and y; 0 for a
        single tile). Informative only: the placement uses the positions themselves."""
        o = self.offsets_px()
        steps = []
        for axis in (0, 1):
            d = np.diff(np.unique(o[:, axis]))
            d = d[d > self.tile_px[axis] / 2]
            if len(d):
                steps.append(1 - np.median(d) / self.tile_px[axis])
        return float(np.mean(steps)) if steps else 0.0

    def stage_info(self, bidirectional: float | None = None) -> stage.StageInfo:
        return stage.StageInfo(self.positions, self.n_tiles, self.tile_size, round(self.overlap, 4), self.origin,
                               bidirectional)


def _n_distinct(values: np.ndarray, tolerance: float) -> int:
    v = np.sort(values)
    return int(1 + (np.diff(v) > tolerance).sum())


# ---------------------------------------------------------------- tiles and positions


def find_tiles(folder: Path) -> list[Path]:
    """The tile TIFFs in a folder, in tile order: by the number at the end of the name (LAS X: name_s0 ... _s99),
    so that _s10 comes after _s9. Stitched results in the same folder are skipped."""
    files = [p for p in Path(folder).iterdir()
             if p.suffix.lower() in (".tif", ".tiff") and "_STITCHED" not in p.stem.upper()]

    def number(p: Path) -> tuple:
        m = re.search(r"(\d+)$", p.stem)
        return (p.stem[: m.start()] if m else p.stem, int(m.group(1)) if m else -1)

    return sorted(files, key=number)


def ome_position(pos_x: float, pos_y: float, flip_x: bool, flip_y: bool, swap_xy: bool) -> tuple[float, float]:
    """Leica tile position -> stage position as Bio-Formats writes it in the OME-XML: swap, then flip."""
    x, y = (pos_y, pos_x) if swap_xy else (pos_x, pos_y)
    return (-x if flip_x else x), (-y if flip_y else y)


@dataclass
class _TileScan:
    name: str
    positions: np.ndarray  # (n, 2) OME convention
    pixel_size: float | None  # µm
    flags: str
    tiled: bool = True  # False: a single image with only its StagePosX / StagePosY


def _tile_scans(root: ET.Element) -> list[_TileScan]:
    """The stage positions of all images in a Leica XML tree (a .lif header or an exported MetaData .xml), in file
    order: every tile of a tile scan, or the one stage position of an image without tiles (as Bio-Formats does).

    Images without scanner settings of their own (e.g. the FLIM results of a tile scan, which LAS X stores as
    child images) take the FlipX / FlipY / SwapXY of the nearest parent image that has them."""
    out: list[_TileScan] = []

    def walk(element: ET.Element, name: str, flags: dict | None) -> None:
        # .lif header: <Element><Data><Image/></Data><Children><Element/>...; exported .xml: <Data><Image/></Data>
        for image in element.findall("./Data/Image") + element.findall("./Image"):
            setting = image.find(".//ATLConfocalSettingDefinition")
            if setting is not None and "FlipX" in setting.attrib:
                flags = {k: setting.get(k) == "1" for k in ("FlipX", "FlipY", "SwapXY")}
            tiles = image.findall(".//Attachment[@Name='TileScanInfo']/Tile")
            leica = [(t.get("PosX"), t.get("PosY")) for t in tiles]
            if not leica and setting is not None and "StagePosX" in setting.attrib:
                leica = [(setting.get("StagePosX"), setting.get("StagePosY"))]
            if leica:
                f = flags or {"FlipX": False, "FlipY": False, "SwapXY": False}
                pos = [ome_position(float(x), float(y), f["FlipX"], f["FlipY"], f["SwapXY"]) for x, y in leica]
                out.append(_TileScan(name, np.array(pos), _pixel_size(image),
                                     " ".join(f"{k}={int(v)}" for k, v in f.items()) + ("" if flags else " (not found)"),
                                     bool(tiles)))
        for child in element.findall("./Children/Element") + element.findall("./Element"):
            walk(child, f"{name}/{child.get('Name')}" if name else child.get("Name", ""), flags)

    walk(root, root.get("Name", ""), None)
    return out


def _pixel_size(image: ET.Element) -> float | None:
    """Pixel size (µm) from the Leica dimension description: Length / NumberOfElements. (Leica's Length runs from
    the first to the last pixel centre; Bio-Formats divides by N - 1, hence 'Correct pixel size' in
    Stitch_tiles.ijm. Length / N gives the tile size that matches the stage steps.)"""
    for dim in image.iter("DimensionDescription"):
        if dim.get("DimID") == "1":
            unit = {"m": 1e6, "mm": 1e3, "um": 1.0, "µm": 1.0}.get(dim.get("Unit", "m"), 1e6)
            return float(dim.get("Length")) * unit / int(dim.get("NumberOfElements"))
    return None


def _pick(scans: list[_TileScan], n: int, source: str) -> _TileScan:
    """The first tile scan with n tiles (as Stitch_tiles.ijm takes the first n positions in the file)."""
    scans = [s for s in scans if s.tiled]
    matching = [s for s in scans if len(s.positions) == n]
    if not matching:
        sizes = ", ".join(f"'{s.name}': {len(s.positions)}" for s in scans) or "none"
        raise ValueError(f"No tile scan with {n} tiles in {source} (tile scans found: {sizes})")
    distinct = {s.positions.tobytes() for s in matching}
    if len(distinct) > 1:
        log.warning("%s holds %d different tile scans with %d tiles; using the first ('%s')",
                    source, len(distinct), n, matching[0].name)
    return matching[0]


def positions_from_xml(path: Path, n: int) -> tuple[np.ndarray, float | None, str]:
    """Tile positions from an exported LAS X MetaData .xml (or any file with the Leica XML)."""
    scan = _pick(_tile_scans(ET.parse(path).getroot()), n, path.name)
    return scan.positions, scan.pixel_size, f"{path.name} ({scan.flags})"


def _lif_header(path: Path) -> ET.Element:
    """The XML header of a .lif file (no pixel data is read)."""
    try:
        from readlif.reader import LifFile
    except ImportError as err:
        raise ImportError("Reading .lif files requires 'readlif': uv sync --extra lif") from err
    return LifFile(str(path)).xml_root


def positions_from_lif(path: Path, n: int) -> tuple[np.ndarray, float | None, str]:
    """Tile positions of the first tile scan with n tiles in a .lif file."""
    scan = _pick(_tile_scans(_lif_header(path)), n, path.name)
    return scan.positions, scan.pixel_size, f"{path.name}, '{scan.name}' ({scan.flags})"


def lif_stage_positions(path: Path) -> np.ndarray:
    """(n, 2) stage positions (m) of all tiles and images with a stage position in a .lif file, in file order
    (as Stitch_tiles.ijm, which takes the first n). Images without any position are left out."""
    scans = _tile_scans(_lif_header(path))
    if not scans:
        raise ValueError(f"No stage positions found in {path.name}")
    return np.concatenate([s.positions for s in scans])


def write_positions(path: Path, layout: TileLayout) -> None:
    lines = [_HEADER, f"# source: {layout.source}\n", f"# pixel_size_um: {layout.pixel_size:.10g}\n",
             "tile\tfile\tstage_x_m\tstage_y_m\n"]
    lines += [f"{k}\t{f}\t{x:.10g}\t{y:.10g}\n" for k, (f, (x, y)) in enumerate(zip(layout.files, layout.positions, strict=True))]
    path.write_text("".join(lines), encoding="utf-8")


def read_positions(path: Path) -> tuple[list[str], np.ndarray, float | None, str]:
    """(files, positions, pixel size, source) from a TILE_POSITIONS file."""
    files, pos, pixel_size, source = [], [], None, path.name
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# pixel_size_um:"):
            pixel_size = float(line.split(":", 1)[1])
        elif line.startswith("# source:"):
            source = f"{path.name} (from {line.split(':', 1)[1].strip()})"
        elif line and not line.startswith(("#", "tile\t")):
            _, f, x, y = line.split("\t")
            files.append(f)
            pos.append((float(x), float(y)))
    return files, np.array(pos, dtype=float), pixel_size, source


def tile_layout(folder: Path, lif: Path | None = None, pixel_size: float | None = None,
                save: bool = True) -> TileLayout:
    """Layout of the tiles in a folder. Positions from, in this order: the TILE_POSITIONS file next to the tiles,
    the LAS X MetaData/*.xml next to them, the .lif file. Positions read from XML are saved to TILE_POSITIONS.

    pixel_size (µm) overrides the one from the metadata."""
    folder = Path(folder)
    tiles = find_tiles(folder)
    if not tiles:
        raise ValueError(f"No tiles (.tif) in {folder}")
    names = [t.name for t in tiles]
    with tifffile.TiffFile(tiles[0]) as tif:
        tile_px = tuple(int(v) for v in tif.series[0].shape[-1:-3:-1])  # (width, height)
    sidecar = folder / TILE_POSITIONS
    meta_px = None
    if sidecar.exists():
        files, positions, meta_px, source = read_positions(sidecar)
        if files != names:
            raise ValueError(f"{sidecar} lists other tiles than the folder holds ({len(files)} listed, "
                             f"{len(names)} found); delete it to read the positions again")
        save = False
    else:
        xmls = sorted((folder / "MetaData").glob("*.xml")) if (folder / "MetaData").is_dir() else []
        xmls = [x for x in xmls if not x.stem.endswith("_properties")]
        if xmls:
            positions, meta_px, source = positions_from_xml(xmls[0], len(tiles))
        elif lif is not None:
            positions, meta_px, source = positions_from_lif(Path(lif), len(tiles))
        else:
            raise ValueError(f"No tile positions for {folder}: no {TILE_POSITIONS}, no LAS X MetaData folder, "
                             "and no .lif file given")
    px = pixel_size or meta_px or _tiff_pixel_size(tiles[0])
    if not px:
        raise ValueError(f"Pixel size of the tiles in {folder} unknown; give it in the settings")
    layout = TileLayout(names, positions, tile_px, px, source)
    if save:
        try:
            write_positions(sidecar, layout)
            log.info("Tile positions written to %s", sidecar)
        except OSError as e:
            log.warning("Could not write %s: %s", sidecar, e)
    return layout


def _tiff_pixel_size(path: Path) -> float | None:
    """Pixel size (µm) from the TIFF calibration, corrected as 'Correct pixel size' in Stitch_tiles.ijm."""
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        if "XResolution" not in page.tags:
            return None
        num, den = page.tags["XResolution"].value
        w = page.imagewidth
    return den / num * (w - 1) / w if num and num != den else None


# ---------------------------------------------------------------- stitching


def fuse(tiles: list[np.ndarray], offsets: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Place (T, C, h, w) tiles at their (x, y) pixel offsets in a (T, C, *shape) image. Where tiles overlap, the
    later tile covers the earlier one; uncovered pixels are 0."""
    t, c = tiles[0].shape[:2]
    out = np.zeros((t, c, *shape), dtype=np.result_type(*tiles))
    for tile, (x, y) in zip(tiles, offsets, strict=True):
        h, w = tile.shape[-2:]
        out[..., y : y + h, x : x + w] = tile
    return out


def stitch_folder(folder: Path, lif: Path | None = None, pixel_size: float | None = None,
                  bidirectional: str | None = None, channels: list[int] | None = None) -> ImageData:
    """Stitch the tiles in a folder into one ImageData, with the stitched metadata block in `info`.

    bidirectional: None, or the axis ("y" / "x") of the bidirectional phase correction. The offset is measured
    once over all tiles (summed over `channels`, 1-based; default all) and applied to every tile before stitching
    (on the stitched image, tiles with an odd spacing would swap even and odd lines and cancel the estimate)."""
    folder = Path(folder)
    layout = tile_layout(folder, lif, pixel_size)
    images = [read_tiff(folder / f) for f in layout.files]
    shapes = {im.data.shape for im in images}
    if len(shapes) > 1:
        raise ValueError(f"Tiles in {folder} differ in size: {sorted(shapes)}")
    tiles = [im.data for im in images]
    shift = None
    if bidirectional:
        chans = channels or list(range(1, tiles[0].shape[1] + 1))
        summed = sum(preprocess.summed_image(t, chans) for t in tiles)
        shift = preprocess.estimate_bidirectional_shift(summed, bidirectional)
        if abs(shift) >= preprocess.MIN_BIDIRECTIONAL_SHIFT:
            log.info("Bidirectional phase correction per tile (along %s): %.2f px", bidirectional, shift)
            tiles = [preprocess.apply_bidirectional(t, shift, bidirectional) for t in tiles]
        else:
            log.info("Bidirectional phase correction per tile (along %s): %.2f px, not applied", bidirectional, shift)
    data = fuse(tiles, layout.offsets_px(), layout.shape)
    info = layout.stage_info(shift)
    nx, ny = info.n_tiles
    log.info("Stitched %d tiles (%d x %d) from %s: %d x %d px, positions from %s", len(tiles), nx, ny, folder.name,
             data.shape[-1], data.shape[-2], layout.source)
    name = _stitched_name(layout.files)
    return ImageData(data, name, folder, layout.pixel_size, images[0].frame_interval, stage.stitched_info_block(info),
                     extra={"tiles": len(tiles)})


def _stitched_name(files: list[str]) -> str:
    """'testforbram_s0.tif' -> 'testforbram_STITCHED' (as Stitch_tiles.ijm)."""
    stem = Path(files[0]).stem
    m = re.search(r"_?s?\d+$", stem)
    return f"{stem[: m.start()] if m else stem}_STITCHED"


def stitched_info(folder: Path, lif: Path | None = None) -> dict:
    """Size of the stitched image from the metadata only (for the checks before a run, see io.image_info)."""
    layout = tile_layout(folder, lif, save=False)
    with tifffile.TiffFile(Path(folder) / layout.files[0]) as tif:
        s = tif.series[0]
        t, c, _, _ = _tcyx_shape(s.shape, s.axes)
    h, w = layout.shape
    return {"name": _stitched_name(layout.files), "frames": t, "channels": c, "width": w, "height": h,
            "pixel_size": layout.pixel_size, "stitched": True, "tiles": len(layout.files)}
