"""The live demo of the manual: the overviews and the dashboards of the example experiment (example.toml), copied into
manual/demo (not in git, ~75 MB) and zipped as manual-demo.zip for the release with the example data, from which the
site build takes it. The example images (1000 x 700 px) fit in the dashboards at full resolution, without tiles.

    python tools/manual/make_demo.py <experiment folder of the example> [zip file]
"""

import shutil
import sys
import zipfile
from pathlib import Path

DEMO = Path(__file__).resolve().parents[2] / "manual" / "demo"


def main(run: Path, zip_path: Path | None) -> None:
    shutil.rmtree(DEMO, ignore_errors=True)
    files = [run / "index.html", *sorted(run.glob("*/index.html")), *sorted(run.glob("*/*/dashboard.html")),
             *sorted(run.glob("*/dashboard.html")),
             *sorted(run.glob("*/*/frames/*.js")), *sorted(run.glob("*/frames/*.js"))]  # the frames of the dashboards
    for f in files:
        target = DEMO / run.name / f.relative_to(run)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
    print(f"{len(files)} files in {DEMO}")
    if zip_path:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in DEMO.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(DEMO))
        print(f"{zip_path}: {zip_path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
