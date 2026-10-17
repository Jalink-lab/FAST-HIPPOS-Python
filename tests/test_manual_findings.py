"""Fixes from the manual test run (docs/manual_test_findings.md): gates per image type, one frame set, no calibration,
the stage positions file check, the settings file of a run, _previous_run."""

import numpy as np
import pytest

from fast_hippos import events, stage
from fast_hippos.config import EventSettings, Settings


def test_default_gates_are_lifetimes_off_for_ratio_and_intensity():
    assert Settings.from_dict({}).screening.baseline_calibration_diff == (0.5, 1.0)  # TCSPC: in ns
    for modality in ("ratio", "intensity"):
        s = Settings.from_dict({"input": {"modality": modality}})
        assert s.screening.baseline_calibration_diff is None and s.screening.max_baseline_deviation is None
    s = Settings.from_dict({"input": {"modality": "ratio"}, "screening": {"baseline_calibration_diff": [0.1, 0.9]}})
    assert s.screening.baseline_calibration_diff == (0.1, 0.9) and s.screening.max_baseline_deviation is None


def _trace(n=50, s=15, c=40, transient=False):
    t = np.arange(n, dtype=float)
    y = np.where(t >= s, 1.0, 0.0)
    if transient:
        y = np.where(t >= s, np.exp(-(t - s) / 3.0), 0.0)
    else:
        y = y + np.where(t >= c, 1.0, 0.0)
    return y + np.random.default_rng(0).normal(0, 0.005, n)


def test_one_frame_set_detects_the_other():
    ev = events.determine(_trace(), EventSettings(stimulation_frame=15))
    assert (ev.stimulation, ev.calibration) == (15, 40)
    ev = events.determine(_trace(), EventSettings(calibration_frame=40))
    assert (ev.stimulation, ev.calibration) == (15, 40)


def test_no_calibration():
    tr = _trace(transient=True)
    ev = events.determine(tr, EventSettings(no_calibration=True))
    assert ev.stimulation == 15 and ev.calibration is None and ev.response.stop == len(tr)
    ev = events.determine(tr, EventSettings(stimulation_frame=15, no_calibration=True))
    assert (ev.stimulation, ev.calibration) == (15, None)


def test_positions_file_header_and_errors(tmp_path):
    f = tmp_path / "pos.txt"
    f.write_text("x\ty\n0.001\t0.002\n0.003, 0.004\n")
    assert stage.read_positions_file(f).tolist() == [[0.001, 0.002], [0.003, 0.004]]
    f.write_text("0.001 0.002\n0.003\n")
    with pytest.raises(ValueError, match="X and Y"):
        stage.read_positions_file(f)
    f.write_text("0.001 0.002\nfoo bar\n")
    with pytest.raises(ValueError, match="line 2"):
        stage.read_positions_file(f)


def test_too_few_stage_positions_is_a_problem_before_the_run(tmp_path):
    from fast_hippos.checks import check_inputs
    from fast_hippos.synthetic import make_timelapse, save_tiff

    image, _ = make_timelapse(size=64, n_frames=10, seed=1)
    s = Settings()
    s.input.files = [save_tiff(image, tmp_path / f"im{k}.tif") for k in range(2)]
    s.screening.enabled = True
    s.screening.stage_positions_file = tmp_path / "pos.txt"
    s.screening.stage_positions_file.write_text("0.001 0.002\n")
    assert any("1 position for 2 images" in p for p in check_inputs(s))


def test_a_run_writes_its_settings_file_and_no_empty_previous_run(tmp_path):
    from fast_hippos.pipeline import PREVIOUS_RUN, clear_run, run
    from fast_hippos.synthetic import make_timelapse, save_tiff

    out = tmp_path / "out"
    out.mkdir()
    assert clear_run(out) == [] and not (out / PREVIOUS_RUN).exists()  # nothing to move: no _previous_run
    image, _ = make_timelapse(size=64, n_frames=20, seed=2)
    s = Settings()
    s.input.files = [save_tiff(image, tmp_path / "im.tif")]
    s.input.output = out
    s.segmentation.method = "threshold"
    s.segmentation.diameter = 18
    run(s)
    assert Settings.from_toml(out / "fast_hippos_settings.toml").segmentation.method == "threshold"
