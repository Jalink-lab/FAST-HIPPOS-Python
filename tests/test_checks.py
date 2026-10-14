import numpy as np
import pytest
import tifffile

from fast_hippos.checks import SettingsError, check_inputs
from fast_hippos.config import Modality, Settings
from fast_hippos.io import image_info, read_tiff


def _image(path, frames=6, channels=2):
    data = np.random.default_rng(0).integers(0, 100, size=(frames, channels, 16, 20), dtype=np.uint16)
    tifffile.imwrite(path, data, imagej=True, metadata={"axes": "TCYX"})
    return path


def _settings(tmp_path, **inp):
    s = Settings()
    s.input.files = [_image(tmp_path / "img.tif")]
    s.input.output = tmp_path / "out"
    s.segmentation.method = "threshold"
    for k, v in inp.items():
        setattr(s.input, k, v)
    return s


def test_image_info_matches_reading(tmp_path):
    for axes, shape in (("TCYX", (5, 3, 16, 20)), ("TYX", (5, 16, 20)), ("CYX", (2, 16, 20)), ("ZCYX", (4, 2, 16, 20))):
        p = tmp_path / f"{axes}.tif"
        tifffile.imwrite(p, np.zeros(shape, np.uint16), imagej=True, metadata={"axes": axes})
        info = image_info(p)[0]
        assert (info["frames"], info["channels"], info["height"], info["width"]) == read_tiff(p).data.shape, axes


def test_additional_channel_that_does_not_exist(tmp_path):
    s = _settings(tmp_path, additional_channel=3)  # the image has 2 channels
    problems = check_inputs(s)
    assert len(problems) == 1 and "img.tif has 2 channels" in problems[0] and "additional channel is set to 3" in problems[0]


def test_second_flim_channel_needed(tmp_path):
    s = _settings(tmp_path, intensity_channel=2, modality=Modality.TCSPC)
    assert any("needs channel 3" in p for p in check_inputs(s))
    s.input.modality = Modality.INTENSITY  # one channel is enough
    assert check_inputs(s) == []


def test_frames_and_files(tmp_path):
    s = _settings(tmp_path)
    s.events.stimulation_frame, s.events.calibration_frame = 2, 6  # the image has frames 0-5
    s.segmentation.method = "labelmap"
    s.segmentation.labelmap = tmp_path / "missing_labels.tif"
    problems = check_inputs(s)
    assert any("calibration frame is set to 6" in p for p in problems)
    assert any("Label image not found" in p for p in problems)
    s.events.baseline_only = True  # frames are then not used
    assert not any("frame is set" in p for p in check_inputs(s))
    s.input.files.append(tmp_path / "nope.tif")
    assert any("Image not found" in p for p in check_inputs(s))


def test_run_stops_before_any_work(tmp_path):
    from fast_hippos.pipeline import run

    s = _settings(tmp_path, additional_channel=3)
    with pytest.raises(SettingsError) as e:
        run(s)
    assert "additional channel" in str(e.value)
    assert not list((tmp_path / "out").glob("*/meta.json"))  # nothing was analysed
    assert "additional channel is set to 3" in (tmp_path / "out" / "run_log.txt").read_text(encoding="utf-8")
