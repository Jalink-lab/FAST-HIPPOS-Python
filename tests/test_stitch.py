import xml.etree.ElementTree as ET

import numpy as np
import pytest
import tifffile

from fast_hippos import stage, stitch
from fast_hippos.io import image_info

TILE = 16  # px
PX = 1.0  # µm


def _scene(t=2, c=2, h=80, w=96, seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 1000, size=(t, c, h, w), dtype=np.uint16)


def _leica_xml(offsets, flags=(1, 1, 1), tile=TILE):
    """LAS X MetaData .xml for tiles at the given (x, y) pixel offsets. With FlipX = FlipY = SwapXY = 1 (as on the
    Stellaris) Leica PosX runs along image x and PosY along image y."""
    tiles = "".join(f'<Tile FieldX="{k}" FieldY="0" PosX="{0.06 + x * PX * 1e-6:.10f}" PosY="{0.04 + y * PX * 1e-6:.10f}"/>'
                    for k, (x, y) in enumerate(offsets))
    fx, fy, sw = flags
    return (f'<Data><Image><ImageDescription><Dimensions>'
            f'<DimensionDescription DimID="1" NumberOfElements="{tile}" Length="{tile * PX * 1e-6}" Unit="m"/>'
            f'<DimensionDescription DimID="2" NumberOfElements="{tile}" Length="{tile * PX * 1e-6}" Unit="m"/>'
            f'</Dimensions></ImageDescription>'
            f'<Attachment Name="TileScanInfo" FlipX="0" FlipY="0" SwapXY="0">{tiles}</Attachment>'
            f'<Attachment Name="HardwareSetting"><ATLConfocalSettingDefinition FlipX="{fx}" FlipY="{fy}" SwapXY="{sw}" '
            f'StagePosX="0.06" StagePosY="0.04"/></Attachment></Image></Data>')


def _tile_folder(tmp_path, scene, offsets, metadata=True):
    folder = tmp_path / "tiles"
    folder.mkdir()
    for k, (x, y) in enumerate(offsets):
        tifffile.imwrite(folder / f"scan_s{k}.tif", scene[..., y : y + TILE, x : x + TILE], imagej=True,
                         metadata={"axes": "TCYX", "finterval": 2.5})
    if metadata:
        (folder / "MetaData").mkdir()
        (folder / "MetaData" / "scan.xml").write_text(_leica_xml(offsets))
        (folder / "MetaData" / "scan_properties.xml").write_text("<Properties/>")
    return folder


# 3 x 2 tiles, snake by rows, the last row shifted by 3 px (irregular: not a grid)
SNAKE = [(0, 0), (16, 0), (32, 0), (35, 16), (19, 16), (3, 16)]


def test_ome_position():
    assert stitch.ome_position(1.0, 2.0, False, False, False) == (1.0, 2.0)
    assert stitch.ome_position(1.0, 2.0, True, True, True) == (-2.0, -1.0)  # swap first, then flip
    assert stitch.ome_position(1.0, 2.0, True, False, True) == (-2.0, 1.0)


def test_find_tiles_in_numeric_order(tmp_path):
    for k in (0, 1, 2, 10, 11):
        (tmp_path / f"scan_s{k}.tif").touch()
    (tmp_path / "scan_STITCHED.tif").touch()
    assert [p.name for p in stitch.find_tiles(tmp_path)] == [f"scan_s{k}.tif" for k in (0, 1, 2, 10, 11)]


def test_stitch_places_tiles_by_stage_position(tmp_path):
    scene = _scene()
    folder = _tile_folder(tmp_path, scene, SNAKE)
    image = stitch.stitch_folder(folder)
    assert image.name == "scan_STITCHED"
    assert image.data.shape == (2, 2, 32, 51)
    assert image.pixel_size == pytest.approx(PX) and image.frame_interval == pytest.approx(2.5)
    for x, y in SNAKE:
        assert np.array_equal(image.data[..., y : y + TILE, x : x + TILE], scene[..., y : y + TILE, x : x + TILE])
    assert not image.data[..., 16:, :3].any()  # not covered by any tile
    info = stage.parse_stitched_info(image.info)
    assert info.n_tiles == (3, 2)
    assert info.tile_size == pytest.approx((TILE * PX * 1e-6,) * 2)
    assert info.bidirectional is None
    # the positions as Bio-Formats gives them: (-PosY, -PosX) for FlipX = FlipY = SwapXY = 1
    assert info.positions[1] == pytest.approx((-0.04, -(0.06 + 16e-6)))
    # positions saved next to the tiles and used from then on, also without the MetaData folder
    assert (folder / stitch.TILE_POSITIONS).exists()
    for f in (folder / "MetaData").iterdir():
        f.unlink()
    (folder / "MetaData").rmdir()
    again = stitch.stitch_folder(folder)
    assert np.array_equal(again.data, image.data) and again.info == image.info
    assert (image_info(folder)[0]["width"], image_info(folder)[0]["height"]) == (51, 32)


def test_cell_positions_same_as_in_own_tile(tmp_path):
    """The stage position of a pixel in the stitched image equals that of the same pixel in its own tile."""
    folder = _tile_folder(tmp_path, _scene(), SNAKE)
    info = stage.parse_stitched_info(stitch.stitch_folder(folder).info)
    for k, (x, y) in enumerate(SNAKE):
        in_tile = np.array([[2.0, 5.0], [15.0, 0.0]])
        expected = stage.absolute_positions(in_tile, info.positions[k], info.tile_size, PX)
        stitched = stage.absolute_positions(in_tile + (x, y), np.array(info.origin_xy), info.tile_size, PX)
        assert stitched == pytest.approx(expected, abs=1e-12)


def test_overlapping_tiles(tmp_path):
    scene = _scene()
    offsets = [(0, 0), (12, 0), (24, 0)]  # 4 px (25 %) overlap
    image = stitch.stitch_folder(_tile_folder(tmp_path, scene, offsets))
    assert image.data.shape[-2:] == (16, 40)
    assert np.array_equal(image.data, scene[..., :16, :40])
    assert stage.parse_stitched_info(image.info).overlap == pytest.approx(0.25)


def test_positions_file_must_match_tiles(tmp_path):
    folder = _tile_folder(tmp_path, _scene(), SNAKE)
    stitch.tile_layout(folder)
    (folder / "scan_s5.tif").unlink()
    with pytest.raises(ValueError, match="other tiles"):
        stitch.tile_layout(folder)


def test_no_positions(tmp_path):
    folder = _tile_folder(tmp_path, _scene(), SNAKE, metadata=False)
    with pytest.raises(ValueError, match="No tile positions"):
        stitch.stitch_folder(folder)


def test_flags_from_parent_image():
    """As in a .lif: the FLIM results of a tile scan are child images without scanner settings of their own."""
    xml = _leica_xml([(0, 0), (16, 0)])
    child = xml.replace("<Data>", '<Element Name="FLIM"><Data>').replace("</Data>", "</Data></Element>")
    child = child.replace(
        '<Attachment Name="HardwareSetting"><ATLConfocalSettingDefinition FlipX="1" FlipY="1" SwapXY="1" '
        'StagePosX="0.06" StagePosY="0.04"/></Attachment>', "")
    root = ET.fromstring(f'<LMSDataContainerHeader><Element Name="scan"><Data><Image><Attachment Name="HardwareSetting">'
                         f'<ATLConfocalSettingDefinition FlipX="1" FlipY="1" SwapXY="1" StagePosX="0.06" StagePosY="0.04"/>'
                         f'</Attachment></Image></Data><Children>{child}</Children></Element></LMSDataContainerHeader>')
    scans = stitch._tile_scans(root)
    assert [(s.name, s.tiled) for s in scans] == [("scan", False), ("scan/FLIM", True)]
    assert scans[0].positions.tolist() == [[-0.04, -0.06]]
    assert scans[1].positions[1] == pytest.approx((-0.04, -(0.06 + 16e-6)))
    assert stitch._pick(scans, 2, "test") is scans[1]


def test_bidirectional_correction_per_tile(tmp_path):
    """Return scan lines (odd columns, fast scan axis vertical) 1.6 px off along y in every tile: measured once over
    all tiles, corrected per tile, and recorded so that the analysis does not correct the stitched image again."""
    size, tile = 96, 48
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    centres = np.random.default_rng(0).uniform(8, size - 8, size=(30, 2))

    def scene(dy):
        return sum(1000 * np.exp(-((yy - dy - cy) ** 2 + (xx - cx) ** 2) / 18) for cy, cx in centres)

    img = scene(0)
    img[:, 1::2] = scene(1.6)[:, 1::2]
    folder = tmp_path / "tiles"
    folder.mkdir()
    offsets = [(0, 0), (tile, 0), (tile, tile), (0, tile)]
    for k, (x, y) in enumerate(offsets):
        t = img[y : y + tile, x : x + tile]
        tifffile.imwrite(folder / f"scan_s{k}.tif", np.stack([t, t])[:, None].astype(np.uint16), imagej=True,
                         metadata={"axes": "TCYX"})
    (folder / "MetaData").mkdir()
    (folder / "MetaData" / "scan.xml").write_text(_leica_xml(offsets, tile=tile))
    image = stitch.stitch_folder(folder, bidirectional="y")
    assert abs(stage.parse_stitched_info(image.info).bidirectional) == pytest.approx(1.6, abs=0.1)
    assert image.data.dtype == np.uint16 and image.data.min() >= 0  # the type of the tiles is kept
    from fast_hippos.preprocess import estimate_bidirectional_shift

    assert abs(estimate_bidirectional_shift(image.data[:, 0], "y")) < 0.15  # aligned after correction


def test_run_on_tile_folder(tmp_path):
    """A tile folder as input: stitched, saved, analyzed, and the cells get the stage positions of their tiles."""
    from fast_hippos.config import Criterion, Settings
    from fast_hippos.pipeline import run
    from fast_hippos.synthetic import make_timelapse

    image, _ = make_timelapse(size=128, n_frames=40, seed=1)
    tile = 64
    offsets = [(0, 0), (tile, 0), (tile, tile), (0, tile)]
    folder = tmp_path / "tiles"
    folder.mkdir()
    for k, (x, y) in enumerate(offsets):
        tifffile.imwrite(folder / f"scan_s{k}.tif", image.data[..., y : y + tile, x : x + tile], imagej=True,
                         metadata={"axes": "TCYX", "finterval": image.frame_interval})
    (folder / "MetaData").mkdir()
    (folder / "MetaData" / "scan.xml").write_text(_leica_xml(offsets, tile=tile))
    s = Settings()
    s.input.files = [folder]
    s.input.output = tmp_path / "out"
    s.segmentation.method = "threshold"
    s.segmentation.diameter = 18
    s.screening.enabled = True
    s.screening.criteria = [Criterion("response_max_diff", ">", 0.2)]
    (r,) = run(s)
    assert r.name == "scan_STITCHED" and r.shape[1:] == (128, 128)
    assert (tmp_path / "out" / "scan_STITCHED.tif").exists()
    # with these flags image x runs along Leica PosX and y along PosY; the stitched image starts at the first tile
    cells = r.cells
    np.testing.assert_allclose(cells["abs_x_m"], 0.06 - tile / 2 * 1e-6 + cells["pos_x_px"] * 1e-6, atol=1e-12)
    np.testing.assert_allclose(cells["abs_y_m"], 0.04 - tile / 2 * 1e-6 + cells["pos_y_px"] * 1e-6, atol=1e-12)
    assert len(r.tiles) == 4
    (again,) = run(s, reapply=True)  # the saved results keep the stage geometry
    np.testing.assert_allclose(again.cells["abs_x_m"], cells["abs_x_m"])


def test_single_tiff_position_from_lasx_metadata(tmp_path):
    """A tile of an exported tile scan, analyzed on its own, gets its tile's stage position and the exact pixel size;
    an image with one position (e.g. stitched by LAS X) gets that one."""
    from fast_hippos.io import read_tiff

    folder = _tile_folder(tmp_path, _scene(), SNAKE)
    image = read_tiff(folder / "scan_s4.tif")
    assert image.stage_position == pytest.approx((-(0.04 + 16e-6), -(0.06 + 19e-6)))
    assert image.pixel_size == pytest.approx(PX)
    info = image_info(folder / "scan_s4.tif")[0]
    assert info["positions"] and info["pixel_size"] == pytest.approx(PX)
    single = tmp_path / "single"
    (single / "MetaData").mkdir(parents=True)
    tifffile.imwrite(single / "merged.tif", _scene()[..., :32, :32], imagej=True, metadata={"axes": "TCYX"})
    (single / "MetaData" / "merged.xml").write_text(_leica_xml([(5, 7)]))
    assert read_tiff(single / "merged.tif").stage_position == pytest.approx((-(0.04 + 7e-6), -(0.06 + 5e-6)))
    tifffile.imwrite(single / "other.tif", _scene()[..., :32, :32], imagej=True, metadata={"axes": "TCYX"})
    assert read_tiff(single / "other.tif").stage_position is None
    assert not image_info(single / "other.tif")[0]["positions"]


def _run_tile(tmp_path, positions_file=None):
    from fast_hippos.config import Settings
    from fast_hippos.pipeline import run
    from fast_hippos.synthetic import make_timelapse

    image, _ = make_timelapse(size=64, n_frames=30, seed=2)
    folder = tmp_path / "export"
    (folder / "MetaData").mkdir(parents=True)
    tifffile.imwrite(folder / "field.tif", image.data, imagej=True, metadata={"axes": "TCYX"})
    (folder / "MetaData" / "field.xml").write_text(_leica_xml([(0, 0)], tile=64))
    s = Settings()
    s.input.files = [folder / "field.tif"]
    s.input.output = tmp_path / "out"
    s.segmentation.method = "threshold"
    s.segmentation.diameter = 18
    s.screening.enabled = True
    s.screening.random_hits = 3
    s.screening.stage_positions_file = positions_file
    (r,) = run(s)
    return r


def test_run_uses_position_from_image_and_text_file_overrides(tmp_path):
    r = _run_tile(tmp_path / "a")
    assert r.stage_xy == pytest.approx((-0.04, -0.06))  # from MetaData/field.xml
    text = tmp_path / "positions.txt"
    text.write_text("0.0123 0.0456\n")
    assert _run_tile(tmp_path / "b", text).stage_xy == pytest.approx((0.0123, 0.0456))
