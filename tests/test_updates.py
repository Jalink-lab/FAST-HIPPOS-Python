"""The update check and the search for Cellpose installations (no network, no real environments)."""

import json

from fast_hippos import __version__, cellpose_envs, updates


def release(tag, setup=True, **kw):
    assets = [{"name": f"FAST-HIPPOS-Setup-{tag.lstrip('v')}.exe", "browser_download_url": "https://x/setup.exe"}] if setup else []
    return {"tag_name": tag, "assets": assets, "body": "notes", "html_url": "https://x", "zipball_url": "https://x/z"} | kw


def test_version_order():
    order = ["0.1.0.dev1", "0.1.0a2", "0.1.0b1", "0.1.0b2", "0.1.0rc1", "0.1.0", "0.1.1", "0.2.0", "1.0.0"]
    keys = [updates.version_key(v) for v in order]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert updates.is_newer("v0.1.0rc1", "0.1.0b2") and not updates.is_newer("0.1.0b2", "0.1.0rc1")


def test_only_published_releases_with_the_setup_count():
    found = [release("example-data", setup=False), release("v0.3.0", draft=True), release("v0.4.0", prerelease=True),
             release("v0.1.0b2"), release("v0.2.0")]
    assert updates.pick_latest(found)["version"] == "0.2.0"
    assert updates.pick_latest([release("example-data", setup=False)]) is None
    assert updates.pick_latest({"message": "rate limit"}) is None


def test_daily_check_and_choices(tmp_path, monkeypatch):
    url = tmp_path / "releases.json"
    url.write_text(json.dumps([release("v99.0.0")]))
    monkeypatch.setenv("FAST_HIPPOS_UPDATE_URL", url.as_uri())
    u = updates.Updater(tmp_path / "updates.json")
    assert u.due() and updates.CHECK_EVERY == 24 * 3600
    info = u.check()
    assert info["newer"] and info["offer"] and info["latest"]["version"] == "99.0.0" and info["current"] == __version__
    assert not u.due()  # not again today
    assert not u.choice("skip")["offer"]
    again = updates.Updater(tmp_path / "updates.json")  # remembered
    assert again.data["skip"] == "99.0.0" and not again.offer()
    assert not again.choice("auto_off")["check"] and not again.due()


def test_failed_check_keeps_the_last_answer(tmp_path, monkeypatch):
    url = tmp_path / "releases.json"
    url.write_text(json.dumps([release("v99.0.0")]))
    monkeypatch.setenv("FAST_HIPPOS_UPDATE_URL", url.as_uri())
    u = updates.Updater(tmp_path / "updates.json")
    u.check()
    url.unlink()
    info = u.check()
    assert info["error"] and info["latest"]["version"] == "99.0.0"


def test_no_update_during_an_analysis(tmp_path):
    u = updates.Updater(tmp_path / "updates.json")
    u.data["latest"] = {"version": "99.0.0"}
    try:
        u.start(1234, True, lambda: None)
    except ValueError as e:
        assert "analysis" in str(e)
    else:
        raise AssertionError("must refuse")


def make_env(root, version, conda=False):
    root.mkdir(parents=True)
    (root / "conda-meta" if conda else root).mkdir(exist_ok=True)
    if not conda:
        (root / "pyvenv.cfg").write_text("")
    python = root / ("python.exe" if conda else "Scripts/python.exe")
    python.parent.mkdir(exist_ok=True)
    python.write_text("")
    (root / "Lib" / "site-packages" / f"cellpose-{version}.dist-info").mkdir(parents=True)
    return python


def test_finds_environments_without_starting_them(tmp_path):
    a = make_env(tmp_path / "data" / "project" / ".venv", "3.1.1.3")
    b = make_env(tmp_path / "miniforge3" / "envs" / "cp4", "4.2.1.1", conda=True)
    make_env(tmp_path / "windows" / "skipped", "3.0.0")  # a system folder
    envs = list(cellpose_envs.walk_for_envs([tmp_path], lambda: False))
    assert {e.name for e in envs} == {".venv", "cp4"}
    assert cellpose_envs.env_python(envs[0]) in (a, b)
    assert {cellpose_envs.cellpose_version(e) for e in envs} == {"3.1.1.3", "4.2.1.1"}


def test_search_can_be_cancelled(tmp_path):
    make_env(tmp_path / "x", "3.1.1.3")
    assert list(cellpose_envs.walk_for_envs([tmp_path], lambda: True)) == []


def test_found_is_only_offered(tmp_path):
    env = tmp_path / "env"
    python = make_env(env, "4.2.1.1")
    s = cellpose_envs.CellposeSetup(tmp_path / "state")
    s._add(env)
    s._save()
    st = cellpose_envs.CellposeSetup(tmp_path / "state").state()  # kept for the next start
    assert st["found"] == [{"python": str(python), "version": "4.2.1.1", "major": 4}]
    assert st["bundled"] == {"3": None, "4": None}  # a found installation is not used by itself
