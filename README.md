# FAST-HIPPOS (Python)

Python port of the [FAST-HIPPOS](https://imagej.net/plugins/fast-hippos) Fiji macro:
*FLIM Analysis of Single-cell Traces for Hit Identification of Phenotypes in Pooled Optical Screening*.

Segment cells, measure intensity-weighted lifetime (or ratio / intensity) traces per cell, detect
stimulation and calibration, find hit cells and write their stage coordinates as Leica `.rgn` files.
Every image gets a self-contained, interactive **HTML dashboard** instead of dozens of Fiji windows.

- Reference implementation: Fiji macro **v0.9.5** ([`reference/fiji_v0.9.5`](reference/fiji_v0.9.5)).
- Behaviour, fixed macro bugs and validation against Fiji: [`docs/SPEC.md`](docs/SPEC.md).

## Setup

The code lives in surfdrive; the environment lives in `C:\PythonProjects\FAST-HIPPOS\.venv` (not synced).

```powershell
$env:UV_PROJECT_ENVIRONMENT = "C:\PythonProjects\FAST-HIPPOS\.venv"
uv sync                      # core + dev dependencies
uv sync --extra lif          # optional: .lif reading
uv run pytest
```

Cellpose 3 and 4 are used from their own environments (`segmentation.cellpose3_python` /
`cellpose4_python` in the config), so they do not have to be installed here. Alternatively install one
of them in this environment with `uv sync --extra cellpose3` or `--extra cellpose4`.

## Usage

```powershell
uv run fast-hippos init-config experiment.toml   # annotated example config
uv run fast-hippos run experiment.toml           # full analysis
uv run fast-hippos reapply experiment.toml       # new events / screening settings on saved output, no segmentation
uv run fast-hippos demo                          # synthetic data set, opens a dashboard
uv run fast-hippos train-classifier intensity_projection.tif scribbles.tif nuclei.joblib
```

Output (per run): `index.html` (overview, hit map), `hits.tsv`, `HITS_*.rgn` (all hits and optimized-path
chunks), `cell_coordinates.tsv`, `run_log.txt`, `settings_used.json`; per image a folder with
`dashboard.html`, `cells.tsv` (all metrics), `labels.tif`, kymographs, trace tables and `traces.png`.

## The dashboard

Open `dashboard.html` (per image) or `index.html` (per run) in a browser; no server or internet is needed.
All views are linked: hovering or selecting a cell anywhere highlights it everywhere.

| Panel | What it shows |
|---|---|
| **Screening** | live re-screening (below), with a timeline of the events, quality gates, hit criteria and output |
| **Image** | lifetime × intensity time-lapse with live LUT / range / brightness; outlines of hits or all cells; cells coloured by any metric; scale bar; the stage route. Large images load full-resolution tiles on demand while zooming |
| **Traces** | single-cell traces as lines, or — for crowded plots — median with 25–75 % / 10–90 % bands per group (hits, non-hits, selection) or a density map |
| **Kymograph** | all cells (sorted on response) × time |
| **Distribution** | histogram of the current frame, with hits and selection outlined |
| **Scatter** | any two per-cell values, log x / y, box or lasso selection |
| **Cell** | crop of the cell (plays with the time-lapse), its trace against the population, pass/fail of every gate and criterion |
| **Cells** | sortable table; export rows as TSV or the selection as `.rgn` |

Mouse and keys: click selects (Ctrl+click adds), Shift+drag selects a box or lasso (image, scatter; `L`
toggles) or a range (kymograph); drag pans, Ctrl+scroll zooms, double-click zooms to a cell; Space plays,
←/→ step, `Z` zooms to the selection (or the hits), `F` fits, Esc clears.

## Changing the hit criteria after the analysis

The **Screening** panel recomputes everything live in the browser from the stored traces; the browser
code (`templates/screening.js`) gives identical results to the Python pipeline (tested in
`tests/test_dashboard_js.py`).

- **Timing**: drag the S(timulation) and C(alibration) markers on the timeline; response window, margins,
  temporal smoothing and rise fraction.
- **Quality gates** and **additional-channel classification**: drag the thresholds in the histograms; each
  shows how many cells fail.
- **Hit criteria**: any number of criteria, each `AND` (required) or `OR` (at least one of the OR criteria
  must pass), with a draggable threshold on the metric's histogram and the number of passing cells.
  Alternatively, **Hits from: selection** turns hand-picked cells into the hits.
- **Output**: sort order, `.rgn` chunk size and **Compute route** (nearest neighbour + 2-opt, per chunk).
  The route is computed on request because it only makes sense once the hits are final; it is shown in
  the image and marked *outdated* when the hits change. The pipeline computes it at the end of `run` /
  `reapply`.
- **Hits → .rgn / TSV** export directly. **Settings → TOML** downloads the settings (and, in selection
  mode, the hand-picked hit list); apply them to the whole run (all images, combined hit list, `.rgn` files,
  index page) with:

  ```powershell
  uv run fast-hippos reapply experiment.toml --override screening_<image>.toml
  ```

Event frames are only written to the TOML when you changed them, so per-image automatic detection is kept.

## Large images

Images larger than `display.dashboard_max_size` (default 1024 px) are embedded as a down-sampled overview;
the full-resolution data is written as a tile pyramid (`<image>/tiles`, 512 × 512 px tiles) that the
viewer loads only for the visible area when you zoom in. Keep the `tiles` folder next to `dashboard.html`
when copying results. For the 1.9 GB test data set (4089 × 2556 px, 30 frames) see docs/SPEC.md §12.

## Differences from the Fiji macro

- Settings in a TOML file instead of dialogs; frames are 0-based and denote the *first* frame with the
  stimulus (Fiji manual frames "s,c" = `stimulation_frame = s + 1`, `calibration_frame = c + 1`).
- Stimulation/calibration detection uses a robust noise estimate; default `sensitivity = 5`.
- Cell lifetimes (TCSPC) pool the fitted amplitudes of all pixels: Σ(A1τ1 + A2τ2) / Σ(A1 + A2). Fiji averaged
  per-pixel lifetimes weighted by intensity, which is biased upward for dim cells (SPEC I19). Fiji thresholds
  therefore do not transfer 1:1.
- The Labkit step is replaced by a scikit-learn pixel classifier (`train-classifier`).
- Bugs listed in docs/SPEC.md §9 are fixed, including misaligned hit positions with position refinement.
