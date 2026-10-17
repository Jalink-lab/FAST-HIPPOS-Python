"""The example experiment of the user manual ('A screen of several samples'): each example image as a sample of its
own, analyzed in its own run with the settings of example.toml, in the experiment folder <example>/experiment.

    python tools/manual/make_example_experiment.py [C:/PythonProjects/FAST-HIPPOS/data/manual]

Each sample gets a config next to example.toml (sample_<k>.toml, as the FAST-HIPPOS window would run it after
'New sample'); every run updates the experiment overview (experiment/index.html).
"""

import subprocess
import sys
import tomllib
from pathlib import Path

DEFAULT_EXAMPLE = Path("C:/PythonProjects/FAST-HIPPOS/data/manual")
LABELS = ["library part 1", "library part 2", "library part 3"]


def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return '"' + v.replace("\\", "/") + '"'
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(x)}" for k, x in v.items()) + " }"
    return repr(v)


def main() -> None:
    example = (Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXAMPLE).resolve()
    base = tomllib.loads((example / "example.toml").read_text(encoding="utf-8"))
    for k, (image, label) in enumerate(zip(base["input"]["files"], LABELS), 1):
        cfg = {**base, "input": {**base["input"], "files": [image], "experiment": "experiment",
                                 "output": f"experiment/{Path(image).stem}", "sample_label": label}}
        lines = [f"# Sample {k} of the example experiment (tools/manual/make_example_experiment.py)"]
        for section, values in cfg.items():
            lines.append(f"\n[{section}]")
            lines += [f"{key} = {toml_value(v)}" for key, v in values.items()]
        path = example / f"sample_{k}.toml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"=== {path.name}: {image} ({label})", flush=True)
        r = subprocess.run([sys.executable, "-m", "fast_hippos.cli", "run", path.name], cwd=example, check=False)
        if r.returncode:
            sys.exit(f"FAILED: {path.name}")
    print(f"Experiment overview: {example / 'experiment' / 'index.html'}")


if __name__ == "__main__":
    main()
