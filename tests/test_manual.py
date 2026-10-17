"""The user manual (manual/, mkdocs.yml): the generated reference pages match the program, and the site builds."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _gen():
    spec = importlib.util.spec_from_file_location("gen_reference", ROOT / "tools" / "manual" / "gen_reference.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reference_pages_are_up_to_date():
    gen = _gen()
    for name, page in (("settings.md", gen.settings_page()), ("metrics.md", gen.metrics_page())):
        assert (ROOT / "manual" / "reference" / name).read_text(encoding="utf-8") == page, \
            f"manual/reference/{name} is out of date: run python tools/manual/gen_reference.py"


def test_images_used_by_the_manual_exist():
    import re

    for md in (ROOT / "manual").rglob("*.md"):
        for img in re.findall(r"!\[[^\]]*\]\(([^)\s]+)", md.read_text(encoding="utf-8")):
            assert (md.parent / img).resolve().exists(), f"{md.relative_to(ROOT)}: {img} not found"


def test_site_builds(tmp_path):
    pytest.importorskip("material")
    r = subprocess.run([sys.executable, "-m", "mkdocs", "build", "--strict", "-q", "-d", str(tmp_path)], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
