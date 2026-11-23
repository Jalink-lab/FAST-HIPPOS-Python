"""Reading input images and metadata, writing calibrated TIFFs."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import tifffile

log = logging.getLogger(__name__)

_UNIT_TO_UM = {"micron": 1.0, "um": 1.0, "µm": 1.0, "\\u00B5m": 1.0, "mm": 1e3, "cm": 1e4, "m": 1e6, "nm": 1e-3}
_UNIT_TO_S = {"s": 1.0, "sec": 1.0, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "ns": 1e-9, "min": 60.0, "h": 3600.0}

IMAGE_SUFFIXES = (".tif", ".tiff", ".lif", ".czi")  # what the file dialog offers; a new format also goes in FORMATS below
# Screening writes hits as Leica .rgn files, from Leica stage coordinates: not for files from elsewhere
NO_SCREENING = {"czi": "Zeiss .czi", "ome-tiff": "OME-TIFF"}


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


def safe_name(name: str) -> str:
    """The folder / file name for an image name (characters that Windows does not allow become '_')."""
    return "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in name).strip()


def iter_images(path: Path, series: list[int] | None = None, bidirectional: str | None = None,
                channels: list[int] | None = None) -> Iterator[ImageData]:
    """Yield all images (series) in a file; a folder of tiles, or a tile scan in a .lif, is stitched into one image
    (bidirectional, channels: per-tile phase correction, see stitch.stitch_folder)."""
    suffix = path.suffix.lower()
    if path.is_dir():
        from .stitch import stitch_folder

        yield stitch_folder(path, bidirectional=bidirectional, channels=channels)
    elif suffix in (".tif", ".tiff"):
        with tifffile.TiffFile(path) as tif:
            n = len(tif.series) if tif.is_ome else 1
        for i in ([k for k in series if 0 <= k < n] if series and n > 1 else range(n)):
            yield read_tiff(path, i)
    elif suffix == ".lif":
        yield from read_lif(path, series, bidirectional, channels)
    elif suffix == ".czi":
        from .czi import read_czi

        yield from read_czi(path, series)
    elif suffix == ".npy":
        arr = np.load(path)
        yield ImageData(_to_tcyx(arr, "TCYX"[-arr.ndim :]), path.stem, path)
    else:
        raise ValueError(f"Unsupported file type: {path} (supported: .tif, .ome.tif, .lif, .czi, .npy)")


def has_series(path: str | Path) -> bool:
    """Whether a file can hold several images, each analyzed on its own (.lif, .czi, .ome.tif)."""
    name = Path(path).name.lower()
    return name.endswith((".lif", ".czi", ".ome.tif", ".ome.tiff"))


def image_name(path: Path, info: dict, n_series: int) -> str:
    """The name the analysis gives an image of image_info, and so the name of its result folder."""
    if path.suffix.lower() == ".lif" or (n_series > 1 and has_series(path)):
        return f"{path.stem} - {info['name'].replace('/', '-')}"
    return info["name"]


def _ome_metadata(tif: tifffile.TiffFile, series: int) -> dict:
    """Name, pixel size (µm) and frame interval (s) of a series, from the OME-XML (empty where it gives none)."""
    out: dict = {}
    try:
        root = ET.fromstring(tif.ome_metadata)
        image = root.findall("{*}Image")[series]
        pixels = image.find("{*}Pixels")
    except (ET.ParseError, TypeError, IndexError):
        return out
    if image.get("Name"):
        out["name"] = image.get("Name")
    if pixels is None:
        return out
    size, unit = pixels.get("PhysicalSizeX"), pixels.get("PhysicalSizeXUnit", "µm")
    if size and unit in _UNIT_TO_UM and float(size) > 0:
        out["pixel_size"] = float(size) * _UNIT_TO_UM[unit]
    step, unit = pixels.get("TimeIncrement"), pixels.get("TimeIncrementUnit", "s")
    if step and unit in _UNIT_TO_S and float(step) > 0:
        out["frame_interval"] = float(step) * _UNIT_TO_S[unit]
    else:  # from the time of the planes of the first channel and slice
        times = sorted((int(p.get("TheT", 0)), float(p.get("DeltaT")) * _UNIT_TO_S.get(p.get("DeltaTUnit", "s"), 1.0))
                       for p in pixels.findall("{*}Plane")
                       if p.get("DeltaT") and p.get("TheC", "0") == "0" and p.get("TheZ", "0") == "0")
        if len(times) > 1 and times[-1][0] > times[0][0] and times[-1][1] > times[0][1]:
            out["frame_interval"] = (times[-1][1] - times[0][1]) / (times[-1][0] - times[0][0])
    return out


def _ome_infos(path: Path, tif: tifffile.TiffFile) -> list[dict]:
    out = []
    for i, s in enumerate(tif.series):
        t, c, h, w = _tcyx_shape(s.shape, s.axes)
        meta = _ome_metadata(tif, i)
        name = (meta.get("name") or f"series {i}") if len(tif.series) > 1 else path.stem
        info = {"name": name, "frames": t, "channels": c, "width": w, "height": h, "dtype": str(s.dtype),
                "format": "ome-tiff", "stitched": False}
        if "pixel_size" in meta:
            info["pixel_size"] = round(meta["pixel_size"], 4)
        if "frame_interval" in meta:
            info["frame_interval"] = meta["frame_interval"]
        out.append(info)
    return out


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
            if tif.is_ome:
                return _ome_infos(path, tif)
            s = tif.series[0]
            ij = tif.imagej_metadata or {}
            t, c, h, w = _tcyx_shape(s.shape, s.axes)
            info = {"name": path.stem, "frames": t, "channels": c, "width": w, "height": h, "dtype": str(s.dtype),
                    "format": "tiff", "frame_interval": ij.get("finterval"),
                    "stitched": "Stitched image" in (ij.get("Info") or "")}
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
        from liffile import LifFile

        from .stitch import TileLayout, lif_images

        scans = lif_images(path)
        out = []
        with LifFile(path) as doc:
            for img in _lif_series(doc):
                d = _lif_dims(img)
                info = {"name": img.path, "frames": max(d["t"], d["z"], 1), "channels": d["c"],
                        "width": d["x"], "height": d["y"], "format": "lif"}
                scan = scans.get(_lif_full_name(doc, img))
                if scan is not None:
                    info["positions"] = True
                    if scan.pixel_size:
                        info["pixel_size"] = round(scan.pixel_size, 4)
                    if d["m"] > 1 and len(scan.positions) == d["m"] and scan.pixel_size:
                        h, w = TileLayout([""] * d["m"], scan.positions, (d["x"], d["y"]), scan.pixel_size).shape
                        info |= {"width": w, "height": h, "tiles": d["m"], "stitched": True}
                out.append(info)
        return out
    if suffix == ".czi":
        from .czi import czi_info

        return czi_info(path)
    if suffix == ".npy":
        arr = np.load(path, mmap_mode="r")
        t, c, h, w = _tcyx_shape(arr.shape, "TCYX"[-arr.ndim :])
        return [{"name": path.stem, "frames": t, "channels": c, "width": w, "height": h}]
    raise ValueError(f"Unsupported file type: {path.name} (supported: .tif, .ome.tif, .lif, .czi, .npy)")


def _tcyx_shape(shape: tuple, axes: str) -> tuple[int, int, int, int]:
    """(T, C, Y, X) sizes that _to_tcyx would produce, without reading any pixels."""
    axes = axes.upper().replace("S", "C").replace("Q", "T")
    dims = dict(zip(axes, shape, strict=True))
    frames = dims.get("T", 1) if "T" in axes else dims.get("Z", 1)
    return frames, dims.get("C", 1), dims["Y"], dims["X"]


def read_tiff(path: Path, series_index: int = 0) -> ImageData:
    """A TIFF as (T, C, Y, X). An OME-TIFF can hold several images (series_index) and has its calibration in its XML."""
    with tifffile.TiffFile(path) as tif:
        if tif.is_ome:
            n = len(tif.series)
            s, meta = tif.series[series_index], _ome_metadata(tif, series_index)
            name = f"{path.stem} - {(meta.get('name') or f'series {series_index}').replace('/', '-')}" if n > 1 else path.stem
            return ImageData(_to_tcyx(s.asarray(), s.axes), name, path, meta.get("pixel_size"), meta.get("frame_interval"),
                             extra={"series": series_index})
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
    from liffile import LifFile

    from .stitch import TileLayout, lif_images, stitch_tiles

    scans = lif_images(path)
    with LifFile(path) as lif:
        images = _lif_series(lif)
        for i in (series if series is not None else range(len(images))):
            img = images[i]
            d = _lif_dims(img)
            nt, nz, nm = d["t"], d["z"], d["m"]
            if nz > 1 and nt > 1:
                raise ValueError(f"{path.name} series {i}: z-stacks with time frames are not supported")
            scan = scans.get(_lif_full_name(lif, img))
            # Length / N from the header matches the stage steps (see stitch.py); the step of the coordinates is
            # Length / (N - 1), only used when the header gives no pixel size
            pixel_size = scan.pixel_size if scan and scan.pixel_size else _lif_step(img, "X", 1e6)
            frame_interval = _lif_step(img, "T") if nt > 1 else None
            name = f"{path.stem} - {img.path.replace('/', '-')}"
            if nm > 1:
                if scan is None or len(scan.positions) != nm or not pixel_size:
                    raise ValueError(f"{path.name} series {i} ('{img.path}'): tile scan of {nm} tiles without their positions")
                layout = TileLayout([f"tile {m}" for m in range(nm)], scan.positions, (d["x"], d["y"]), pixel_size,
                                    f"{path.name} ({scan.flags})")
                data, info = stitch_tiles([_lif_tile(img, m) for m in range(nm)], layout, bidirectional, channels, name)
                yield ImageData(data, name, path, pixel_size, frame_interval, info, extra={"series": i, "tiles": nm})
            else:
                stage = tuple(float(v) for v in scan.positions[0]) if scan is not None else None
                yield ImageData(_lif_tile(img, 0), name, path, pixel_size, frame_interval, stage_position=stage, extra={"series": i})


def _lif_series(lif) -> list:
    """The images of a .lif file that FAST-HIPPOS can read, in file order (the series numbers in settings and runs)."""
    return [img for img in lif.images if not img.is_flim]


def _lif_dims(img) -> dict[str, int]:
    """Sizes of a liffile image; a dimension that is not there counts as 1. RGB samples count as channels."""
    s = img.sizes
    return {"x": s.get("X", 1), "y": s.get("Y", 1), "t": s.get("T", 1), "z": s.get("Z", 1), "m": s.get("M", 1),
            "c": s.get("C", s.get("S", 1))}


def _lif_step(img, dim: str, scale: float = 1.0) -> float | None:
    """Spacing of a dimension from its coordinates (metres for X, seconds for T), times scale."""
    values = img.coords.get(dim)
    if values is None or len(values) < 2:
        return None
    step = abs(float(values[-1]) - float(values[0])) / (len(values) - 1)
    return step * scale if step > 0 else None


def _lif_tile(img, m: int) -> np.ndarray:
    """Tile m of a liffile image as (T, C, Y, X); z-slices count as frames."""
    d, sizes = _lif_dims(img), img.sizes
    if "X" not in sizes or "Y" not in sizes:  # e.g. a line scan: keeps its series number, but is no image to analyze
        raise ValueError(f"Series '{img.path}' is not an XY image (dimensions {', '.join(sizes)})")
    axis = "T" if d["t"] > 1 else "Z"

    def plane(t: int, c: int) -> np.ndarray:
        at = {k: v for k, v in ((axis, t), ("M", m), ("C", c)) if k in sizes}
        frame = img.frame(**at)
        return np.asarray(frame[..., c] if "S" in sizes else frame)

    return np.stack([np.stack([plane(t, c) for c in range(d["c"])]) for t in range(max(d["t"], d["z"]))])


def _lif_full_name(lif, img) -> str:
    """Full name of an image as stitch.lif_images keys it ('project/folder/image')."""
    return f"{lif.name}/{img.path}"


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
