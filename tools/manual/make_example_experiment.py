"""The example of the user manual: every example image a sample of its own (as Run analysis in the window does),
with the settings of example.toml and the labels 'library part 1-3', in the experiment folder <example>/experiment.

    python tools/manual/make_example_experiment.py [C:/PythonProjects/FAST-HIPPOS/data/manual]"""

import json
import subprocess
import sys
from pathlib import Path

DEFAULT_EXAMPLE = Path("C:/PythonProjects/FAST-HIPPOS/data/manual")
LABELS = ["library part 1", "library part 2", "library part 3"]


def main() -> None:
    """As Run analysis in the window: every example image a sample (run-samples), with the labels above."""
    from fast_hippos.config import Settings
    from fast_hippos.pipeline import sample_list

    example = (Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXAMPLE).resolve()
    samples = sample_list(Settings.from_toml(example / "example.toml"))
    for row, label in zip(samples, LABELS):
        row["label"] = label
    plan = example / "samples.json"
    plan.write_text(json.dumps(samples), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "fast_hippos.cli", "run-samples", "example.toml", "--samples", plan.name],
                       cwd=example, check=False)
    if r.returncode:
        sys.exit("FAILED: run-samples")
    print(f"Experiment overview: {example / 'experiment' / 'index.html'}")


if __name__ == "__main__":
    main()
