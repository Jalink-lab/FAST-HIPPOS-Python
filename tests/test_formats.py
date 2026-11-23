"""Image formats: OME-TIFF, Zeiss CZI (written here with pylibCZIrw), and screening only for Leica data."""

import numpy as np
import pytest
import tifffile

from fast_hippos import io
from fast_hippos.checks import SettingsError, check_inputs, screening_problems
from fast_hippos.config import Settings
from fast_hippos.pipeline import sample_list, sample_name


def stack(seed=0, t=3, c=2, h=32, w=40):
    return np.random.default_rng(seed).integers(0, 4000, (t, c, h, w), dtype=np.uint16)


def write_ome(path, arrays, **meta):
    with tifffile.TiffWriter(path, ome=True) as tif:
        for i, a in enumerate(arrays):
            tif.write(a, photometric="minisblack", metadata={"axes": "TCYX", "Name": f"field {i}", **meta})


def write_czi(path, scenes, scale=0.5e-6):
    czi = pytest.importorskip("pylibCZIrw.czi")
    with czi.create_czi(str(path)) as doc:
        for s, (a, x) in enumerate(scenes):
            for t in range(a.shape[0]):
                for c in range(a.shape[1]):
                    doc.write(data=a[t, c][..., None], plane={"T": t, "C": c}, scene=s, location=(x, 0))
        doc.write_metadata(path.stem, scale_x=scale, scale_y=scale)


def test_ome_calibration_and_interval(tmp_path):
    p, a = tmp_path / "x.ome.tif", stack()
    write_ome(p, [a], PhysicalSizeX=0.25, PhysicalSizeXUnit="µm", TimeIncrement=500, TimeIncrementUnit="ms")
    info = io.image_info(p)
    assert len(info) == 1 and info[0]["format"] == "ome-tiff" and info[0]["pixel_size"] == 0.25
    image = next(io.iter_images(p))
    assert np.array_equal(image.data, a) and image.pixel_size == pytest.approx(0.25)
    assert image.frame_interval == pytest.approx(0.5)


def test_ome_with_several_series(tmp_path):
    p = tmp_path / "x.ome.tif"
    a, b = stack(1), stack(2, h=20)
    write_ome(p, [a, b])
    assert [i["name"] for i in io.image_info(p)] == ["field 0", "field 1"]
    images = list(io.iter_images(p, [1]))
    assert len(images) == 1 and np.array_equal(images[0].data, b) and images[0].name == "x.ome - field 1"
    s = Settings()
    s.input.files = [p]
    assert [(r["series"], r["name"]) for r in sample_list(s)] == [(0, "x - field 0"), (1, "x - field 1")]


def test_plain_tiff_is_unchanged(tmp_path):
    p, a = tmp_path / "x.tif", stack()
    tifffile.imwrite(p, a, imagej=True, metadata={"axes": "TCYX", "finterval": 2.0, "unit": "um"}, resolution=(4.0, 4.0))
    assert io.image_info(p)[0]["format"] == "tiff"
    image = next(io.iter_images(p))
    assert np.array_equal(image.data, a) and image.pixel_size == pytest.approx(0.25) and image.frame_interval == 2.0


def test_czi_scenes(tmp_path):
    p = tmp_path / "x.czi"
    a, b = stack(3), stack(4)
    write_czi(p, [(a, 0), (b, 100)])
    info = io.image_info(p)
    assert [i["format"] for i in info] == ["czi", "czi"] and info[0]["pixel_size"] == 0.5
    assert (info[0]["frames"], info[0]["channels"], info[0]["height"], info[0]["width"]) == (3, 2, 32, 40)
    images = list(io.iter_images(p))
    assert len(images) == 2 and np.array_equal(images[0].data, a) and np.array_equal(images[1].data, b)
    assert images[0].pixel_size == pytest.approx(0.5) and images[0].stage_position is None
    assert np.array_equal(next(io.iter_images(p, [1])).data, b)
    assert sample_name(p) == "x"


def test_czi_single_scene_keeps_the_file_name(tmp_path):
    p = tmp_path / "one.czi"
    write_czi(p, [(stack(5), 0)])
    assert next(io.iter_images(p)).name == "one"
    s = Settings()
    s.input.files = [p]
    assert [r["name"] for r in sample_list(s)] == ["one"]


@pytest.mark.parametrize("kind", ["czi", "ome"])
def test_screening_is_refused_outside_leica_data(tmp_path, kind):
    if kind == "czi":
        p = tmp_path / "x.czi"
        write_czi(p, [(stack(), 0)])
    else:
        p = tmp_path / "x.ome.tif"
        write_ome(p, [stack()])
    s = Settings()
    s.input.files, s.input.output = [p], tmp_path / "out"
    assert not any("Leica data" in x for x in check_inputs(s))
    s.screening.enabled = True
    assert any("only available for Leica data" in x for x in check_inputs(s))
    assert screening_problems(s)
    assert issubclass(SettingsError, ValueError)


def test_screening_stays_available_for_leica_tiff(tmp_path):
    p = tmp_path / "x.tif"
    tifffile.imwrite(p, stack(), imagej=True, metadata={"axes": "TCYX"})
    s = Settings()
    s.input.files, s.input.output = [p], tmp_path / "out"
    s.screening.enabled = True
    assert not any("Leica data" in x for x in check_inputs(s)) and not screening_problems(s)
