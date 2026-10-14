"""Reading input images and metadata, writing calibrated TIFFs."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import tifffile

log = logging.getLogger(__name__)

_UNIT_TO_UM = {"micron": 1.0, "um": 1.0, "µm": 1.0, "\\u00B5m": 1.0, "mm": 1e3, "cm": 1e4, "m": 1e6, "nm": 1e-3}


@dataclass
class ImageData:
    """A time-lapse as a (T, C, Y, X) array (native dtype, to save memory) plus metadata."""

    data: np.ndarray
    name: str
    source: Path
    pixel_size: float | None = None  # µm
    frame_interval: float | None = None  # s
    info: str = ""  # ImageJ 'Info' metadata (holds the stitching / stage block)
    stage_position: tuple[float, float] | None = None  # (x, y) in m, from file metadata
    extra: dict = field(default_factory=dict)

    @property
    def n_frames(self) -> int:
        return self.data.shape[0]

    @property
    def n_channels(self) -> int:
        return self.data.shape[1]

    def channel(self, c: int) -> np.ndarray:
        """1-based channel as a float32 (T, Y, X) array."""
        if not 1 <= c <= self.n_channels:
            raise ValueError(f"Channel {c} requested, but '{self.name}' has {self.n_channels} channel(s)")
        return self.data[:, c - 1].astype(np.float32)


def iter_images(path: Path, series: list[int] | None = None, bidirectional: str | None = None,
                channels: list[int] | None = None) -> Iterator[ImageData]:
    """Yield all images (series) in a file; a folder of tiles, or a tile scan in a .lif, is stitched into one image
    (bidirectional, channels: per-tile phase correction, see stitch.stitch_folder)."""
    suffix = path.suffix.lower()
    if path.is_dir():
        from .stitch import stitch_folder

        yield stitch_folder(path, bidirectional=bidirectional, channels=channels)
    elif suffix in (".tif", ".tiff"):
        yield read_tiff(path)
    elif suffix == ".lif":
        yield from read_lif(path, series, bidirectional, channels)
    elif suffix == ".npy":
        arr = np.load(path)
        yield ImageData(_to_tcyx(arr, "TCYX"[-arr.ndim :]), path.stem, path)
    else:
        raise ValueError(f"Unsupported file type: {path} (supported: .tif, .lif, .npy)")


def image_info(path: Path, lif: Path | None = None) -> list[dict]:
    """Size of every image (series) in a file from its metadata only, with the axes interpreted as by
    iter_images: [{name, frames, channels, width, height, ...}]. Fast, also for large files. For a folder of tiles:
    the stitched image (lif: where the tile positions are, if not next to the tiles)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if path.is_dir():
        from .stitch import stitched_info

        return [stitched_info(path, lif)]
    if suffix in (".tif", ".tiff"):
        with tifffile.TiffFile(path) as tif:
            s = tif.series[0]
            ij = tif.imagej_metadata or {}
            t, c, h, w = _tcyx_shape(s.shape, s.axes)
            info = {"name": path.stem, "frames": t, "channels": c, "width": w, "height": h, "dtype": str(s.dtype),
                    "frame_interval": ij.get("finterval"), "stitched": "Stitched image" in (ij.get("Info") or "")}
            tag = tif.pages[0].tags.get("XResolution")
            if tag and tag.value[0] and str(ij.get("unit", "")) in (*_UNIT_TO_UM, "pixel"):  # as read_tiff
                info["pixel_size"] = round(tag.value[1] / tag.value[0], 4)
        if not info["stitched"]:
            from .stitch import tiff_metadata

            position, pixel_size = tiff_metadata(path)
            info["positions"] = position is not None
            if pixel_size and "pixel_size" not in info:
                info["pixel_size"] = round(pixel_size, 4)
        return [info]
    if suffix == ".lif":
        from readlif.reader import LifFile

        from .stitch import TileLayout, lif_images

        scans = lif_images(path)
        out = []
        for img in LifFile(str(path)).get_iter_image():
            dims = img.dims
            info = {"name": img.name, "frames": max(dims.t, dims.z, 1), "channels": img.channels,
                    "width": dims.x, "height": dims.y}
            scan = scans.get(_lif_full_name(img))
            if scan is not None:
                info["positions"] = True
                if scan.pixel_size:
                    info["pixel_size"] = round(scan.pixel_size, 4)
                if dims.m > 1 and len(scan.positions) == dims.m and scan.pixel_size:
                    h, w = TileLayout([""] * dims.m, scan.positions, (dims.x, dims.y), scan.pixel_size).shape
                    info |= {"width": w, "height": h, "tiles": dims.m, "stitched": True}
            out.append(info)
        return out
    if suffix == ".npy":
        arr = np.load(path, mmap_mode="r")
        t, c, h, w = _tcyx_shape(arr.shape, "TCYX"[-arr.ndim :])
        return [{"name": path.stem, "frames": t, "channels": c, "width": w, "height": h}]
    raise ValueError(f"Unsupported file type: {path.name} (supported: .tif, .lif, .npy)")


def _tcyx_shape(shape: tuple, axes: str) -> tuple[int, int, int, int]:
    """(T, C, Y, X) sizes that _to_tcyx would produce, without reading any pixels."""
    axes = axes.upper().replace("S", "C").replace("Q", "T")
    dims = dict(zip(axes, shape, strict=True))
    frames = dims.get("T", 1) if "T" in axes else dims.get("Z", 1)
    return frames, dims.get("C", 1), dims["Y"], dims["X"]


def read_tiff(path: Path) -> ImageData:
    with tifffile.TiffFile(path) as tif:
        series = tif.series[0]
        axes = series.axes
        arr = series.asarray()
        ij = tif.imagej_metadata or {}
        page = tif.pages[0]
        pixel_size = None
        unit = str(ij.get("unit", ""))
        # ImageJ stores the calibration as pixels per unit; without a known unit the image is uncalibrated
        if "XResolution" in page.tags:
            num, den = page.tags["XResolution"].value
            if num > 0 and unit in _UNIT_TO_UM:
                pixel_size = den / num * _UNIT_TO_UM[unit]
            elif num > 0 and num != den and unit == "pixel":
                # Fiji uses the scale even when the unit says 'pixel' (e.g. LAS X exports); assume µm
                pixel_size = den / num
                log.warning("%s: unit 'pixel' with scale %.4g; assuming µm", path.name, pixel_size)
        frame_interval = ij.get("finterval")
        info = ij.get("Info", "") or ""
    data = _to_tcyx(arr, axes)
    position = None
    if "Stitched image" not in info:  # LAS X export: stage position (and pixel size) in MetaData/<name>.xml
        from .stitch import tiff_metadata

        position, meta_pixel_size = tiff_metadata(path)
        if meta_pixel_size and (pixel_size is None or unit == "pixel"):  # more exact than the TIFF scale
            pixel_size = meta_pixel_size
    return ImageData(data, path.stem, path, pixel_size, frame_interval, info, stage_position=position)


def _to_tcyx(arr: np.ndarray, axes: str) -> np.ndarray:
    """Reorder an array with tifffile axes (e.g. 'TZCYX', 'CYX') to (T, C, Y, X).

    A z-dimension without a t-dimension is interpreted as time (as the Fiji macro does);
    'S' (RGB samples) is treated as channels.
    """
    axes = axes.upper().replace("S", "C").replace("Q", "T")
    if "Z" in axes and "T" in axes:
        z = axes.index("Z")
        if arr.shape[z] > 1:
            raise ValueError("Images with both z-slices and time frames are not supported")
        arr = np.take(arr, 0, axis=z)
        axes = axes.replace("Z", "")
    axes = axes.replace("Z", "T")
    for ax in "TC":
        if ax not in axes:
            arr = arr[np.newaxis]
            axes = ax + axes
    order = [axes.index(a) for a in "TCYX"]
    return np.ascontiguousarray(np.transpose(arr, order))  # native dtype; channel() converts


def read_lif(path: Path, series: list[int] | None = None, bidirectional: str | None = None,
             channels: list[int] | None = None) -> Iterator[ImageData]:
    """The images (series) of a .lif file, with their own stage position and pixel size from the header. A tile scan
    is stitched by the positions of its tiles."""
    try:
        from readlif.reader import LifFile
    except ImportError as err:
        raise ImportError("Reading .lif files requires 'readlif': uv sync --extra lif") from err
    from .stitch import TileLayout, lif_images, stitch_tiles

    lif = LifFile(str(path))
    scans = lif_images(path)
    indices = series if series is not None else range(lif.num_images)
    for i in indices:
        img = lif.get_image(i)
        nt, nz, nm = img.dims.t, img.dims.z, max(img.dims.m, 1)
        if nz > 1 and nt > 1:
            raise ValueError(f"{path.name} series {i}: z-stacks with time frames are not supported")
        scan = scans.get(_lif_full_name(img))
        # readlif's scale is (N - 1) / Length; Length / N from the header matches the stage steps (see stitch.py)
        pixel_size = scan.pixel_size if scan and scan.pixel_size else (1.0 / img.scale[0] if img.scale and img.scale[0] else None)
        frame_interval = None
        if nt > 1 and len(img.scale) > 3 and img.scale[3]:
            frame_interval = 1.0 / img.scale[3]
        name = f"{path.stem} - {img.name.replace('/', '-')}"
        if nm > 1:
            if scan is None or len(scan.positions) != nm or not pixel_size:
                raise ValueError(f"{path.name} series {i} ('{img.name}'): tile scan of {nm} tiles without their positions")
            layout = TileLayout([f"tile {m}" for m in range(nm)], scan.positions, (img.dims.x, img.dims.y), pixel_size,
                                f"{path.name} ({scan.flags})")
            data, info = stitch_tiles([_lif_tile(img, m) for m in range(nm)], layout, bidirectional, channels, name)
            yield ImageData(data, name, path, pixel_size, frame_interval, info, extra={"series": i, "tiles": nm})
        else:
            stage = tuple(float(v) for v in scan.positions[0]) if scan is not None else None
            yield ImageData(_lif_tile(img, 0), name, path, pixel_size, frame_interval, stage_position=stage, extra={"series": i})


def _lif_tile(img, m: int) -> np.ndarray:
    """Tile m of a readlif image as (T, C, Y, X); z-slices count as frames."""
    nt, nz = img.dims.t, img.dims.z
    return np.stack([np.stack([np.asarray(img.get_frame(z=t if nz > 1 else 0, t=t if nt > 1 else 0, c=c, m=m))
                               for c in range(img.channels)]) for t in range(max(nt, nz))])


def _lif_full_name(img) -> str:
    """Full name of a readlif image as stitch.lif_images keys it ('project/folder/image')."""
    return img.path + img.name.rsplit("/", 1)[-1]


def lif_stage_positions(path: Path, n: int | None = None) -> np.ndarray:
    """Stage positions (n, 2) in m of the first n tiles / images of a .lif file, from its header only (every tile of
    a tile scan has its own position; X and Y as in the OME-XML, see stitch.py)."""
    from .stitch import lif_stage_positions as positions

    return positions(path)[:n]


def write_tiff(
    path: Path,
    data: np.ndarray,
    axes: str,
    pixel_size: float | None = None,
    frame_interval: float | None = None,
    info: str | None = None,
    lut: np.ndarray | None = None,
) -> None:
    """Write an ImageJ-compatible TIFF (axes e.g. 'YX', 'TYX')."""
    metadata: dict = {"axes": axes}
    if pixel_size:
        metadata["unit"] = "um"
    if frame_interval:
        metadata["finterval"] = frame_interval
    if info:
        metadata["Info"] = info
    if lut is not None:
        metadata["LUTs"] = [lut]
    kwargs = {}
    if pixel_size:
        kwargs["resolution"] = (1.0 / pixel_size, 1.0 / pixel_size)
    if data.dtype == np.float64:
        data = data.astype(np.float32)
    if data.dtype == np.int64 or data.dtype == np.int32 or data.dtype == np.uint32:
        data = data.astype(np.uint16) if data.max() < 65536 else data.astype(np.float32)
    tifffile.imwrite(path, data, imagej=True, metadata=metadata, **kwargs)
