"""Command line interface: ``fast-hippos-cli <command>``."""

from __future__ import annotations

import argparse
import shutil
import sys
from importlib import resources
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="fast-hippos-cli", description="FAST-HIPPOS single-cell FLIM trace analysis and screening. "
        "Without a command (e.g. when fast-hippos.exe is double-clicked) the graphical interface opens.")
    sub = p.add_subparsers(dest="command")

    r = sub.add_parser("run", help="analyze the images listed in a config file")
    r.add_argument("config", type=Path)
    a = sub.add_parser("reapply", help="redo stimulation detection, screening and dashboards for the images of the run in "
                       "the output folder (no segmentation), with the [events], [screening] and [display] settings of the config")
    a.add_argument("config", type=Path)
    for sp in (r, a):
        sp.add_argument(
            "--override", type=Path, action="append", default=[], metavar="TOML",
            help="TOML file whose sections override the config (e.g. screening settings saved from a dashboard)",
        )
    s = sub.add_parser("stitch", help="stitch a folder of tiles exported from LAS X by the stage positions of the tiles")
    s.add_argument("folder", type=Path, help="folder with one TIFF per tile (name_s0.tif, name_s1.tif, ...)")
    s.add_argument("--lif", type=Path, help="the .lif file, if the folder has no LAS X MetaData folder")
    s.add_argument("--output", type=Path, help="stitched TIFF (default: <name>_STITCHED.tif next to the folder)")
    s.add_argument("--pixel-size", type=float, help="µm, overrides the metadata")
    s.add_argument("--bidirectional", choices=["y", "x"], help="bidirectional phase correction per tile along this axis")
    i = sub.add_parser("init-config", help="write an annotated example config")
    i.add_argument("path", type=Path, nargs="?", default=Path("fast_hippos.toml"))
    t = sub.add_parser("train-classifier", help="train the nuclei pixel classifier from scribbles")
    t.add_argument("image", type=Path, help="2-D image (e.g. intensity_projection.tif from an output folder)")
    t.add_argument("annotations", type=Path, help="label image: 0 = unlabelled, 1..K = classes")
    t.add_argument("output", type=Path, help="classifier file (.joblib)")
    t.add_argument("--sigma-max", type=float, default=16.0)
    g = sub.add_parser("gui", help="open the graphical user interface in the browser")
    g.add_argument("--port", type=int, default=0, help="port on 127.0.0.1 (default: a free one)")
    g.add_argument("--no-browser", action="store_true", help="do not open the browser")
    sub.add_parser("shortcut", help="put a FAST-HIPPOS shortcut (opens the GUI) on the desktop (Windows)")
    d = sub.add_parser("demo", help="analyze a synthetic data set and open the dashboard")
    d.add_argument("output", type=Path, nargs="?", default=Path("fast_hippos_demo"))
    args = p.parse_args(argv)
    if args.command is None:  # default: the GUI
        args = p.parse_args(["gui"])

    if args.command in ("run", "reapply"):
        from .config import Settings
        from .pipeline import run

        settings = Settings.from_toml(args.config, overrides=args.override)
        if args.command == "run" and not settings.input.files:
            p.error("no input files in [input] files")
        if args.command == "reapply":  # the run in the output folder, with this config's event / screening / display settings
            import tomllib

            from .pipeline import reapply_settings

            changes = settings.to_dict()
            # own settings of single images: those of the run are kept unless the config (or an override) has an image part
            if not any("image" in tomllib.loads(Path(f).read_text(encoding="utf-8")) for f in [args.config, *args.override]):
                changes.pop("image")
            try:
                settings = Settings.from_dict(reapply_settings(settings.input.output, changes))
            except ValueError as e:
                p.error(str(e))
        from .checks import SettingsError

        try:
            results = run(settings, reapply=args.command == "reapply")
        except SettingsError as e:
            print(f"Not started: {len(e.problems)} problem{'s' if len(e.problems) > 1 else ''} with the settings (see above).",
                  file=sys.stderr)
            return 2
        except BaseException:  # also a stop (Ctrl+C): say where the previous run is
            from .pipeline import PREVIOUS_RUN

            previous = Path(settings.input.output) / PREVIOUS_RUN
            if args.command == "run" and previous.is_dir():
                import logging

                logging.getLogger("fast_hippos").error("The run did not finish. The results of the previous run are kept "
                                                       "in %s; move them back to use them again.", previous)
            raise
        return 0 if results else 1
    if args.command == "stitch":
        import logging

        from .io import write_tiff
        from .stitch import stitch_folder

        logging.basicConfig(level=logging.INFO, format="%(message)s")
        image = stitch_folder(args.folder, args.lif, args.pixel_size, args.bidirectional)
        path = args.output or args.folder.parent / f"{image.name}.tif"
        write_tiff(path, image.data, "TCYX", image.pixel_size, image.frame_interval, image.info)
        print(f"Wrote {path}")
        return 0
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
    if args.command == "gui":
        from .gui import serve

        serve(args.port, open_browser=not args.no_browser)
        return 0
    if args.command == "shortcut":
        from .shortcut import create_desktop_shortcut

        print(f"Created {create_desktop_shortcut()}")
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
