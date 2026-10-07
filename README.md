# FAST-HIPPOS (Python)

Python port of the [FAST-HIPPOS](https://imagej.net/plugins/fast-hippos) Fiji macro:
*FLIM Analysis of Single-cell Traces for Hit Identification of Phenotypes in Pooled Optical Screening*.

Segment cells, measure intensity-weighted lifetime (or ratio / intensity) traces per cell, detect
stimulation and calibration, find hit cells and write their stage coordinates as Leica `.rgn` files.
Every image gets a self-contained, interactive **HTML dashboard** (time-lapse lifetime/intensity viewer,
traces, kymograph, histograms, density plot, scatter plots and cell table, all linked) instead of dozens
of Fiji windows.

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

Open dashboards in a browser. In the dashboard: click to select cells (Ctrl+click adds), Shift+drag to
select a region, Space to play, ←/→ to step; export the selection as CSV or `.rgn`.

## Changing the hit criteria after the analysis

The **Screening** panel at the top of each dashboard recomputes everything live in the browser from
the stored traces: stimulation/calibration frames, response window, temporal smoothing, validity gates,
additional-channel classification and the hit criteria (AND/OR; drag the threshold in the small histogram
next to each criterion). Image outlines, traces, kymograph, histograms, scatter plot and table follow
immediately. The browser code (`templates/screening.js`) gives identical results to the Python pipeline
(tested in `tests/test_dashboard_js.py`).

- **Hits → TSV / Hits → .rgn** export the current hits directly (.rgn in chunks, with an optimized path).
- **Settings → TOML** downloads the settings; apply them to the whole run (all images, combined hit list,
  `.rgn` files, index page) with:

  ```powershell
  uv run fast-hippos reapply experiment.toml --override screening_<image>.toml
  ```

Event frames are only written to the TOML when you changed them, so per-image automatic detection is kept.

## Differences from the Fiji macro

- Settings in a TOML file instead of dialogs; frames are 0-based and denote the *first* frame with the
  stimulus (Fiji manual frames "s,c" = `stimulation_frame = s + 1`, `calibration_frame = c + 1`).
- Stimulation/calibration detection uses a robust noise estimate; default `sensitivity = 5`.
- Cell lifetimes (TCSPC) pool the fitted amplitudes of all pixels: Σ(A1τ1 + A2τ2) / Σ(A1 + A2). Fiji averaged
  per-pixel lifetimes weighted by intensity, which is biased upward for dim cells (SPEC I19). Fiji thresholds
  therefore do not transfer 1:1.
- The Labkit step is replaced by a scikit-learn pixel classifier (`train-classifier`).
- Bugs listed in docs/SPEC.md §9 are fixed, including misaligned hit positions with position refinement.
