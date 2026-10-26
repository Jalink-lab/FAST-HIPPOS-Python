# FAST-HIPPOS (Python) — notes for Claude Code

Python port of the FAST-HIPPOS Fiji macro: single-cell FLIM time-lapse analysis and hit selection for photoactivation
screens. Window (GUI) in the browser, HTML dashboards and overviews, `.rgn` files for LAS X.

## Environment
- The project folder is in surfdrive (synced). The uv environment is OUTSIDE it: always
  `export UV_PROJECT_ENVIRONMENT=C:/PythonProjects/FAST-HIPPOS/.venv` before `uv` commands, or call
  `C:/PythonProjects/FAST-HIPPOS/.venv/Scripts/python.exe` directly. The file `.venv` in the project folder is a
  placeholder that stops uv from making an environment in surfdrive: never delete it.
- Tests: `python -m pytest -q -p no:warnings` (~3 min); lint: `python -m ruff check src tests tools`.
- The user's own window state is in `~/.fast_hippos` (last_settings.toml): back it up before testing the window, or
  use an isolated test window: `python tools/manual/gui_instance.py <example folder> 8766` (own home folder).
  Another process may share port 8765 (it then answers 501): use another port.

## How it works now (2026-10)
- Every image is a sample: the window's Images card has the experiment folder, the images (a .tif, a tile folder,
  or every series of a .lif, with a tick box per series) and one row per sample (name = folder, label).
  Run analysis = `pipeline.run_samples` (CLI `run-samples`): one run per sample in `<experiment>/<name>`, then the
  experiment overview. `fast-hippos-cli run` can still analyze several images in one run (settings files only).
- One browser tab: the window (templates/gui.html) has a top bar Setup | Experiment | Sample ▾ | Image ▾ and shows
  the overviews and dashboards in frames, served by the GUI server; the pages stay stand-alone files
  (templates/common/base.js: `SHELL` hands links to the window). Purple theme (tokens in common/base.css and
  gui.html; `--accent-strong` for filled buttons).
- Context help: `templates/help.json` is made from the manual by `tools/manual/make_help.py`; the pages' ? buttons
  point at `<page>#<anchor>` (data-help attributes, `CARD_HELP` in gui.html). `tests/test_help.py` fails when
  help.json is stale or a ? points at a heading that is gone.

## The user manual (manual/, MkDocs Material, live at https://jalink-lab.github.io/FAST-HIPPOS-Python/)
- Read `tools/manual/MAINTAINING.md` first. Every change to the window, dashboards or overviews is checked against
  the manual in the same piece of work (the update-manual skill).
- Generated, never edit by hand: `manual/reference/settings.md`, `metrics.md` (gen_reference.py), help.json.
- `python tools/manual/refresh.py` re-applies the example experiment (C:/PythonProjects/FAST-HIPPOS/data/manual),
  retakes the screenshots, rebuilds the demo and the site (strict) and runs the manual tests. The demo ZIP goes to
  the `example-data` release (`gh release upload example-data <zip> --clobber`); upload it BEFORE pushing, so that
  the site build of the push takes the new demo.
- Style: plain, scientific register; no example numbers on overview pages; show the user a preview of visual changes.

## Git
- GitHub: Jalink-lab/FAST-HIPPOS-Python (public, beta). gh CLI: "C:/Program Files/GitHub CLI/gh.exe".
- Commit locally; push only when the user says so (small follow-ups of approved work: ask once).
