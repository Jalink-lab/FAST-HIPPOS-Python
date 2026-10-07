"""The dashboard recomputes screening in JavaScript (templates/screening.js); it must match Python."""

import itertools
import json
from importlib import resources

import numpy as np
import pytest

from fast_hippos import events, kymograph, screening
from fast_hippos.config import Criterion, ScreeningSettings
from fast_hippos.synthetic import make_timelapse

py_mini_racer = pytest.importorskip("py_mini_racer")


@pytest.fixture(scope="module")
def js():
    ctx = py_mini_racer.MiniRacer()
    ctx.eval(resources.files("fast_hippos").joinpath("templates", "screening.js").read_text(encoding="utf-8"))
    ctx.eval("""
      function f32(a) { return Float32Array.from(a, v => v === null ? NaN : v); }
      function plain(o) { return JSON.stringify(o, (k, v) => (v instanceof Float64Array || v instanceof Uint8Array || v instanceof Float32Array)
        ? Array.from(v, x => Number.isFinite(x) ? x : (Number.isNaN(x) ? "nan" : (x > 0 ? "inf" : "-inf"))) : v); }
      function run(a) {
        const K = f32(a.K), A = a.A ? f32(a.A) : null;
        const Ks = FHScreen.smooth(K, a.T, a.N, a.p.smooth_traces);
        const m = FHScreen.metrics(Ks, a.T, a.N, a.ev, a.p, A);
        const has = m.windows.calibration[1] > m.windows.calibration[0];
        const h = FHScreen.hits(m.cols, a.N, a.p, has);
        const order = FHScreen.order(K, a.T, a.N, m.windows);
        return plain({ cols: m.cols, valid: h.valid, hit: h.hit, order, otsu: A ? FHScreen.otsuLog10(m.cols.additional_intensity) : null,
                       smooth: Array.from(Ks.slice(0, 5 * a.N)) });
      }""")
    return ctx


def _decode(values):
    return np.array([np.nan if v == "nan" else np.inf if v == "inf" else -np.inf if v == "-inf" else v for v in values], float)


@pytest.fixture(scope="module")
def data():
    _, truth = make_timelapse(seed=4, n_frames=40, stimulation=10, calibration=30)
    rng = np.random.default_rng(0)
    kymo = truth.lifetimes + rng.normal(0, 0.03, truth.lifetimes.shape).astype(np.float32)
    kymo[rng.random(kymo.shape) < 0.01] = np.nan  # some missing values
    additional = np.tile(truth.additional, (kymo.shape[0], 1)).astype(np.float32) * rng.uniform(0.9, 1.1, kymo.shape).astype(np.float32)
    return kymo.astype(np.float32), additional


EVENTS = [(10, 30, False), (10, None, False), (None, 30, False), (None, None, True), (12, 28, False)]
PARAMS = list(itertools.product(
    [-1, 3],                                    # response_window
    ["before_calibration", "after_stimulation"],
    [0, 2],                                     # response_window_margin
    [0, 2],                                     # smoothing radius
    ["OR", "AND"],
))


@pytest.mark.parametrize("ev", EVENTS)
@pytest.mark.parametrize("window,anchor,wmargin,smooth,logic", PARAMS)
def test_js_matches_python(js, data, ev, window, anchor, wmargin, smooth, logic):
    kymo, additional = data
    t, n = kymo.shape
    stim, cal, baseline_only = ev
    sc = ScreeningSettings(
        enabled=True, logic=logic, response_window=window, response_window_anchor=anchor,
        response_window_margin=wmargin, baseline_calibration_diff=(0.4, 1.0), max_baseline_deviation=0.15,
        criteria=[Criterion("response_max_diff", ">", 0.2), Criterion("rise_time_frames", "<", 6),
                  Criterion("additional_intensity", "between", 50, 1000)],
    )
    e = events.Events(t, stim, cal, baseline_only, margin=1)
    ks = kymograph.smooth_time(kymo, smooth)
    df = screening.compute_metrics(ks, e, sc, additional)
    has_cal = e.calibration_window.stop > e.calibration_window.start
    df = screening.find_hits(df, sc, has_cal)
    order = events.response_order(kymo, e)

    p = {"response_window": window, "response_window_anchor": anchor, "response_window_margin": wmargin,
         "baseline_calibration_diff": [0.4, 1.0], "max_baseline_deviation": 0.15, "rise_time_fraction": 0.75,
         "additional_channel_metric": "mean", "logic": logic, "smooth_traces": smooth,
         "criteria": [{"metric": c.metric, "op": c.op, "value": c.value, "value2": c.value2} for c in sc.criteria]}
    arg = {"K": [None if np.isnan(v) else float(v) for v in kymo.ravel()], "A": additional.ravel().tolist(),
           "T": t, "N": n, "ev": {"stimulation": stim, "calibration": cal, "baseline_only": baseline_only, "margin": 1}, "p": p}
    out = json.loads(js.call("run", arg))

    np.testing.assert_allclose(_decode(out["smooth"]), ks[:5].ravel(), rtol=0, equal_nan=True)
    for name, values in out["cols"].items():
        np.testing.assert_allclose(_decode(values), df[name].to_numpy(float), rtol=1e-9, atol=1e-12, equal_nan=True, err_msg=name)
    assert out["valid"] == df["valid"].astype(int).tolist()
    assert out["hit"] == df["hit"].astype(int).tolist()
    assert out["order"] == order.tolist()
    _, thr = screening.classify_additional(df["additional_intensity"])
    assert out["otsu"] == pytest.approx(thr, rel=1e-9)
