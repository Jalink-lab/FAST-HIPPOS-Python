import json
import threading
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
    assert gui.output_info(str(tmp_path / "missing")) == {"exists": False, "images": []}
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
