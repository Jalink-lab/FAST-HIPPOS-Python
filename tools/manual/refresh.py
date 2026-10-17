"""Refresh everything of the user manual that is made from the program, in one go (locally; nothing is published):

1. re-apply the example run (example.toml in the example folder), so that its dashboards and overview are made with the
   current code;
2. retake the screenshots (manual/images; all, or only those named with --shots);
3. regenerate the reference pages (manual/reference/settings.md, metrics.md);
4. rebuild the live demo (manual/demo) and its ZIP (manual-demo.zip in the example folder), for the release;
5. build the site in strict mode (broken links, missing images) and run the manual tests.

    python tools/manual/refresh.py [--example C:/PythonProjects/FAST-HIPPOS/data/manual] [--shots gui_ dash_scatter]
                                   [--skip reapply,screenshots,demo]

The example folder holds the example images, stage_positions.txt and example.toml (= example_settings.toml of the
'example-data' release, plus the local Cellpose environments); see tools/manual/make_example_data.py.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "manual"
DEFAULT_EXAMPLE = Path("C:/PythonProjects/FAST-HIPPOS/data/manual")


def step(title: str, cmd: list, cwd: Path = ROOT) -> None:
    print(f"\n=== {title}\n$ {' '.join(map(str, cmd))}", flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, check=False)
    if r.returncode != 0:
        sys.exit(f"FAILED: {title} (exit code {r.returncode})")


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--example", type=Path, default=DEFAULT_EXAMPLE, help="the example folder (with example.toml)")
    a.add_argument("--shots", nargs="*", default=[], help="only these screenshots (name prefixes, e.g. gui_ dash_cell)")
    a.add_argument("--skip", default="", help="comma-separated steps to skip: reapply, screenshots, reference, demo, build")
    args = a.parse_args()
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    py = sys.executable
    example = args.example.resolve()
    if not (example / "example.toml").exists():
        sys.exit(f"No example.toml in {example}: see the docstring of tools/manual/make_example_data.py")

    if "reapply" not in skip:
        step("Re-apply the example run", [py, "-m", "fast_hippos.cli", "reapply", "example.toml"], cwd=example)
    if "screenshots" not in skip:  # (re-applies once more inside its own FAST-HIPPOS window)
        step("Screenshots", [py, TOOLS / "screenshots.py", example, *args.shots])
    if "reference" not in skip:
        step("Reference pages", [py, TOOLS / "gen_reference.py"])
    if "demo" not in skip:
        step("Live demo", [py, TOOLS / "make_demo.py", example / "example_run", example / "manual-demo.zip"])
    if "build" not in skip:
        with tempfile.TemporaryDirectory() as site:  # not in the (synchronized) project folder
            step("Site build (strict)", [py, "-m", "mkdocs", "build", "--strict", "-q", "-d", site])
        step("Manual tests", [py, "-m", "pytest", "-q", "-p", "no:warnings", "tests/test_manual.py"])
    print("\nDone. Look at the changed screenshots (git status manual/images) before committing.")
    print(f"To publish the demo: gh release upload example-data {example / 'manual-demo.zip'} --clobber")


if __name__ == "__main__":
    main()
