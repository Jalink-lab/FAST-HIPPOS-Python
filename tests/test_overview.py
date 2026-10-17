import base64
import json

import numpy as np
import pandas as pd
import py_mini_racer
import pytest

from fast_hippos import overview
from fast_hippos.config import Criterion, Settings
from fast_hippos.pipeline import run
from fast_hippos.synthetic import make_timelapse, save_tiff


def test_overview_javascript_compiles():
    """All Overview modules together must parse (syntax errors, duplicate declarations between the files)."""
    from fast_hippos.dashboard import _bundle

    html = _bundle("overview", ["style.css"], overview.OVERVIEW_JS)
    src = html[html.index('"use strict";'):html.rindex("</script>")]
    py_mini_racer.MiniRacer().eval(f"new Function({json.dumps(src)}); 0")


def _payload(path):
    html = path.read_text(encoding="utf-8")
    assert "__FH_" not in html
    start = html.index('<script id="fh-data" type="application/json">') + len('<script id="fh-data" type="application/json">')
    return json.loads(html[start:html.index("</script>", start)].replace("<\\/", "</"))


@pytest.fixture(scope="module")
def run_two(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ov")
    files = []
    for k in range(2):
        image, _ = make_timelapse(size=96, n_frames=40, seed=10 + k)
        files.append(save_tiff(image, tmp / f"sample{k}.tif"))
    s = Settings()
    s.input.files = files
    s.input.output = tmp / "out"
    s.segmentation.method = "threshold"
    s.segmentation.diameter = 18
    s.screening.enabled = True
    s.screening.criteria = [Criterion("response_max_diff", ">", 0.2)]
    results = run(s)
    return s, results, tmp / "out"


def test_overview_page_and_summary(run_two):
    _, results, out = run_two
    data = _payload(out / "index.html")
    assert [i["name"] for i in data["images"]] == ["sample0", "sample1"]
    assert data["screening"] and data["response_metric"] == "response_max_diff" and data["started"]
    hits = pd.read_csv(out / "hits.tsv", sep="\t")
    for img, r in zip(data["images"], results, strict=True):
        assert img["n_hits"] == len(img["hits"]) == int((hits["image"] == r.name).sum())
        assert all(h["rank"] is not None for h in img["hits"])
        assert img["href"] == f"{r.out_dir.name}/dashboard.html" and img["thumb"].startswith("data:image/png")
        bands = np.frombuffer(base64.b64decode(img["bands"]), dtype=np.float32)
        assert bands.size == len(overview.BANDS) * r.shape[0]
        assert img["n_valid"] <= img["n_cells"] and isinstance(img["flags"], list)
        cells = np.frombuffer(base64.b64decode(img["cells"]["cell"]), dtype=np.float32)
        assert cells.size == img["n_shown"] == r.n_cells  # small images: every cell
    summary = pd.read_csv(out / overview.SUMMARY_FILE, sep="\t")
    assert list(summary["image"]) == ["sample0", "sample1"] and "hits" in summary and "qc_flags" in summary
    assert overview.SUMMARY_FILE in data["files"]


def test_sample_keeps_every_hit(monkeypatch):
    monkeypatch.setattr(overview, "MAX_CELLS", 10)
    cells = pd.DataFrame({"cell": range(1, 101), "hit": [i % 20 == 0 for i in range(100)]})
    sub = overview._subsample(cells, seed=1)
    assert len(sub) == 10 and sub["hit"].sum() == cells["hit"].sum() == 5
    many = pd.DataFrame({"cell": range(1, 101), "hit": [i % 8 == 0 for i in range(100)]})  # more hits than room
    assert overview._subsample(many, seed=1)["hit"].sum() == many["hit"].sum()


def _img(n_cells=100, n_valid=90, stim=5, cal=20, baseline_only=False, cal_delta=0.5, spread=0.05, hits=3, positions=True):
    return {"n_cells": n_cells, "n_valid": n_valid, "n_hits": hits, "has_positions": positions, "cal_delta": cal_delta,
            "baseline_spread": spread, "events": {"stimulation": stim, "calibration": cal, "baseline_only": baseline_only}}


def test_qc_flags_respect_experiments_without_stimulus():
    run = {"n_images": 3, "median_cells": 100, "with_stimulation": 2, "with_calibration": 2, "stimulation_mode": 5}
    assert overview._flags(_img(), run, True) == []
    assert overview._flags(_img(stim=None, cal=None), run, True) == ["no_stimulation", "no_calibration"]
    # most images without calibration (or a baseline-only experiment): not flagged
    few = run | {"with_calibration": 1}
    assert "no_calibration" not in overview._flags(_img(cal=None), few, True)
    assert overview._flags(_img(stim=None, cal=None, baseline_only=True), run, True) == []
    assert overview._flags(_img(stim=12), run, True) == ["event_offset"]
    assert overview._flags(_img(cal_delta=0.01), run, True) == ["no_cal_response"]
    assert overview._flags(_img(n_cells=10, n_valid=3), run, True)[:2] == ["few_cells", "low_valid"]
    assert overview._flags(_img(hits=0, positions=False), run, True) == ["no_positions", "no_hits"]
    assert overview._flags(_img(hits=0, positions=False), run, False) == []  # no screening: no hit flags
    assert overview._level("low_valid", _img(n_valid=30)) == "bad"


def test_overview_without_screening(tmp_path):
    """Without screening the page compares the samples: no hits, no hit columns in the summary, no hit flags."""
    image, _ = make_timelapse(size=96, n_frames=40, seed=21)
    s = Settings()
    s.input.files = [save_tiff(image, tmp_path / "a.tif")]
    s.input.output = tmp_path / "out"
    s.segmentation.method = "threshold"
    s.segmentation.diameter = 18
    run(s)
    data = _payload(tmp_path / "out" / "index.html")
    assert not data["screening"] and data["images"][0]["hits"] == [] and data["chunks"] == []
    assert all(f["key"] not in ("no_hits", "no_positions") for f in data["images"][0]["flags"])
    summary = pd.read_csv(tmp_path / "out" / overview.SUMMARY_FILE, sep="\t")
    assert "hits" not in summary.columns and len(summary) == 1
