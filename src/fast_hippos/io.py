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


def iter_images(path: Path, series: list[int] | None = None) -> Iterator[ImageData]:
    """Yield all images (series) in a file."""
    suffix = path.suffix.lower()
    if suffix in (".tif", ".tiff"):
        yield read_tiff(path)
    elif suffix == ".lif":
        yield from read_lif(path, series)
    elif suffix == ".npy":
        arr = np.load(path)
        yield ImageData(_to_tcyx(arr, "TCYX"[-arr.ndim :]), path.stem, path)
    else:
        raise ValueError(f"Unsupported file type: {path} (supported: .tif, .lif, .npy)")


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
    return ImageData(data, path.stem, path, pixel_size, frame_interval, info)


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


def read_lif(path: Path, series: list[int] | None = None) -> Iterator[ImageData]:
    try:
        from readlif.reader import LifFile
    except ImportError as err:
        raise ImportError("Reading .lif files requires 'readlif': uv sync --extra lif") from err
    lif = LifFile(str(path))
    indices = series if series is not None else range(lif.num_images)
    for i in indices:
        img = lif.get_image(i)
        nt, nc = img.dims.t, img.channels
        nz = img.dims.z
        if nz > 1 and nt > 1:
            raise ValueError(f"{path.name} series {i}: z-stacks with time frames are not supported")
        n = max(nt, nz)
        frames = []
        for t in range(n):
            chans = [
                np.asarray(img.get_frame(z=t if nz > 1 else 0, t=t if nt > 1 else 0, c=c)) for c in range(nc)
            ]
            frames.append(np.stack(chans))
        data = np.stack(frames)
        pixel_size = 1.0 / img.scale[0] if img.scale and img.scale[0] else None  # scale is px/µm
        frame_interval = None
        if nt > 1 and len(img.scale) > 3 and img.scale[3]:
            frame_interval = 1.0 / img.scale[3]
        name = f"{path.stem} - {img.name.replace('/', '-')}"
        stage = _lif_stage_position(img)
        yield ImageData(data, name, path, pixel_size, frame_interval, stage_position=stage, extra={"series": i})


def _lif_stage_position(img) -> tuple[float, float] | None:
    """Stage position (m) of a .lif series, from the Leica XML (best effort, unverified on all LAS X versions)."""
    try:
        root = img.xml_root if hasattr(img, "xml_root") else None
        if root is None:
            return None
        for el in root.iter():
            if "StagePosX" in el.attrib and "StagePosY" in el.attrib:
                return float(el.attrib["StagePosX"]), float(el.attrib["StagePosY"])
    except (AttributeError, ValueError):
        pass
    return None


def lif_stage_positions(path: Path, n: int | None = None) -> np.ndarray:
    """Stage positions (n, 2) in m of the first n series of a .lif file."""
    positions = []
    for k, image in enumerate(read_lif(path)):
        if n is not None and k >= n:
            break
        if image.stage_position is None:
            raise ValueError(f"No stage position found for series {k} in {path.name}")
        positions.append(image.stage_position)
    return np.array(positions, dtype=float)


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
