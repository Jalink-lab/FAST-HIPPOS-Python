"""Gates: hit criteria that are a polygon in the plane of two metrics (drawn in the scatter plot of a dashboard).
Python (screening.in_polygon / find_hits) and the dashboard (templates/screening.js) must find the same cells."""

import json
from importlib import resources

import numpy as np
import pandas as pd
import pytest

from fast_hippos import screening
from fast_hippos.config import Criterion, ScreeningSettings, Settings

py_mini_racer = pytest.importorskip("py_mini_racer")

SQUARE = [(1, 1), (3, 1), (3, 3), (1, 3)]
CONCAVE = [(0.5, 0.5), (4, 0.6), (4, 4), (2.2, 1.5), (0.6, 4)]  # an arrow head: a dent between the two arms


@pytest.fixture(scope="module")
def js():
    ctx = py_mini_racer.MiniRacer()
    ctx.eval(resources.files("fast_hippos").joinpath("templates", "screening.js").read_text(encoding="utf-8"))
    return lambda crit, x, y: list(ctx.eval(
        f"Array.from(FHScreen.gatePass({json.dumps(crit)}, {json.dumps(x)}, {json.dumps(y)}, {len(x)}))"))


def _points(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    x, y = rng.uniform(-0.5, 5, n), rng.uniform(-0.5, 5, n)
    x[::97], y[::89] = np.nan, np.nan  # missing values
    return x, y


def _crit(polygon, op="inside", log_x=False, log_y=False):
    return Criterion("a", op, metric2="b", polygon=polygon, log_x=log_x, log_y=log_y, logic="AND")


def test_square():
    x = np.array([2, 0, 2, 3.5, np.nan, 2.999])
    y = np.array([2, 2, 0.5, 2, 2, 2.999])
    assert screening.in_polygon(x, y, SQUARE).tolist() == [True, False, False, False, False, True]


@pytest.mark.parametrize("polygon", [SQUARE, CONCAVE])
@pytest.mark.parametrize("op", ["inside", "outside"])
@pytest.mark.parametrize(("log_x", "log_y"), [(False, False), (True, False), (True, True)])
def test_python_and_dashboard_agree(js, polygon, op, log_x, log_y):
    x, y = _points()
    crit = _crit(polygon, op, log_x, log_y)
    py = screening.passes(crit, pd.DataFrame({"a": x, "b": y})).to_numpy()
    plain = lambda a: [None if np.isnan(v) else float(v) for v in a]  # JSON has no NaN
    d = screening.criterion_dict(crit, "OR")
    got = np.array(js(d, plain(x), plain(y)), bool)
    assert (py == got).all(), f"{(py != got).sum()} cells differ"
    assert 50 < py.sum() < len(x) - 50  # a real test: both classes present
    if op == "outside":  # never NaN, nor <= 0 on a log axis
        assert not py[np.isnan(x) | np.isnan(y)].any()
        if log_x:
            assert not py[x <= 0].any()


def test_concave_dent_is_outside():
    assert screening.in_polygon([3.5, 2.2, 1.5], [3.0, 3.0, 1.0], CONCAVE).tolist() == [True, False, True]


def test_log_edges_are_straight_in_log_space():
    # a triangle (1, 1) - (100, 1) - (1, 100) drawn on log axes: its long edge is log x + log y = 2
    tri = [(1, 1), (100, 1), (1, 100)]
    assert screening.in_polygon([9], [9], tri, True, True).tolist() == [True]  # 0.954 + 0.954 < 2
    assert screening.in_polygon([20], [20], tri, True, True).tolist() == [False]  # 1.30 + 1.30 > 2
    assert screening.in_polygon([20], [20], tri).tolist() == [True]  # in linear space it is inside


def test_find_hits_with_a_gate_and_a_threshold():
    x, y = _points(500, seed=2)
    df = pd.DataFrame({"a": x, "b": y, "baseline": 1.0, "calibration_response": 0.8, "baseline_offset_from_population": 0.0})
    sc = ScreeningSettings(enabled=True, baseline_calibration_diff=None, max_baseline_deviation=None,
                           criteria=[_crit(SQUARE), Criterion("a", ">", 2, logic="AND")])
    out = screening.find_hits(df, sc, has_calibration=False)
    expected = screening.in_polygon(x, y, SQUARE) & (x > 2)
    assert (out["hit"].to_numpy() == expected).all() and expected.sum() > 10


def test_criteria_on_cell_measures():
    """Criteria and gates can also use the measures of the segmentation (mean_intensity, area_(um2), circularity)."""
    from fast_hippos.config import CELL_MEASURES

    x, y = _points(400, seed=3)
    df = pd.DataFrame({"mean_intensity": np.exp(x), "peak_during_response": y, "area_(um2)": 100.0, "baseline": 1.0})
    sc = ScreeningSettings(enabled=True, baseline_calibration_diff=None, max_baseline_deviation=None, criteria=[
        Criterion("mean_intensity", "inside", metric2="peak_during_response", polygon=[(3, 1), (60, 1), (60, 3), (3, 3)],
                  log_x=True, logic="AND"),
        Criterion("area_(um2)", ">", 50.0, logic="AND")])
    out = screening.find_hits(df, sc, has_calibration=False)
    expected = screening.in_polygon(np.exp(x), y, [(3, 1), (60, 1), (60, 3), (3, 3)], log_x=True)
    assert (out["hit"].to_numpy() == expected).all() and expected.sum() > 10
    assert set(CELL_MEASURES) == {"mean_intensity", "area_(um2)", "circularity"}
    with pytest.raises(ValueError, match="circularity"):  # the message names the measures too
        screening.find_hits(df, ScreeningSettings(enabled=True, baseline_calibration_diff=None, max_baseline_deviation=None,
                                                  criteria=[Criterion("nonsense", ">", 1.0)]), False)


def test_gate_settings_round_trip(tmp_path):
    from fast_hippos.gui import to_toml

    s = Settings()
    s.screening.criteria = [_crit(CONCAVE, "outside", log_x=True), Criterion("a", "<", 3.0)]
    path = tmp_path / "s.toml"
    path.write_text(to_toml(s.to_dict()), encoding="utf-8")
    back = Settings.from_toml(path).screening.criteria
    assert back[0].op == "outside" and back[0].metric2 == "b" and back[0].log_x and not back[0].log_y
    assert [tuple(p) for p in back[0].polygon] == [tuple(map(float, p)) for p in CONCAVE]
    assert back[1].value == 3.0 and back[1].polygon is None
    assert "gate" in screening.criterion_text(back[0])


def test_unusable_gates():
    df = pd.DataFrame({"a": [1.0], "b": [1.0]})
    with pytest.raises(ValueError, match="polygon"):
        screening.passes(_crit([(0, 0), (1, 1)]), df)
    with pytest.raises(ValueError, match="value"):
        screening.passes(Criterion("a", ">"), df)


def test_area_in_square_micrometres():
    from fast_hippos.pipeline import with_area_um2

    base = pd.DataFrame({"cell": [1, 2], "area_(px)": [100, 250], "mean_intensity": [1.0, 2.0]})
    out = with_area_um2(base, 0.5)
    assert list(out.columns) == ["cell", "area_(px)", "area_(um2)", "mean_intensity"]
    assert out["area_(um2)"].tolist() == [25.0, 62.5]
    assert with_area_um2(out, 2.0)["area_(um2)"].tolist() == [25.0, 62.5]  # an existing value is kept


def test_readable_names():
    """Every cell value has a readable name (no underscores, units in brackets) and a tooltip; the keys stay."""
    from fast_hippos.config import CELL_MEASURES, METRIC_LABELS, METRIC_TIPS, METRICS, metric_label

    for key in [*METRICS, *CELL_MEASURES]:
        assert key in METRIC_LABELS and key in METRIC_TIPS, key
    assert not [n for n in METRIC_LABELS.values() if "_" in n]
    assert metric_label("area_(um2)") == "Area (µm²)"
    assert metric_label("cAMP.peak_response") == "cAMP · Peak response"
    assert metric_label("something_new") == "something new"


def test_settings_of_older_versions_get_the_new_column_names(tmp_path):
    """Before 0.1.0b3 the columns had other names (response_max_diff, area_um2): settings files that name them are
    read with the current names, also in gates, readout values and the sort / scatter choices."""
    path = tmp_path / "old.toml"
    path.write_text("""
[screening]
sort_by = "response_max_diff"
criteria = [
  { metric = "response_max_abs", op = "<", value = 3.1, logic = "AND" },
  { metric = "additional_intensity", metric2 = "cAMP.response_max_diff", op = "inside", logic = "AND", polygon = [[1, 1], [2, 1], [2, 2]] },
]
[display]
scatter_x = "area_um2"
scatter_y = "value_at_frame"
""", encoding="utf-8")
    s = Settings.from_toml(path)
    assert [c.metric for c in s.screening.criteria] == ["peak_during_response", "additional_channel_intensity"]
    assert s.screening.criteria[1].metric2 == "cAMP.peak_response"
    assert s.screening.sort_by == "peak_response"
    assert (s.display.scatter_x, s.display.scatter_y) == ("area_(um2)", "value_at_frame")


def test_results_of_older_versions_get_the_new_column_names(tmp_path):
    from fast_hippos.config import RENAMED_COLUMNS
    from fast_hippos.experiment import _current_names
    from fast_hippos.pipeline import with_area_um2

    base = pd.DataFrame({"cell": [1], "area_px": [100], "pos_x_px": [5.0], "abs_x_m": [0.01]}).rename(columns=RENAMED_COLUMNS)
    assert list(with_area_um2(base, 0.5).columns) == ["cell", "area_(px)", "area_(um2)", "position_x_(px)", "stage_x_(m)"]
    data = _current_names({"images": [{"cells": {"baseline_mean": "x", "hit": "y"}}], "response_metric": "response_max_diff",
                           "criteria": [{"metric": "rise_time_frames", "op": ">", "value": 2}], "metrics": {"calibration_diff": "d"}})
    assert set(data["images"][0]["cells"]) == {"baseline", "hit"}
    assert data["response_metric"] == "peak_response" and data["criteria"][0]["metric"] == "rise_time_(frames)"
    assert list(data["metrics"]) == ["calibration_response"]


def test_no_column_name_has_a_space():
    """Column names in the files: no spaces, units in brackets (rise_time_(frames)); the old names all map to one."""
    from fast_hippos.config import CELL_MEASURES, METRICS, RENAMED_COLUMNS

    for name in [*METRICS, *CELL_MEASURES, *RENAMED_COLUMNS.values()]:
        assert " " not in name, name
    assert set(METRICS) <= set(RENAMED_COLUMNS.values())  # every value of the response had an older name
