"""Example data of the user manual: three images cut from a large FLIM screen (95 % non-responders, 5 % responders),
with generic names and a stage positions file, so that the manual can show the overview and the .rgn export.

    python tools/manual/make_example_data.py <large TCYX ImageJ TIFF> <output folder>
"""

import sys
from pathlib import Path

import tifffile

# (x, y) of the top-left corner in the large image, in pixels; all crops 1000 x 700 pixels
CROPS = {"example_screen_1": (300, 250), "example_screen_2": (1700, 1100), "example_screen_3": (2900, 1700)}
W, H = 1000, 700
CENTRE = (-0.0426, -0.0593)  # stage position of the centre of the large image (m)


def main(source: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with tifffile.TiffFile(source) as tif:
        meta = tif.imagej_metadata or {}
        data = tif.series[0].asarray(out="memmap")  # T, C, Y, X
        px = tif.pages[0].tags["XResolution"].value
        pixel_size = px[1] / px[0]  # µm per pixel
    big_h, big_w = data.shape[-2:]
    positions = []
    for name, (x, y) in CROPS.items():
        crop = data[..., y:y + H, x:x + W]
        tifffile.imwrite(out / f"{name}.tif", crop, imagej=True, resolution=(1 / pixel_size, 1 / pixel_size),
                         metadata={"axes": "TCYX", "unit": "micron", "finterval": meta.get("finterval", 1.0), "mode": "color"})
        cx = CENTRE[0] + (x + W / 2 - big_w / 2) * pixel_size * 1e-6
        cy = CENTRE[1] + (y + H / 2 - big_h / 2) * pixel_size * 1e-6
        positions += [cx, cy]
        print(name, crop.shape)
    (out / "stage_positions.txt").write_text("".join(f"{v:.12f}\n" for v in positions), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
