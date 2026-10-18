"""A screen of several samples: one run per sample inside an experiment folder, and the overview of all samples."""

import json

import pytest

from fast_hippos.config import Criterion, Settings
from fast_hippos.experiment import (
    build_experiment_data,
    in_experiment,
    read_overview_data,
    run_folders,
    settings_differences,
)
from fast_hippos.pipeline import reapply_experiment, run
from fast_hippos.synthetic import make_timelapse, save_tiff


@pytest.fixture(scope="module")
def experiment(tmp_path_factory):
    """An experiment folder with two samples (runs): A and B, B with another criterion."""
    root = tmp_path_factory.mktemp("exp")
    exp = root / "screen"
    for k, (name, threshold) in enumerate([("sample_A", 0.2), ("sample_B", 0.3)]):
        image, _ = make_timelapse(seed=k + 1)
        src = save_tiff(image, root / f"{name}.tif")
        s = Settings()
        s.input.files = [src]
        s.input.experiment = exp
        s.input.output = exp / name
        s.input.sample_label = f"condition {name[-1]}"
        s.segmentation.method = "threshold"
        s.segmentation.diameter = 18
        s.segmentation.min_cell_size = 30
        s.screening.enabled = True
        s.screening.criteria = [Criterion("response_max_diff", ">", threshold)]
        run(s)
    return exp


def test_every_run_updates_the_experiment_overview(experiment):
    assert [f.name for f in run_folders(experiment)] == ["sample_A", "sample_B"]
    data = read_overview_data(experiment / "index.html")
    assert data["kind"] == "experiment" and [r["name"] for r in data["runs"]] == ["sample_A", "sample_B"]
    assert [r["label"] for r in data["runs"]] == ["condition A", "condition B"]
    assert [i["sample"] for i in data["images"]] == ["sample_A", "sample_B"]
    assert [i["index"] for i in data["images"]] == [0, 1]
    # the images of the two samples have the same name: made unique, and the links point into the sample folders
    assert len({i["name"] for i in data["images"]}) == 2
    for im in data["images"]:
        assert im["href"].startswith(im["sample"] + "/") and (experiment / im["href"]).exists()
    summary = (experiment / "experiment_summary.tsv").read_text().splitlines()
    assert summary[0].startswith("sample\tlabel\timage") and len(summary) == 3


def test_differing_settings_are_reported(experiment):
    data = build_experiment_data(experiment)
    assert [d["setting"] for d in data["differences"]] == ["screening.criteria"]
    assert data["notes"] and "not all analyzed with the same settings" in data["notes"][0]
    assert "0.2" in data["notes"][0] and "0.3" in data["notes"][0]


def test_settings_that_do_not_matter_are_not_compared():
    a = {"input": {"files": ["a.tif"], "output": "x/a", "sample_label": "A", "modality": "tcspc"},
         "display": {"lut": "a", "smooth_traces": 1}, "screening": {"random_seed": 1, "enabled": True},
         "image": {"a": {"events": {"stimulation_frame": 3}}}}
    b = {"input": {"files": ["b.tif"], "output": "x/b", "sample_label": "B", "modality": "tcspc"},
         "display": {"lut": "b", "smooth_traces": 1}, "screening": {"random_seed": 2, "enabled": True}, "image": {}}
    assert settings_differences({"a": a, "b": b}) == []
    b["display"]["smooth_traces"] = 3
    assert [d["setting"] for d in settings_differences({"a": a, "b": b})] == ["display.smooth_traces"]


def test_in_experiment(tmp_path):
    assert in_experiment(tmp_path / "e" / "s", tmp_path / "e")
    assert not in_experiment(tmp_path / "e" / "s" / "t", tmp_path / "e")
    assert not in_experiment(tmp_path / "e", tmp_path / "e")
    assert not in_experiment(tmp_path / "s", None)


def test_reapply_to_all_samples_makes_them_the_same(experiment):
    s = Settings()
    s.screening.enabled = True
    s.screening.criteria = [Criterion("response_max_diff", ">", 0.25)]
    assert reapply_experiment(experiment, s.to_dict()) == []
    data = read_overview_data(experiment / "index.html")
    assert data["differences"] == [] and not any("same settings" in n for n in data["notes"])
    for folder in run_folders(experiment):
        used = json.loads((folder / "settings_used.json").read_text())
        assert used["screening"]["criteria"][0]["value"] == 0.25
        assert used["input"]["sample_label"] == f"condition {folder.name[-1]}"  # each sample keeps its label
    assert (experiment / "experiment_log.txt").exists()


def test_cli_rebuilds_the_overview(experiment):
    from fast_hippos.cli import main

    (experiment / "index.html").unlink()
    assert main(["experiment", str(experiment)]) == 0
    assert (experiment / "index.html").exists()


def test_window_lists_the_samples_and_their_differences(experiment):
    from fast_hippos.gui import experiment_info, settings_from_plain

    used = json.loads((experiment / "sample_A" / "settings_used.json").read_text())
    same = experiment_info(str(experiment), settings_from_plain(used).to_dict())
    assert [s["name"] for s in same["samples"]] == ["sample_A", "sample_B"] and same["index"]
    assert [s["label"] for s in same["samples"]] == ["condition A", "condition B"]
    assert same["differs"] == {}  # the samples were made the same by the re-apply before
    used["screening"]["criteria"][0]["value"] = 0.9
    assert experiment_info(str(experiment), used)["differs"] == {"sample_A": ["screening.criteria"], "sample_B": ["screening.criteria"]}
    assert experiment_info(str(experiment / "nothing"))["exists"] is False


def test_differences_are_named_as_in_the_window(experiment):
    from fast_hippos.experiment import describe_differences

    line = describe_differences([{"setting": "screening.criteria", "values": {"a": [], "b": None}}])[0]
    assert line.startswith("Hit criteria (screening.criteria) — ")


def test_reapply_keeps_the_label_of_a_sample(experiment):
    from fast_hippos.pipeline import reapply_settings

    s = Settings()  # e.g. a settings file without a sample label
    assert reapply_settings(experiment / "sample_A", s.to_dict())["input"]["sample_label"] == "condition A"
    s.input.sample_label = "renamed"
    assert reapply_settings(experiment / "sample_A", s.to_dict())["input"]["sample_label"] == "renamed"


def test_reapply_keeps_the_gates_of_another_image_type(experiment, tmp_path):
    """Settings of a lifetime sample re-applied to a ratio sample: the ratio sample keeps its own quality gates."""
    import shutil

    from fast_hippos.pipeline import reapply_settings

    ratio = tmp_path / "exp" / "ratio_sample"
    shutil.copytree(experiment / "sample_A", ratio)
    used = json.loads((ratio / "settings_used.json").read_text())
    used["input"]["modality"] = "ratio"
    used["screening"]["baseline_calibration_diff"] = None
    used["screening"]["max_baseline_deviation"] = None
    (ratio / "settings_used.json").write_text(json.dumps(used))
    s = Settings()  # tcspc, with the default lifetime gates
    s.screening.criteria = [Criterion("response_max_diff", ">", 0.4)]
    merged = reapply_settings(ratio, s.to_dict())
    assert merged["screening"]["baseline_calibration_diff"] is None and merged["screening"]["max_baseline_deviation"] is None
    assert merged["screening"]["criteria"][0]["value"] == 0.4
    # the experiment folder was copied: the sample now belongs to the folder it is in, when that is an experiment
    assert merged["input"]["experiment"] == str(experiment)  # tmp_path/exp has no experiment overview
    shutil.copy(experiment / "index.html", tmp_path / "exp" / "index.html")
    assert reapply_settings(ratio, s.to_dict())["input"]["experiment"] == str((tmp_path / "exp").resolve())


def test_output_folder_must_not_be_the_experiment_folder(tmp_path):
    from fast_hippos.checks import check_inputs

    s = Settings()
    s.input.experiment = tmp_path
    s.input.output = tmp_path
    assert any("is the experiment folder" in p for p in check_inputs(s))


def test_samples_in_natural_order_and_tables_with_the_image_names(experiment, tmp_path):
    import shutil

    exp = tmp_path / "plates"
    for name in ["plate 10", "plate 2"]:
        shutil.copytree(experiment / "sample_A", exp / name)
    assert [f.name for f in run_folders(exp)] == ["plate 2", "plate 10"]
    from fast_hippos.experiment import write_experiment_overview

    write_experiment_overview(exp, failed=["plate 10"])
    data = read_overview_data(exp / "index.html")
    assert len({i["name"] for i in data["images"]}) == 2 and {i["image"] for i in data["images"]} == {data["images"][0]["image"]}
    summary = (exp / "experiment_summary.tsv").read_text().splitlines()
    assert len({line.split("\t")[2] for line in summary[1:]}) == 1  # the image column: its own name in both samples
    assert "Not re-applied" in data["notes"][0] and "plate 10" in data["notes"][0]
