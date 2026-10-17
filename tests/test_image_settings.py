"""Settings of single images (Settings.image): stimulation settings and response window that differ per image."""

import json

import pandas as pd
import pytest
import tomllib

from fast_hippos import gui, overview
from fast_hippos.config import Settings
from fast_hippos.pipeline import reapply_settings, run
from fast_hippos.synthetic import make_timelapse, save_tiff


def test_parse_check_and_merge(tmp_path):
    cfg = tmp_path / "s.toml"
    cfg.write_text('[events]\nstimulation_frame = 5\n\n[image."Cos7 A".events]\nstimulation_frame = 148\ncalibration_frame = 1052\n\n'
                   '[image."Cos7 A".screening]\nresponse_window = 20\n\n[image."B".events]\nstimulation_frame = ""\n')
    s = Settings.from_toml(cfg)
    assert s.image == {"Cos7 A": {"events": {"stimulation_frame": 148, "calibration_frame": 1052}, "screening": {"response_window": 20}},
                       "B": {"events": {"stimulation_frame": None}}}
    a = s.for_image("Cos7 A")
    assert (a.events.stimulation_frame, a.events.calibration_frame, a.screening.response_window) == (148, 1052, 20)
    assert s.for_image("other") is s and s.events.stimulation_frame == 5  # the settings themselves are not changed
    assert s.for_image("B").events.stimulation_frame is None  # '' = detect automatically for this image
    with pytest.raises(ValueError, match="criteria cannot differ per image"):
        Settings.from_dict({"image": {"x": {"screening": {"criteria": []}}}})
    with pytest.raises(ValueError, match="only events and screening"):
        Settings.from_dict({"image": {"x": {"segmentation": {"diameter": 3}}}})
    # the GUI writes them back as TOML tables that read the same
    text = gui.to_toml(s.to_dict())
    assert '[image."Cos7 A".events]' in text
    assert Settings.from_dict(tomllib.loads(text)).image == s.image


@pytest.fixture(scope="module")
def two_images(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("own")
    files = []
    for k in range(2):
        image, _ = make_timelapse(size=96, n_frames=40, seed=30 + k)
        files.append(save_tiff(image, tmp / f"img{k}.tif"))
    s = Settings()
    s.input.files = files
    s.input.output = tmp / "out"
    s.segmentation.method = "threshold"
    s.segmentation.diameter = 18
    s.screening.enabled = True
    s.image = {"img1": {"events": {"stimulation_frame": 12, "calibration_frame": 33}}}
    return s, run(s), tmp / "out"


def test_run_uses_own_settings_of_one_image(two_images):
    s, results, out = two_images
    r0, r1 = results
    assert r0.events.detected and r0.events.stimulation != 12
    assert (r1.events.stimulation, r1.events.calibration, r1.events.detected) == (12, 33, False)
    assert json.loads((out / "settings_used.json").read_text())["image"] == s.image
    log = (out / "run_log.txt").read_text(encoding="utf-8")
    assert "Own settings of this image: stimulation_frame 12, calibration_frame 33" in log
    # shown in the overview and its table
    html = (out / "index.html").read_text(encoding="utf-8")
    data = json.loads(html[html.index('type="application/json">') + 24:html.index("</script>", html.index('type="application/json">'))].replace("<\\/", "</"))
    assert data["images"][0]["own"] is None and data["images"][1]["own"] == s.image["img1"]
    summary = pd.read_csv(out / overview.SUMMARY_FILE, sep="\t", keep_default_na=False)
    assert list(summary["own_settings"]) == ["", "stimulation_frame=12; calibration_frame=33"]
    dash = (out / "img1" / "dashboard.html").read_text(encoding="utf-8")
    assert '"own_settings":{"events":{"stimulation_frame":12,"calibration_frame":33}}' in dash


class FakeJob(gui.Job):
    def start(self, settings, reapply, source="gui", remember=None):
        self.started = (settings, reapply, source)
        return 1


def test_reapply_keeps_or_replaces_image_settings(two_images):
    s, _, out = two_images
    assert reapply_settings(out, {"screening": {"logic": "AND"}})["image"] == s.image  # kept
    assert reapply_settings(out, {"image": {}})["image"] == {}  # the GUI removed them


def test_apply_to_this_image_only_and_to_all_images(two_images, monkeypatch, tmp_path):
    _, _, out = two_images
    monkeypatch.setattr(gui, "LAST_SETTINGS", tmp_path / "last.toml")
    job = FakeJob()
    dash = str(out / "img0" / "dashboard.html")
    # this image only: just the per-image settings of the dashboard become img0's; img1 keeps its own
    toml = "[events]\nstimulation_frame = 7\ncalibration_frame = 30\nbaseline_only = false\nmargin = 1\n\n[screening]\nresponse_window = 4\nlogic = \"AND\"\n"
    gui.apply_from_dashboard(job, dash, toml, image="img0", scope="image")
    settings, reapply, source = job.started
    assert reapply and source == "dashboard"
    assert settings["image"]["img0"] == {"events": {"stimulation_frame": 7, "calibration_frame": 30, "baseline_only": False, "margin": 1},
                                         "screening": {"response_window": 4}}
    assert settings["image"]["img1"]["events"]["stimulation_frame"] == 12
    assert settings["screening"]["logic"] != "AND" and settings["events"]["stimulation_frame"] is None  # nothing else changed
    # all images, with a timing set in the dashboard of img1: the timing holds for all, and replaces img1's own timing
    gui.apply_from_dashboard(job, str(out / "img1" / "dashboard.html"), "[events]\nstimulation_frame = 9\n\n[screening]\nlogic = \"AND\"\n",
                             image="img1", scope="all")
    settings, _, _ = job.started
    assert settings["events"]["stimulation_frame"] == 9 and settings["screening"]["logic"] == "AND"
    assert "img1" not in settings["image"]  # its own timing is replaced by the one for all images
    with pytest.raises(ValueError, match="which image"):
        gui.apply_from_dashboard(job, dash, toml, image=None, scope="image")
