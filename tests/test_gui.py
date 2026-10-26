import json
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from conftest import make_result
from fast_hippos import gui
from fast_hippos.config import Criterion, Settings


def test_schema_covers_every_setting():
    sc = gui.schema()
    keys = {f["key"] for s in sc["sections"] for f in s["fields"]}
    plain = Settings().to_dict()
    assert keys == {f"{s}.{k}" for s, v in plain.items() for k in v}
    assert set(gui.FIELDS) <= keys  # no stale entries in the field table
    by_key = {f["key"]: f for s in sc["sections"] for f in s["fields"]}
    assert by_key["input.modality"]["kind"] == "select"
    assert by_key["segmentation.method"]["kind"] == "select"  # choices make a drop-down
    assert by_key["screening.criteria"]["kind"] == "criteria"
    assert by_key["input.files"]["level"] == "basic"
    assert by_key["display.min_lifetime"]["level"] == "advanced"


def test_layout_has_every_setting_once():
    placed = [k for card in gui.LAYOUT for k in card["basic"] + [k for a in card["advanced"] for k in a[1] if k != "|"]]
    keys = {f"{s}.{k}" for s, v in Settings().to_dict().items() for k in v}
    assert len(placed) == len(set(placed)), "a setting appears twice"
    assert set(placed) | set(gui.PER_SAMPLE) == keys and not set(placed) & set(gui.PER_SAMPLE)


def test_toml_round_trip(tmp_path):
    s = Settings()
    s.input.files = [tmp_path / "a b.tif"]
    s.input.output = tmp_path / "out"
    s.input.additional_channel = 3
    s.screening.enabled = True
    s.screening.baseline_calibration_diff = None  # default is a tuple: written as []
    s.screening.criteria = [Criterion("response_max_diff", ">", 0.6, logic="AND"),
                            Criterion("baseline_mean", "between", 2.0, 2.4)]
    s.segmentation.cellpose3_python = Path(r"C:\envs\cp3\python.exe")
    path = tmp_path / "settings.toml"
    path.write_text(gui.to_toml(s.to_dict()), encoding="utf-8")
    assert Settings.from_toml(path).to_dict() == s.to_dict()


def test_invalid_settings_are_reported():
    bad = Settings().to_dict()
    bad["input"]["typo"] = 1
    with pytest.raises(ValueError, match="typo"):
        gui.settings_from_plain(bad)


def test_output_info(tmp_path):
    assert gui.output_info(str(tmp_path / "missing")) == {"exists": False, "images": [], "run": None, "index": False}
    make_result(tmp_path / "img1", "img 1", source="a.tif")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "meta.json").write_text("[1, 2]")  # not a FAST-HIPPOS result: ignored, never moved
    (tmp_path / "index.html").write_text("x")
    info = gui.output_info(str(tmp_path))
    assert info["images"] == ["img1"]
    assert info["run"]["images"][0] | {} == {"name": "img 1", "folder": "img1", "source": "a.tif", "cells": 5, "index": 0}
    assert info["run"]["started"]  # from the folder itself for results without run.json
    s = Settings()
    s.input.files = [tmp_path / "img1" / "labels_corrected.tif"]  # an input inside a result folder: blocks a new run
    plan = gui.output_info(str(tmp_path), settings=s.to_dict())["plan"]
    assert plan["folders"] == ["img1"] and plan["files"] == ["index.html"]
    assert len(plan["blocked"]) == 1 and "labels_corrected.tif" in plan["blocked"][0]


def test_api_requires_token():
    server = ThreadingHTTPServer(("127.0.0.1", 0), gui.make_handler("secret", gui.Job()))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        page = urllib.request.urlopen(url + "/").read().decode()
        assert "secret" in page and "__FH_LOGO__" not in page

        def post(name, token):
            req = urllib.request.Request(f"{url}/api/{name}", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json", "X-FH-Token": token})
            return urllib.request.urlopen(req)

        with pytest.raises(urllib.error.HTTPError) as e:
            post("schema", "wrong")
        assert e.value.code == 403
        assert json.loads(post("schema", "secret").read())["sections"]
    finally:
        server.shutdown()
        server.server_close()


class FakeJob(gui.Job):
    def start(self, settings, reapply, source="gui", remember=None):
        self.started = (settings, reapply, source)
        self.remembered = remember
        return 1


def test_apply_from_dashboard(tmp_path):
    out = tmp_path / "out"
    make_result(out / "img", "img")
    base = Settings()
    base.input.files = [tmp_path / "img.tif"]
    base.input.output = out
    base.screening.criteria = [Criterion("baseline_mean", "<", 2.5)]
    base.segmentation.cellpose3_python = tmp_path / "cp3" / "python.exe"
    (out / "settings_used.json").write_text(json.dumps(base.to_dict()))
    toml = ('[screening]\nenabled = true\nmanual_hits = "img_manual_hits.tsv"\n'
            'criteria = [ { metric = "response_max_diff", op = ">", value = 0.6, logic = "AND" } ]\n')
    job = FakeJob()
    gui.apply_from_dashboard(job, str(out / "img" / "dashboard.html"), toml, "image\tcell\nimg\t3")
    settings, reapply, source = job.started
    assert reapply and source == "dashboard"
    assert settings["screening"]["criteria"][0]["metric"] == "response_max_diff"
    assert settings["segmentation"]["cellpose3_python"] == str(tmp_path / "cp3" / "python.exe")  # rest kept
    assert Path(settings["screening"]["manual_hits"]) == out / "img_manual_hits.tsv"
    assert (out / "img_manual_hits.tsv").read_text().endswith("img\t3")
    assert job.remembered is None  # a dashboard does not change the settings the GUI starts with


def test_reapply_from_the_gui_uses_the_run_in_the_folder(tmp_path):
    """Re-apply in the GUI: the images and segmentation of the run in the output folder, the screening of the page;
    the page's own settings are remembered."""
    out = tmp_path / "out"
    make_result(out / "img", "img")
    run = Settings()
    run.input.files = [tmp_path / "run_image.tif"]
    run.input.output = out
    run.segmentation.diameter = 31
    (out / "settings_used.json").write_text(json.dumps(run.to_dict()))
    page = Settings()
    page.input.files = [tmp_path / "other.tif"]  # the Images list now holds something else
    page.input.output = out
    page.segmentation.diameter = 12
    page.screening.criteria = [Criterion("baseline_mean", ">", 2.7)]
    page.display.dashboard_tiles = not run.display.dashboard_tiles  # only takes effect in a full run: the run's value stays
    job = FakeJob()
    gui.start_reapply(job, page.to_dict())
    settings, reapply, _ = job.started
    assert reapply and settings["input"]["files"] == [str(tmp_path / "run_image.tif")]
    assert settings["segmentation"]["diameter"] == 31
    assert settings["screening"]["criteria"][0]["value"] == 2.7
    assert settings["display"]["dashboard_tiles"] == run.display.dashboard_tiles
    assert job.remembered["input"]["files"] == [str(tmp_path / "other.tif")]
    with pytest.raises(ValueError, match="No analysis results"):
        gui.start_reapply(job, {**page.to_dict(), "input": {**page.to_dict()["input"], "output": str(tmp_path / "empty")}})


def test_served_files_stay_in_output_folders(tmp_path):
    job = gui.Job()
    out = tmp_path / "out"
    (out / "img").mkdir(parents=True)
    (out / "img" / "dashboard.html").write_text("<html><head></head></html>")
    (tmp_path / "secret.txt").write_text("x")

    def url(p: Path) -> str:
        return "/files/" + urllib.parse.quote(p.resolve().as_posix())

    assert gui._served(job, url(out / "img" / "dashboard.html")) is None  # folder not registered
    job.roots.add(out.resolve())
    assert gui._served(job, url(out / "img" / "dashboard.html")) == (out / "img" / "dashboard.html").resolve()
    assert gui._served(job, url(tmp_path / "secret.txt")) is None



def test_gui_is_the_default_command(monkeypatch):
    from fast_hippos import cli

    calls = []
    monkeypatch.setattr(gui, "serve", lambda port, open_browser: calls.append((port, open_browser)))
    assert cli.main([]) == 0
    assert calls == [(0, True)]


def test_enable_conditions_refer_to_settings():
    keys = {f"{s}.{k}" for s, v in Settings().to_dict().items() for k in v}
    by_key = {f["key"]: f for s in gui.schema()["sections"] for f in s["fields"]}
    for key, f in by_key.items():
        for cond_key in f.get("enable", {}):
            assert cond_key in keys, (key, cond_key)
            assert cond_key in gui.REASONS, f"no reason text for conditions on {cond_key}"
    assert set(by_key["events.stimulation_frame"]["enable"]) == {"events.baseline_only"}


def test_cellpose_check_is_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(gui, "CELLPOSE_CACHE", tmp_path / "cache.json")
    monkeypatch.setattr(gui, "STATE_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(gui, "_probe_cellpose", lambda exe: calls.append(exe) or {"cellpose": "3.1.1.2", "gpu": None})
    assert gui.check_cellpose("env/python.exe") == {"cellpose": "3.1.1.2", "gpu": None}
    assert gui.check_cellpose("env/python.exe")["cached"] is True  # instant, from the last check
    assert calls == ["env/python.exe"]
    gui.check_cellpose("env/python.exe", fresh=True)
    assert calls == ["env/python.exe"] * 2


def test_theme_is_kept_between_starts(tmp_path, monkeypatch):
    """The light / dark choice is stored in the state folder and put in the page: the browser's own storage would be
    lost, because every start uses another port."""
    monkeypatch.setattr(gui, "STATE_DIR", tmp_path)
    monkeypatch.setattr(gui, "PREFS", tmp_path / "gui_prefs.json")
    assert b'data-theme=""' in gui._page("t")  # nothing chosen: follow the system
    gui.save_prefs({"theme": "dark"})
    assert b'data-theme="dark"' in gui._page("t")
    gui.save_prefs({"theme": "<script>", "other": 1})  # only known values are stored
    assert gui.load_prefs() == {"theme": "dark"}


def test_every_setting_has_a_hover_explanation():
    keys = {f["key"] for s in gui.schema()["sections"] for f in s["fields"]}
    assert {k for k in keys if not gui.TIPS.get(k)} == set()
    assert set(gui.TIPS) <= keys  # no stale entries


def test_folded_sections_are_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(gui, "STATE_DIR", tmp_path)
    monkeypatch.setattr(gui, "PREFS", tmp_path / "gui_prefs.json")
    gui.save_prefs({"theme": "dark"})
    gui.save_prefs({"folded": ["Screening", "Run", 3]})
    assert gui.load_prefs() == {"theme": "dark", "folded": ["Screening", "Run"]}
    page = gui._page("t").decode("utf-8")
    assert '"folded": ["Screening", "Run"]' in page
    gui.save_prefs({"folded": ["</script><script>alert(1)"]})
    assert "</script><script>alert" not in gui._page("t").decode("utf-8")  # cannot break out of the data block


def test_window_shows_the_pages_in_one_tab():
    """The top bar (Setup, Experiment, Sample, Image) and the frames; the pages hand their links to the window."""
    from fast_hippos.dashboard import _dashboard_template

    page = gui._page("t").decode("utf-8")
    for view in ("setup", "overview", "image"):
        assert f'data-view="{view}"' in page
    assert 'id="fr-overview"' in page and "window.FH_SHELL" in page and 'id="selImage"' in page
    assert "window.parent.FH_SHELL" in _dashboard_template()
