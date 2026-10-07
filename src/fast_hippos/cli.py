"""Command line interface: ``fast-hippos <command>``."""

from __future__ import annotations

import argparse
import shutil
import sys
from importlib import resources
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fast-hippos", description="FAST-HIPPOS single-cell FLIM trace analysis and screening")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="analyze the images listed in a config file")
    r.add_argument("config", type=Path)
    a = sub.add_parser("reapply", help="re-run event detection, screening and dashboards on saved output (no segmentation)")
    a.add_argument("config", type=Path)
    for sp in (r, a):
        sp.add_argument(
            "--override", type=Path, action="append", default=[], metavar="TOML",
            help="TOML file whose sections override the config (e.g. screening settings saved from a dashboard)",
        )
    i = sub.add_parser("init-config", help="write an annotated example config")
    i.add_argument("path", type=Path, nargs="?", default=Path("fast_hippos.toml"))
    t = sub.add_parser("train-classifier", help="train the nuclei pixel classifier from scribbles")
    t.add_argument("image", type=Path, help="2-D image (e.g. intensity_projection.tif from an output folder)")
    t.add_argument("annotations", type=Path, help="label image: 0 = unlabelled, 1..K = classes")
    t.add_argument("output", type=Path, help="classifier file (.joblib)")
    t.add_argument("--sigma-max", type=float, default=16.0)
    d = sub.add_parser("demo", help="analyze a synthetic data set and open the dashboard")
    d.add_argument("output", type=Path, nargs="?", default=Path("fast_hippos_demo"))
    args = p.parse_args(argv)

    if args.command in ("run", "reapply"):
        from .config import Settings
        from .pipeline import run

        settings = Settings.from_toml(args.config, overrides=args.override)
        if args.command == "run" and not settings.input.files:
            p.error("no input files in [input] files")
        results = run(settings, reapply=args.command == "reapply")
        return 0 if results else 1
    if args.command == "init-config":
        if args.path.exists():
            p.error(f"{args.path} exists")
        with resources.as_file(resources.files("fast_hippos").joinpath("templates", "example_config.toml")) as src:
            shutil.copyfile(src, args.path)
        print(f"Wrote {args.path}")
        return 0
    if args.command == "train-classifier":
        from .io import read_tiff
        from .pixel_classifier import train

        image = read_tiff(args.image).data[0, 0]
        annotations = read_tiff(args.annotations).data[0, 0].astype(int)
        train(image, annotations, args.output, sigma_max=args.sigma_max)
        return 0
    if args.command == "demo":
        return _demo(args.output)
    return 1


def _demo(out: Path) -> int:
    import webbrowser

    from .config import Criterion, Settings
    from .pipeline import run
    from .synthetic import make_timelapse, save_tiff

    out.mkdir(parents=True, exist_ok=True)
    image, _ = make_timelapse(size=384, n_frames=60, photons=200, seed=3)
    src = save_tiff(image, out / "synthetic.tif")
    (out / "stage_positions.txt").write_text("0.01\n0.02\n")
    s = Settings()
    s.input.files = [src]
    s.input.output = out / "output"
    s.input.additional_channel = 3
    s.segmentation.method = "threshold"
    s.segmentation.diameter = 18
    s.display.smooth_traces = 1
    s.screening.enabled = True
    s.screening.criteria = [Criterion("response_max_diff", ">", 0.2)]
    s.screening.stage_positions_file = out / "stage_positions.txt"
    s.screening.classify_additional_channel = True
    results = run(s)
    webbrowser.open((results[0].out_dir / "dashboard.html").resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
