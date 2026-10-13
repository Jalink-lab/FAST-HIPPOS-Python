import json
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

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
    placed = [k for card in gui.LAYOUT for k in card["basic"] + [k for a in card["advanced"] for k in a[1]]]
    keys = {f"{s}.{k}" for s, v in Settings().to_dict().items() for k in v}
    assert len(placed) == len(set(placed)), "a setting appears twice"
    assert set(placed) == keys


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
    assert gui.output_info(str(tmp_path / "missing")) == {"exists": False, "images": [], "index": False}
    (tmp_path / "img1").mkdir()
    (tmp_path / "img1" / "traces.npz").write_bytes(b"")
    assert gui.output_info(str(tmp_path))["images"] == ["img1"]


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
    def start(self, settings, reapply, source="gui"):
        self.started = (settings, reapply, source)
        return 1


def test_apply_from_dashboard(tmp_path):
    out = tmp_path / "out"
    (out / "img").mkdir(parents=True)
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
