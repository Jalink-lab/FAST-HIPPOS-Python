"""Zeiss .czi files, read with Zeiss's pylibCZIrw. Every scene is an image; a tile scan comes back already stitched.

Screening is not available for these files (see io.NO_SCREENING): the hits are written as Leica .rgn files.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np

_DTYPES = {"Gray8": "uint8", "Gray16": "uint16", "Gray32Float": "float32",
           "Bgr24": "uint8", "Bgr48": "uint16", "Bgr96Float": "float32"}


def _reader():
    try:
        from pylibCZIrw import czi
    except ImportError as e:
        raise ValueError("CZI files cannot be read on this computer (the CZI reader pylibCZIrw has no version for it, "
                         "for example an Intel Mac): export the images as TIFF") from e
    return czi


def _get(node, *keys):
    """A value deep in the metadata dictionary, or None."""
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _as_list(value) -> list:
    return [] if value is None else value if isinstance(value, list) else [value]


def _float(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _metadata(doc) -> dict:
    """Pixel size (µm), frame interval (s) and scene names, where the file gives them."""
    meta = _get(doc.metadata, "ImageDocument", "Metadata") or {}
    pixel_size = None
    for item in _as_list(_get(meta, "Scaling", "Items", "Distance")):
        if isinstance(item, dict) and item.get("@Id") == "X" and (v := _float(item.get("Value"))):
            pixel_size = v * 1e6  # the file stores metres
    dims = _get(meta, "Information", "Image", "Dimensions")
    interval = _float(_get(dims, "T", "Positions", "Interval", "Increment"))
    names = {}
    for scene in _as_list(_get(dims, "S", "Scenes", "Scene")):
        if isinstance(scene, dict) and scene.get("@Index") is not None and scene.get("@Name"):
            names[int(scene["@Index"])] = str(scene["@Name"])
    return {"pixel_size": pixel_size, "frame_interval": interval, "scene_names": names}


def _layout(doc, path: Path) -> dict:
    """Sizes and pixel type of the file."""
    box = doc.total_bounding_box
    other = {k: v[1] - v[0] for k, v in box.items() if k not in "TZCXY" and v[1] - v[0] > 1}
    if other:
        text = ", ".join(f"{k} = {n}" for k, n in other.items())
        raise ValueError(f"{path.name} has dimensions that FAST-HIPPOS does not read ({text})")
    nt, nz, nc = (box[a][1] - box[a][0] for a in "TZC")
    if nt > 1 and nz > 1:
        raise ValueError(f"{path.name}: z-stacks with time frames are not supported")
    types = [doc.get_channel_pixel_type(c) for c in range(box["C"][0], box["C"][1])]
    unknown = sorted({t for t in types if t not in _DTYPES})
    if unknown:
        raise ValueError(f"{path.name}: pixel type {', '.join(unknown)} is not supported")
    rgb = [t.startswith("Bgr") for t in types]
    if any(rgb) and not all(rgb):
        raise ValueError(f"{path.name} mixes colour and grey channels, which is not supported")
    return {"box": box, "nt": nt, "nz": nz, "nc": nc, "rgb": all(rgb),
            "dtype": np.result_type(*[_DTYPES[t] for t in types])}


def _scenes(doc) -> list:
    """(scene index or None, rectangle) of every image in the file."""
    rects = doc.scenes_bounding_rectangle
    return [(s, rects[s]) for s in sorted(rects)] or [(None, doc.total_bounding_rectangle)]


def _name(scene, scenes: list, names: dict) -> str | None:
    if len(scenes) < 2:
        return None
    return names.get(scene) or f"scene {scene + 1}"


def czi_info(path: Path) -> list[dict]:
    """Size of every scene from the metadata only."""
    with _reader().open_czi(str(path)) as doc:
        lay, meta, scenes = _layout(doc, path), _metadata(doc), _scenes(doc)
        out = []
        for scene, rect in scenes:
            info = {"name": _name(scene, scenes, meta["scene_names"]) or path.stem, "frames": max(lay["nt"], lay["nz"]),
                    "channels": lay["nc"] * (3 if lay["rgb"] else 1), "width": rect.w, "height": rect.h,
                    "dtype": str(lay["dtype"]), "format": "czi"}
            if meta["pixel_size"]:
                info["pixel_size"] = round(meta["pixel_size"], 4)
            if meta["frame_interval"] and lay["nt"] > 1:
                info["frame_interval"] = meta["frame_interval"]
            out.append(info)
    return out


def read_czi(path: Path, series: list[int] | None = None) -> Iterator:
    """The scenes of a .czi file as ImageData (T, C, Y, X). Colour images: one channel per R, G, B."""
    from .io import ImageData

    with _reader().open_czi(str(path)) as doc:
        lay, meta, scenes = _layout(doc, path), _metadata(doc), _scenes(doc)
        box, nt, nz, nc = lay["box"], lay["nt"], lay["nz"], lay["nc"]
        frames = max(nt, nz)
        for i in (series if series is not None else range(len(scenes))):
            if not 0 <= i < len(scenes):
                raise ValueError(f"{path.name} has {len(scenes)} scene(s); series {i} does not exist")
            scene, rect = scenes[i]
            n_out = nc * (3 if lay["rgb"] else 1)
            data = np.zeros((frames, n_out, rect.h, rect.w), lay["dtype"])
            for f in range(frames):
                for c in range(nc):
                    plane = doc.read(plane={"T": box["T"][0] + (f if nt > 1 else 0), "Z": box["Z"][0] + (f if nz > 1 else 0),
                                            "C": box["C"][0] + c}, scene=scene, roi=(rect.x, rect.y, rect.w, rect.h))
                    if lay["rgb"]:
                        data[f, c * 3:c * 3 + 3] = np.moveaxis(plane[..., ::-1], -1, 0)  # stored as B, G, R
                    else:
                        data[f, c] = plane[..., 0]
            part = _name(scene, scenes, meta["scene_names"])
            name = f"{path.stem} - {part.replace('/', '-')}" if part else path.stem
            yield ImageData(data, name, path, meta["pixel_size"], meta["frame_interval"] if nt > 1 else None,
                            extra={"series": i})
