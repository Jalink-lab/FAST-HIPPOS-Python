"""Check an installation: the program imports, .lif support is there, and every installed Cellpose segments a test image.

    <program folder>/.venv/Scripts/python.exe installer/check.py      (Windows)
    <program folder>/.venv/bin/python installer/check.py              (macOS, Linux)

Prints per Cellpose version where it runs (graphics card or processor) and whether it worked. Used by the automatic
builds on GitHub, and useful for anyone who wants to know whether an installation works.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

import fast_hippos
from fast_hippos import cellpose_envs, gui


def cells_image() -> np.ndarray:
    """A 2-D image with 12 bright round cells of about 40 pixels."""
    rng = np.random.default_rng(1)
    y, x = np.mgrid[:512, :512]
    img = np.zeros((512, 512), np.float32)
    for i in range(12):
        cx, cy = 64 + 128 * (i % 4), 85 + 170 * (i // 4)
        img += 900 * (((x - cx) / 22) ** 2 + ((y - cy) / 19) ** 2 < 1)
    return rng.poisson(img + 40).astype(np.float32)


def main() -> int:
    from readlif.reader import LifFile  # noqa: F401 - .lif support is part of every installation

    print(f"FAST-HIPPOS {fast_hippos.__version__}: program and .lif support ok; window page {len(gui.schema()['sections'])} sections")
    runner = Path(fast_hippos.__file__).with_name("_cellpose_runner.py")
    failed = 0
    for version, model in ((3, "cyto3"), (4, "cpsam")):
        python = cellpose_envs.bundled(version)
        if not python:
            print(f"Cellpose {version}: not installed")
            continue
        params = {"model": model, "diameter": 40, "flow_threshold": 0.4, "cellprob_threshold": 0.0, "use_gpu": True}
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "image.npy", Path(tmp) / "masks.npy"
            np.save(src, cells_image())
            r = subprocess.run([python, str(runner), str(src), str(dst), json.dumps(params)], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", check=False)
            if r.returncode or not dst.exists():
                print(f"Cellpose {version}: FAILED\n{r.stderr[-1500:]}")
                failed += 1
                continue
            n = len(np.unique(np.load(dst))) - 1
        info = next((json.loads(line[8:]) for line in r.stdout.splitlines() if line.startswith("FH_INFO ")), {})
        ok = 10 <= n <= 14
        print(f"Cellpose {info.get('version')} on {info.get('gpu_name') or info.get('device')}: {n} cells, {'ok' if ok else 'WRONG'}")
        failed += not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
