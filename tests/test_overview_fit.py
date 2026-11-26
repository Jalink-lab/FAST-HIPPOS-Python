"""The curve fits of the Overview's scatter plot (templates/overview/fit.js), against SciPy and known parameters."""

import json
from importlib import resources

import numpy as np
import py_mini_racer
import pytest
from scipy.optimize import curve_fit

MODELS = {
    "linear": (lambda x, a, b: a + b * x, [1.5, -0.8]),
    "exponential": (lambda x, a, b, c: a * np.exp(b * x) + c, [2.0, -1.3, 0.5]),
    "logarithmic": (lambda x, a, b: a + b * np.log(x), [0.3, 1.2]),
    "sigmoid": (lambda x, bot, top, x50, s: bot + (top - bot) / (1 + np.exp((x50 - x) / s)), [1.0, 3.0, 2.5, 0.4]),
}


@pytest.fixture(scope="module")
def js():
    ctx = py_mini_racer.MiniRacer()
    ctx.eval(resources.files("fast_hippos").joinpath("templates", "overview", "fit.js").read_text(encoding="utf-8"))
    return lambda name, x, y, w=None: ctx.eval(
        f"JSON.stringify(fitCurve({json.dumps(name)}, {json.dumps(list(map(float, x)))}, {json.dumps(list(map(float, y)))}, "
        f"{json.dumps(None if w is None else list(map(float, w)))}))")


def _data(name, n=400, noise=0.05, seed=1):
    rng = np.random.default_rng(seed)
    f, p = MODELS[name]
    x = rng.uniform(0.1, 5, n)
    return x, f(x, *p) + rng.normal(0, noise, n), p


@pytest.mark.parametrize("name", MODELS)
def test_fit_matches_scipy(js, name):
    x, y, p_true = _data(name)
    r = json.loads(js(name, x, y))
    f = MODELS[name][0]
    popt, pcov = curve_fit(f, x, y, p0=p_true, maxfev=20000)
    np.testing.assert_allclose(r["p"], popt, rtol=1e-4, atol=1e-6)
    np.testing.assert_allclose(r["se"], np.sqrt(np.diag(pcov)), rtol=1e-3)
    np.testing.assert_allclose(r["p"], p_true, rtol=0.1, atol=0.05)  # and near the truth
    resid = y - f(x, *popt)
    assert r["r2"] == pytest.approx(1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum(), rel=1e-6)
    assert r["n"] == len(x)


def test_weights_count_as_repeated_points(js):
    """A weight of 3 is the same fit as the point three times (the sample of a large image)."""
    x, y, _ = _data("sigmoid", n=120)
    w = np.where(np.arange(120) % 4 == 0, 3.0, 1.0)
    rep = np.repeat(np.arange(120), w.astype(int))
    a, b = json.loads(js("sigmoid", x, y, w)), json.loads(js("sigmoid", x[rep], y[rep]))
    np.testing.assert_allclose(a["p"], b["p"], rtol=1e-5)
    assert a["r2"] == pytest.approx(b["r2"], rel=1e-6)


def test_decreasing_sigmoid_and_rising_exponential(js):
    rng = np.random.default_rng(3)
    x = rng.uniform(0, 10, 300)
    y = 4 - 3 / (1 + np.exp((5 - x) / 0.7)) + rng.normal(0, 0.05, 300)  # from 4 down to 1
    r = json.loads(js("sigmoid", x, y))
    assert r["r2"] > 0.98 and r["p"][2] == pytest.approx(5, abs=0.1)
    y = 0.2 * np.exp(0.4 * x) + 1 + rng.normal(0, 0.05, 300)
    r = json.loads(js("exponential", x, y))
    np.testing.assert_allclose(r["p"], [0.2, 0.4, 1], rtol=0.05, atol=0.05)


def test_unusable_input(js):
    assert "too few" in json.loads(js("sigmoid", [1, 2, 3], [1, 2, 3]))["error"]
    assert "same" in json.loads(js("linear", [2] * 10, list(range(10))))["error"]
    x = np.linspace(-2, 5, 50)  # the logarithmic fit leaves out x <= 0 and NaN
    y = np.where(x > 0, 1 + 2 * np.log(np.abs(x) + 1e-9), 0.0)
    y[5] = np.nan
    r = json.loads(js("logarithmic", x, y))
    assert r["n"] == int((x > 0).sum())
    np.testing.assert_allclose(r["p"], [1, 2], atol=1e-6)
