"""The context help (templates/help.json, from the manual): up to date, and every ? button points at a section of it."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src" / "fast_hippos" / "templates"


def _help() -> dict:
    return json.loads((TEMPLATES / "help.json").read_text(encoding="utf-8"))


def test_help_is_up_to_date_with_the_manual():
    pytest.importorskip("pymdownx", reason="needs the docs dependencies (uv sync --group docs)")
    spec = importlib.util.spec_from_file_location("make_help", ROOT / "tools" / "manual" / "make_help.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (TEMPLATES / "help.json").read_text(encoding="utf-8") == mod.text(), \
        "the manual changed: run python tools/manual/make_help.py"


def test_every_help_target_exists():
    """data-help, data-help-btn, data-help-scope, data-help-home and the targets in the scripts ('guide/x#anchor')."""
    sections = {p["path"]: set(re.findall(r'<section data-a="([^"]*)"', p["html"])) for p in _help()["pages"]}
    targets = set()
    for f in TEMPLATES.rglob("*"):
        if f.suffix in (".html", ".js"):
            targets |= {(f.name, t) for t in re.findall(r'"((?:guide|reference|help)/[a-z-]+(?:#[a-z0-9-]*)?)"',
                                                        f.read_text(encoding="utf-8"))}
    assert len(targets) > 25
    bad = [(name, t) for name, t in sorted(targets)
           if t.split("#")[0] not in sections or ("#" in t and t.split("#")[1] not in sections[t.split("#")[0]])]
    assert not bad, f"help targets that are not in the manual (renamed headings?): {bad}"


def test_help_is_embedded_in_the_pages():
    from fast_hippos.dashboard import _dashboard_template, help_json

    page = _dashboard_template()
    assert "__FH_HELP__" in page and "#helpPanel {" in page and "const HELP" in page
    assert "</script" not in help_json().lower()
    assert json.loads(help_json())["pages"]


def test_gui_page_has_the_help():
    from fast_hippos import gui

    page = gui._page("t").decode("utf-8")
    assert "__FH_HELP__" not in page and "__HELP_" not in page
    assert "#helpPanel {" in page and "const HELP" in page and '"guide/window"' in page
