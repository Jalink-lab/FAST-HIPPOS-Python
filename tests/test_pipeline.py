import numpy as np
import pandas as pd
import pytest

from fast_hippos import events, kymograph, modalities, screening, stage
from fast_hippos.config import Criterion, EventSettings, Modality, ScreeningSettings, Settings
from fast_hippos.pipeline import run
from fast_hippos.synthetic import make_timelapse, save_tiff


@pytest.fixture(scope="module")
def synthetic():
    return make_timelapse(seed=1)


def test_tcspc_pooled_lifetime_is_unbiased(synthetic):
    image, truth = synthetic  # low counts (~40 photons/pixel)
    intensity, lifetime = modalities.tcspc(image.channel(1), image.channel(2), 0.6, 3.4)
    pooled = kymograph.cell_values(intensity, lifetime, truth.labels, Modality.TCSPC)
    assert pooled.shape == truth.lifetimes.shape
    err = pooled - truth.lifetimes
    assert abs(np.nanmean(err)) < 0.005  # unbiased
    assert np.nanstd(err) < 0.025  # photon noise only
    # the Fiji estimator (intensity-weighted mean of pixel lifetimes) is biased upward and noisier (issue I19)
    fiji_err = kymograph.weighted_lifetime(intensity, lifetime, truth.labels) - truth.lifetimes
    assert np.nanmean(fiji_err) > 0.02
    assert np.nanstd(fiji_err) > np.nanstd(err)


def test_ratio_pooled():
    labels = np.array([[1, 1], [2, 2]])
    c1 = np.array([[[10.0, 30.0], [5.0, 5.0]]])
    c2 = np.array([[[10.0, 10.0], [10.0, 0.0]]])
    intensity, ratio = modalities.ratio(c1, c2)
    values = kymograph.cell_values(intensity, ratio, labels, Modality.RATIO)
    np.testing.assert_allclose(values[0], [40 / 20, 5 / 10])  # sum(C1) / sum(C2); pixels with a zero are excluded


def test_event_detection(synthetic):
    image, truth = synthetic
    intensity, lifetime = modalities.tcspc(image.channel(1), image.channel(2), 0.6, 3.4)
    kymo = kymograph.cell_values(intensity, lifetime, truth.labels, Modality.TCSPC)
    ev = events.determine(kymograph.population_mean(kymo), EventSettings())
    assert (ev.stimulation, ev.calibration) == (truth.stimulation, truth.calibration)
    assert ev.baseline == slice(0, truth.stimulation - 1)
    assert ev.response == slice(truth.stimulation, truth.calibration - 1)


def test_screening_finds_responders(synthetic):
    _, truth = synthetic
    ev = events.Events(truth.lifetimes.shape[0], truth.stimulation, truth.calibration)
    sc = ScreeningSettings(enabled=True, criteria=[Criterion("response_max_diff", ">", 0.2)])
    df = screening.compute_metrics(truth.lifetimes, ev, sc)
    df = screening.find_hits(df, sc, has_calibration=True)
    assert (df["hit"].to_numpy() == truth.responders).mean() > 0.95


def test_and_logic_with_zero_metric():
    df = pd.DataFrame({"baseline_mean": [0.0, 1.0], "calibration_diff": [0.7, 0.7], "baseline_dev_pop": [0, 0],
                       "response_max_diff": [0.5, 0.5]})
    sc = ScreeningSettings(enabled=True, logic="AND", max_baseline_deviation=None, criteria=[
        Criterion("baseline_mean", "<", 0.5), Criterion("response_max_diff", ">", 0.2)])
    out = screening.find_hits(df, sc, has_calibration=True)
    assert out["hit"].tolist() == [True, False]  # a true value of 0 must not fail (issue I7)


def test_two_opt_improves_path():
    rng = np.random.default_rng(0)
    pts = rng.random((200, 2))
    nn = stage.nearest_neighbour_path(pts)
    opt = stage.two_opt(pts, nn, max_time=5)
    assert sorted(opt) == list(range(200))
    assert stage.path_length(pts, opt) < stage.path_length(pts, nn)


def test_stitched_info_roundtrip():
    info = stage.StageInfo(np.array([[0.01, 0.02], [0.011, 0.02]]), (2, 1), (1e-4, 1e-4), 0.1)
    parsed = stage.parse_stitched_info(stage.stitched_info_block(info))
    assert parsed.n_tiles == (2, 1)
    np.testing.assert_allclose(parsed.positions, info.positions)
    np.testing.assert_allclose(parsed.tile_size, info.tile_size)
    assert parsed.overlap == pytest.approx(0.1)


def test_full_run(tmp_path, synthetic):
    image, truth = synthetic
    positions = tmp_path / "stage.txt"
    positions.write_text("0.0123\n0.0456\n")
    src = save_tiff(image, tmp_path / "synthetic.tif")
    settings = Settings()
    settings.input.files = [src]
    settings.input.output = tmp_path / "out"
    settings.input.additional_channel = 3
    settings.segmentation.method = "threshold"
    settings.segmentation.diameter = 18
    settings.segmentation.min_cell_size = 30
    settings.screening.enabled = True
    settings.screening.criteria = [Criterion("response_max_diff", ">", 0.2)]
    settings.screening.stage_positions_file = positions
    settings.screening.classify_additional_channel = True
    results = run(settings)
    assert len(results) == 1
    r = results[0]
    assert (r.events.stimulation, r.events.calibration) == (truth.stimulation, truth.calibration)
    assert abs(r.n_cells - truth.labels.max()) <= 3
    # hits should be the responders: look up the true label at each cell's centroid
    cells = r.cells
    true_label = truth.labels[cells["centroid_y"].round().astype(int), cells["centroid_x"].round().astype(int)]
    agreement = (cells["hit"].to_numpy() == truth.responders[true_label - 1]).mean()
    assert agreement > 0.9
    out = tmp_path / "out"
    for name in ["hits.tsv", "cell_coordinates.tsv", "index.html", "HITS_synthetic.rgn", "hit_positions.png"]:
        assert (out / name).exists(), name
    assert (r.out_dir / "dashboard.html").exists()
    # re-apply with a different criterion uses the saved data
    settings.screening.criteria = [Criterion("response_max_diff", ">", 0.6)]
    again = run(settings, reapply=True)
    assert again[0].cells["hit"].sum() < cells["hit"].sum()


def test_settings_override(tmp_path):
    base = tmp_path / "config.toml"
    base.write_text('[input]\nfiles = ["a.tif"]\n[events]\nstimulation_frame = 6\n[screening]\nenabled = false\n'
                    'criteria = [{ metric = "baseline_mean", op = "<", value = 2.5 }]\n')
    override = tmp_path / "screening.toml"
    override.write_text('[events]\nstimulation_frame = ""\n[screening]\nenabled = true\nbaseline_calibration_diff = []\n'
                        'criteria = [{ metric = "response_max_diff", op = ">", value = 0.3 }]\n')
    s = Settings.from_toml(base, overrides=[override])
    assert s.events.stimulation_frame is None  # "" clears a value
    assert s.screening.enabled and s.screening.baseline_calibration_diff is None
    assert [c.metric for c in s.screening.criteria] == ["response_max_diff"]  # lists are replaced
    assert s.input.files[0].name == "a.tif"  # untouched sections are kept


def test_mixed_and_or_criteria():
    df = pd.DataFrame({"baseline_mean": [2.0, 2.0, 2.0, 3.0], "calibration_diff": 0.7, "baseline_dev_pop": 0.0,
                       "response_max_diff": [0.5, 0.1, 0.1, 0.5], "rise_time_frames": [9, 2, 9, 2]})
    sc = ScreeningSettings(enabled=True, logic="OR", max_baseline_deviation=None, criteria=[
        Criterion("baseline_mean", "<", 2.5, logic="AND"),
        Criterion("response_max_diff", ">", 0.3), Criterion("rise_time_frames", "<", 5)])
    out = screening.find_hits(df, sc, has_calibration=True)
    # baseline required; then fast OR large response
    assert out["hit"].tolist() == [True, True, False, False]


def test_manual_hits(tmp_path):
    f = tmp_path / "hits.tsv"
    f.write_text("image\tcell\nimgA\t2\nimgB\t3\nimgA\t4\n")
    hits = screening.manual_hits(f, "imgA", pd.Series([1, 2, 3, 4]))
    assert hits.tolist() == [False, True, False, True]
