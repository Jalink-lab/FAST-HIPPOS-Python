# Maintaining the user manual of FAST-HIPPOS

Notes for whoever (person or Claude, with the `update-manual` skill) updates the manual after a change to the program.
The manual: `manual/` (MkDocs Material, `mkdocs.yml`), live at <https://jalink-lab.github.io/FAST-HIPPOS-Python/>.
Rule: every noticeable change to the window, the dashboard or the overview is checked against the manual in the same
piece of work.

## Which code goes with which pages

| Changed code | Check these pages |
|---|---|
| `templates/gui.html`, `gui.py` (cards, labels, checks, buttons) | `guide/window.md`, `start/first-analysis.md` (steps 2–6), `help/faq.md` |
| `gui.py` FIELDS / TIPS / layout, `config.py` (settings, defaults) | regenerate `reference/settings.md`; pages that mention the setting (`grep -rn` its label) |
| `config.py` METRICS, cell table columns | regenerate `reference/metrics.md` (other values: `OTHER_VALUES` in `gen_reference.py`) |
| `templates/dashboard/` (panels, screening pane, Apply buttons) | `guide/dashboard.md`, `guide/choosing-hits.md`, `guide/own-settings.md`, `start/first-analysis.md` (step 7) |
| `templates/overview/` | `guide/overview.md`, `guide/screen.md` (the experiment overview) |
| `experiment.py`, experiment folder, New sample, Re-apply all samples, the top bar (Setup, Experiment, Sample, Image) | `guide/screen.md`, `guide/window.md` (Images, Run card), `guide/output-folder.md`, `reference/command-line.md` |
| `events.py`, `screening.py` (detection, gates, criteria) | `guide/choosing-hits.md`, `reference/analysis.md`, `guide/window.md` (Stimulation and calibration), `help/faq.md` |
| per-image settings (`config.IMAGE_SETTINGS`, Apply to this image only) | `guide/own-settings.md` |
| `pipeline.py` output files, run folder, `_previous_run` | `guide/output-folder.md` |
| `stage.py`, `stitch.py`, .rgn files | `guide/microscope.md` |
| `cli.py`, settings files | `reference/command-line.md` |
| installation, dependencies | `start/install.md` |
| anything with a label that the README quotes | `README.md` (outside `manual/`, also user-facing) |

Hover texts of *buttons* (`title=` in the templates) are not quoted in the manual: check only that the sentence about
that control still agrees. Hover texts of *settings* are, through the generated reference. Toggle buttons have two
labels in the code (e.g. "Fold all" / "Unfold all"): search for both.

Generated, never edit by hand: `manual/reference/settings.md`, `manual/reference/metrics.md` (`tests/test_manual.py`
fails when they are stale). Wrong text there: fix it in `gui.py` (TIPS / FIELDS) or `config.py` (METRICS).

**Context help.** The window, the dashboard and both overviews show the manual in a side panel (*? Help*, the ?
buttons, the ? and F1 keys): `src/fast_hippos/templates/help.json`, made from the guide, reference and help pages by
`python tools/manual/make_help.py` (also run by `refresh.py`). After every change to those pages, run it and commit
help.json with the change; `tests/test_help.py` fails when it is stale. The ? buttons point at headings
(`data-help="guide/dashboard#image"` in the templates, `CARD_HELP` in `gui.html`): renaming a heading changes its
anchor, and the same test then names the buttons to fix. Screenshots are left out of the help; links to pages that
are not in it (Getting started, command line) open the online manual.

## The example

- Folder: `C:/PythonProjects/FAST-HIPPOS/data/manual` (outside the synced project folder): `example_screen_1-3.tif`,
  `stage_positions.txt`, `example.toml` (with the local Cellpose environments), `example_settings.toml` (the public
  copy, in the release ZIP), `example_run/` (the output).
- The example experiment (`guide/screen.md`): `experiment/` in the same folder, made with
  `python tools/manual/make_example_experiment.py` (each image a sample, `sample_1-3.toml`, ~1.5 min); the
  screenshots `gui_experiment*`, `gui_run_experiment` and `experiment` need it. Remake it after a change
  to the example or the analysis.
- On another computer: download `fast-hippos-example-data.zip` from the
  [example-data release](https://github.com/Jalink-lab/FAST-HIPPOS-Python/releases/tag/example-data), unpack it,
  copy `example_settings.toml` to `example.toml`, add `cellpose3_python = "<path>/python.exe"` under `[segmentation]`,
  and run `fast-hippos-cli run example.toml` once (Cellpose, ~1 min). The images were cut from
  `Allchannels_merged_95_5.tif` with `make_example_data.py`.
- The screen: Cos7 cells with the cAMP sensor EpacH250, ~5 % ADRB2 knock-out cells (marked with PA-JF646, channel 3)
  among wild-type cells; isoproterenol in frame 5, forskolin calibration in frame 25; hits = low responders
  (paper: Mukherjee et al., bioRxiv 2025, doi:10.1101/2025.07.11.664338).
- Settings (the user's choice): criteria `response_max_abs < 3.1` AND `baseline_mean` between 2.0 and 2.7; gate
  calibration − baseline 0.5–1.2, |baseline − population| gate off; dashboard views: traces as lines, scatter
  `additional_intensity` (log) against `value_at_frame`; colour range 2.0–3.6 ns.

**Numbers quoted in the text** (recount after a change to the example or the analysis):

| Number | Pages |
|---|---|
| 675 / 749 / 856 cells, 2280 in total | `start/first-analysis.md` |
| 75 hits (24 / 28 / 23), 64 of them marker-positive, `HITS_example_run_1-75.rgn` | `start/first-analysis.md`, `guide/choosing-hits.md`, `guide/output-folder.md`, `start/demo.md` |
| stimulation 5, calibration 25 | `start/first-analysis.md` |

Recount with:

```python
import pandas as pd
d = [pd.read_csv(f"C:/PythonProjects/FAST-HIPPOS/data/manual/example_run/example_screen_{i}/cells.tsv", sep="\t") for i in (1, 2, 3)]
print([len(x) for x in d], [int(x.hit.sum()) for x in d], sum(int((x.hit & (x.class_additional > 0)).sum()) for x in d))
```

## Which screenshot shows what

| Screenshot (`manual/images/`) | Shows |
|---|---|
| `gui.png` | the whole window: toolbar (Open/Save settings, Defaults, ◐, Quit), the advanced-settings line, Fold all, the Images and Cell segmentation cards and the Run card with log and results |
| `gui_images`, `gui_segmentation`, `gui_stimulation`, `gui_screening`, `gui_display`, `gui_run` | one card each (cropped) |
| `gui_advanced` | Cell segmentation with its advanced settings open |
| `gui_rgn` | Screening, advanced: stage positions file, .rgn files and route, stage axes, tiles (cropped) |
| `dashboard.png`, `dashboard_views.png` | the whole dashboard: top bar, Screening pane open / folded, Image, Traces, Kymograph |
| `dash_screening`, `dash_timing`, `dash_gates`, `dash_output`, `dash_criteria` | the Screening pane and its parts |
| `dash_image`, `dash_traces`, `dash_kymograph`, `dash_cells` | one panel each |
| `dash_distribution`, `dash_scatter` | one panel each, at frame 15 |
| `dash_cell` | the Cell card of a hit |
| `overview.png`, `ov_images`, `ov_response`, `ov_cells`, `ov_maps`, `ov_hits` | the overview, and its panels |
| `gui_experiment`, `gui_run_experiment`, `gui_experiment_differs` | the window with the settings of sample 3 of the example experiment: the Images card (experiment folder, sample label), the Run card (samples, Re-apply all samples, Experiment overview), and the warning about samples analyzed with other settings (a criterion changed in the page) |
| `experiment.png` | the overview of the example experiment (3 samples) |
| `logo_hippos.png` | the home page: the logo without its name, with a transparent background and floor (made once from the full logo; not by a script) |
| `landing/` (`f00-f29.webp`, `colorbar.png`, `movie.json`), `landing_experiment.png` | the home page: the frames of the lifetime movie of a part of example_screen_1 (hits outlined from frame 12 on), played by `manual.js` with the label, colour scale and timeline as page text; and a close-up of `experiment.png`; made by `make_landing_images.py` (part of `refresh.py`) |

Screenshots that change only because of times in the log (`gui.png`, `gui_run.png`) or the date in the overview
header: restore them (`git checkout -- <file>`), so that commits only hold real changes.

## Refresh and check

```powershell
C:\PythonProjects\FAST-HIPPOS\.venv\Scripts\python.exe tools/manual/refresh.py
```

Re-applies the example, retakes all screenshots, regenerates the reference, rebuilds the demo and `manual-demo.zip`,
builds the site strictly and runs `tests/test_manual.py`. About 1–2 minutes. Options:

- `--shots gui dash_scatter`: only the screenshots whose names start with these prefixes (`gui` = all `gui*` shots);
- `--skip reapply,screenshots,demo`: for a change in the text only (the reference and the build always help).
The screenshots run in a FAST-HIPPOS window of their own (`gui_instance.py`, own home folder: the user's settings are
not touched). A new screenshot: add it to `screenshots.py` (the distribution and scatter shots are taken at frame 15).

Then look at the changed images (`git status manual/images`), and at the changed pages in a browser
(`python -m mkdocs serve`, or serve a build).

Also: `tests/test_dashboard_js.py` compiles the scripts of the window, the dashboard and the overview.

## Publish (with the user's OK)

Order: refresh → commit (pages, screenshots, reference; `manual/demo/` is not in git) → with the user's OK: upload
→ push → watch the deploy.

Is the published demo older than the last change to the dashboard or overview? Compare
`gh release view example-data --json assets --jq '.assets[] | .name + " " + .updatedAt'` (UTC) with
`git log -1 --format=%ci -- src/fast_hippos/templates/dashboard src/fast_hippos/templates/overview src/fast_hippos/templates/common`.

1. Dashboard or overview templates changed: upload the new demo first:
   `gh release upload example-data C:/PythonProjects/FAST-HIPPOS/data/manual/manual-demo.zip --clobber`
2. `example_settings.toml` or the images changed: rebuild `fast-hippos-example-data.zip` (folder
   `FAST-HIPPOS example/` with the three TIFFs, `stage_positions.txt`, `example_settings.toml`), upload it the same way,
   and update the release notes (`gh release edit example-data --notes-file …`).
3. Push `main`. The *Manual* workflow deploys when `manual/**` or `mkdocs.yml` changed; for only a new demo, start it
   with `gh workflow run manual.yml`. Watch it (`gh run watch <id> --exit-status`) and check the live page.

Pitfall: in Git Bash heredocs, backslashes get mangled; write edit scripts with a file editor (or the Write tool).
