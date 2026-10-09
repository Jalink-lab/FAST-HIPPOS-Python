# FAST-HIPPOS — behaviour specification for the Python port

Reference: Fiji macro **v0.9.5** as installed in Fiji (`Fiji.app/plugins/Macros/FAST-HIPPOS`)
(copied to `reference/fiji_v0.9.5/`). Line numbers below refer to
`reference/fiji_v0.9.5/FAST-HIPPOS_.ijm`. User documentation: <https://imagej.net/plugins/fast-hippos>;
workflow background: <https://github.com/Jalink-lab/dynamic-pooled-screening>.

> Version note: GitHub (`Jalink-lab/FAST-HIPPOS`) still holds the older line (internal number 6.65).
> v0.9.5 adds Labkit-based hit position refinement, stage-path optimization, additional-channel
> classification, Cellpose-SAM (`cpsam`) support and a fake time-lapse for single-frame screening,
> and drops the top-N `.rgn` file and the curve-fitting dialog.

Units: lifetimes in ns, time in s, pixel sizes in µm, stage coordinates in **m** (as in Leica metadata
and `.rgn` files), hit-position plots in mm.

---

## 1. Inputs and per-modality conversion

Loop over input files (`.tif`, `.lif`, `.fli`) and, for `.lif`, over all series.
Output base name: `<file stem>` or `<file stem> - <series name>` (slashes → dashes).

| Modality (`microscope`) | Reader | Intensity *I* | Lifetime τ (or ratio) |
|---|---|---|---|
| Fitted TCSPC data / TauSeparation | `.tif`: plain opener (keeps calibration); `.lif`: Bio-Formats | A1·τ1 + A2·τ2 (ch *n*, *n*+1 = amplitudes) | (A1·τ1 + A2·τ2)/(A1 + A2); NaN → 0 |
| TauContrast | Bio-Formats | ch *n* | ch *n*+1 · 0.097 − 1 (0–255 → −1…~24 ns) |
| Fast FLIM | plain opener | ch *n* | ch *n*+1 · 0.001 (ps → ns) |
| Frequency Domain FLIM (`.fli`) | Bio-Formats, series 1 minus series 2 (background); SPAD: median r=1 | from external `fdFLIM` plugin per block of `phases` frames | τφ or τmod |
| Ratio Imaging | plain opener | C1 + C2 | C1/C2 with zeros → NaN |
| Intensity only | plain opener / Bio-Formats | image | image with zeros → NaN |

*n* = `intensityChannel` (default 1), τ1 = 0.6 ns, τ2 = 3.4 ns defaults.
Frame interval from metadata, else `default_frameInterval` (5 s).

**Single-frame + screening (new in 0.9.5):** the frame is duplicated to make a 2-frame "time-lapse".

### Optional preprocessing (in order)
1. Remove last frame (`removeLastFrame_boolean`).
2. **XY drift correction** (`correct_drift`): registration image = summed component channels
   (TCSPC/ratio) or the intensity channel; optional variance filter r=2 (`edge_detect`); zero-pad
   top-left to a 2ᴺ square; FFT cross-correlation (FD Math "Correlate") of each frame against first /
   last / previous frame; Gaussian blur σ=4 on the CC; per-frame argmax (x, y) → shift = argmax − dim/2
   (cumulative for "previous"). Integer translation of all channels (bicubic only if `subpixel`, off).
3. **Bidirectional phase correction** (`correct_bidirectional_phase`, applied to the intensity stack):
   split odd/even lines, sum-project, FFT cross-correlate, Gaussian fit to a 32-px profile through the
   CC centre → shift = μ − 15; shift halves by ±shift/2 (cubic), re-interleave, crop to original size.

---

## 2. Segmentation

**Segmentation image:** sum projection over frames `[CellposeStartFrame, CellposeEndFrame]`
(−1 = all) of the intensity stack, or of `segmentationChannel` if set. Optional gamma 0.5 + 0.35 %
saturation (`equalize_contrast_cp`). The projection is kept as `intensity` (used for RGB overlay,
statistics, Labkit).

**Conversion before Cellpose:** NaN → mean of pixels below the 5th percentile; contrast stretch at
0.35 % saturation; scale to 16-bit.

**Backends:**
- Cellpose 3 via BIOP wrapper (`cyto3`, `cyto2_cp3`, `nuclei`, custom) — `diameter`, `flow_threshold`
  (default 1.0), `cellprob_threshold` (default 0), `--use_gpu`, single channel.
- Cellpose-SAM (`cpsam`) via "Cellpose SAM..." with a separate env.
- Load labelmap from disk (`load_labelmap_boolean`).
- Manual: freehand ROIs → labelmap (whole image if none drawn).
- Nuclei route (`nucleiChannel != −1`, legacy): Cellpose (old wrapper) on cell+nuclei 2-channel image,
  StarDist "Versatile (fluorescent nuclei)" (prob = `StarDistProbThreshold`, nms 0.3) on nuclei,
  then nucleus→cell assignment by maximum Jaccard overlap; cells without nucleus are kept.
- On Cellpose failure: wait 60 s and retry (indefinitely).

**Label filtering** (CLIJ2), then labels are renumbered 1..N:
1. Size ≥ `minCellSize` pixels.
2. Circularity < `maxCircularity` (MorphoLibJ "Analyze Regions") — see issue I5.
3. Mean intensity (on `intensity`) ≥ `minCellBrightness`.

`Cell_statistics.tsv` = CLIJ2 `statisticsOfLabelledPixels(intensity, labels)` (row *i* ↔ label *i*+1):
area (`PIXEL_COUNT`), `MEAN_INTENSITY`, centroid, bounding box, ….

**Segment first, analyze later** (`segmentFirstAnalyzeLater`, default on, needs equal dimensions):
concatenate all files, segment once, save `labelmaps/labelmap_cells_NNNN.tif` and
`intensities/intensity_NNNN.tif`, then re-run the file loop loading these.

---

## 3. Measurement — the kymograph

Core data structure: 2-D float array, **x = cell index (label − 1), y = frame**.

For each cell *c* and frame *t* (pixels *p* in the cell, *I* masked to pixels where τ ≠ 0):

    τ_c(t) = Σ_p τ(p,t)·I(p,t) / Σ_p I(p,t)

(implemented as mean(τ·I)/mean(I) over the ROI via ROI-Manager multi-measure).

**Python port (decision 2026-10-08): pooled cell values instead** (issue I19):
TCSPC τ_c = Σ(A1τ1 + A2τ2) / Σ(A1 + A2); ratio = ΣC1 / ΣC2; Fast FLIM / TauContrast / FD-FLIM keep
Σ(τ·I)/ΣI, which for mean-arrival-time lifetimes already equals the lifetime of the pooled photons.

Derived:
- **Smoothed kymograph**: box mean along time only, radius `smoothRadiusTraces` (0 = off).
  Used for plots/hit detection when > 0.
- **Additional-channel kymograph** (`additionalChannel`): per-cell mean intensity of that channel per frame.
- Population **mean trace** (mean over cells per frame) and per-frame standard deviation over cells.
- Optional tables: `<name>_lifetime.tsv` (frames × cells + `time (s)`), `<name>_intensity.tsv`,
  `<name>_intensity_ch<k>.tsv`.

---

## 4. Stimulation and calibration frames

**Manual** (`manualStimCalFrames`): `"s,c"`; `"0"` = baseline-only (s = T, c = −1);
`"0,c"` = baseline + calibration only (`calibrationOnly`).

**Automatic:**
1. d1 = `differentiateArray(mean trace)`, d2 = `differentiateArray(d1)` (see issue I8 for the exact,
   slightly shifted definition — must be replicated to reproduce frames).
2. Peaks of d2 via `Array.findMaxima(d2, stimulationSensitivity · std(d2))` (prominence-based,
   returned in order of decreasing amplitude).
3. 0 peaks → s = 0, c = −1 (whole trace is response); 1 peak → s = peak − 1, c = −1;
   ≥ 2 peaks → the two strongest, ordered in time: s = first − 1, c = second − 1.

Saved as `<name>_Stim_&_Cal_frames.txt` (`s<TAB>c`).

**Sorted kymograph:** per cell, mean τ over `[s, c−1)` (or `[s, T)` without calibration, or whole trace
in baseline-only mode); cells reordered by `Array.rankPositions(response)` (exact left/right orientation
of the saved image to be verified against Fiji output). The rank vector is saved
as a 1-px-high image (needed by the inspection tool).

---

## 5. Visualizations (all optional except traces plot)

- **Traces plot**: all cells (Glasbey colours from the labelmap LUT; if ≥ 255 cells, colours are sampled
  as `lut[label/N·255]`), black mean trace (width 3), y-limits `[minLifetime, maxLifetime]`, text
  "N traces" and smoothing radius. Single frame → histogram plot instead.
- **Per-frame histograms** (50 bins in `[minLifetime, maxLifetime]`) as a plot stack + **density plot**
  (image: time × bins, counts, Turbo LUT, flipped so lifetime increases upward).
- **Per-frame scatter plots**: τ vs `MEAN_INTENSITY` of the projection (log x), τ vs `PIXEL_COUNT`
  (linear x), τ vs additional-channel intensity (log x).
- **RGB lifetime–intensity overlay**: τ zeros → NaN, NaNs filled ("Remove NaNs", radius = xy radius),
  3-D mean sphere (`smoothRadiusOverlayXY`, `smoothRadiusOverlayTime`); LUT on `[min, max]`; RGB;
  each channel × intensity (image or movie, contrast stretched with saturation
  10^(0.5·(`RGB_brightness`−2)) %, 16-bit); calibration bar overlay.

---

## 6. Screening (`runScreen`)

Settings come from a second dialog and are persisted in IJ Prefs.

### 6.1 Windows (per cell; s, c as above; T frames)
- baseline = `[0, s)` (length `baselineLength = s`, min 1); calibrationOnly: `[0, c−2)`
- response = `[s+1, c)` (calibrationOnly: `[c−2, c−1)`, i.e. a single frame)
- calibration = `[c, T)` (calibrationOnly: `[c−1, T)`); if c = −1 → c = T−1
- timed response window: length *w* (`hit_avg_response_time_window`, −1 = full response, margin forced 0),
  margin *m*; anchored
  - "after stimulation": start = min(s + m + 1, c)
  - "before calibration": start = max(c − m − w + 1, s + 1)
  - *w* clipped so the window stays within `[s, c]`; slice `[start−1, start−1+w)`.
- population: average baseline (NaN-aware mean over cells and baseline frames), response, calibration.

### 6.2 Validity gates (always ANDed)
- `baseline_calibration_difference`: low ≤ (mean_cal − mean_base) ≤ high (default 0.5–1.0 ns, on)
- `baseline_avg_baseline_difference`: (mean_base − population baseline) ≤ X (default 0.2 ns, on; one-sided)

### 6.3 Criteria (each optional, "lower"/"higher" than threshold; combined with OR / AND)
| Column in hit list | Quantity tested |
|---|---|
| `mean baseline` | mean τ over baseline |
| `mean response` | mode *absolute*: mean τ over timed window; mode *difference with baseline*: mean(response − own baseline) over the **full** response (I6); mode *fraction*: mean timed diff / max diff |
| `max response` | max τ over full response |
| `max response difference` | max(response − own baseline) |
| `max response diff to avg baseline` | max(response − population baseline) |
| `rise time (frames)` | first index z where response_diff ≥ 0.75·max_diff; reported z+1; slower: z > N−1, faster: z < N−1 |
| `rapid response ratio` | mean diff of 2nd half / mean diff of 1st half of the response |
| `mean additional channel intensity` | additional channel, time-average or first frame; lower / higher / between |

Plus **random hits** mode (N random cells) for testing.

AND logic: a hit is kept only if *all* criterion columns between `Cell` and `Tile` are non-zero (I7).

**Python port:** every criterion has its own logic (`logic = "AND"` or `"OR"`, default `screening.logic`):
hit = valid AND (all AND criteria pass) AND (at least one OR criterion passes, if there are any). With a
single global logic this reduces to the Fiji behaviour. `screening.manual_hits` (TSV with `cell` and
optionally `image`) replaces the criteria by a hand-picked list (e.g. exported from a dashboard selection).
Sorting on a chosen column, "highest first" via table reversal.

### 6.4 Additional-channel classification (new, `classifyCellsUsingAdditionalChannel = true`, hardcoded)
log10(time-mean intensity per cell) → Otsu threshold → **interactive** adjustment on an 80-bin
log-histogram (−1…3) → `Class` (0/1) and `ch<k> intensity` columns in the cell-coordinates and hit
tables; hits with Class 1 drawn red in the hits scatter plot.

### 6.5 Hit positions
**Stage positions** (list X0, Y0, X1, Y1, … in m), from, in order:
1. stitched-image Info metadata written by `Stitch_tiles.ijm`
   (lines: `Stitched image with tile layout:` / `nx,ny` / `Stage coordinates:` / `x0,y0,…` /
   `Tile size (um):` / `w,h` / `overlap (%):` / `o`);
2. `.lif` file via Bio-Formats `PlanePositionX/Y` per series (`Get_stage_coordinates_to_log_window.py`);
3. tile layout from counting unique values (`find_tile_layout`).

Tile size (m) from metadata, else `width / (nx − (nx−1)·overlap) · pixelWidth`.

**Pixel position within the cell:** label centroid, or — new, `refinePositions_boolean` — the intensity
centre of mass of a **nucleus probability map** inside the label eroded by 2 px:
`intensity` normalized by its Otsu threshold → Labkit classifier (`Labkit_FAST_HIPPOS_nuclei_classifier.txt`,
channel 3 = nuclei) → p < 0.5 set to 0 → morphological opening (disk r=1) → squared → CLIJ2
`MASS_CENTER_X/Y` per eroded label; NaN → centroid.

**Absolute position** (axes deliberately swapped and negated — must be reproduced exactly):

    AbsPosX = −stage[2·tile+1] − tileSizeX/2 + x_px·pixelWidth/1e6
    AbsPosY = −stage[2·tile]   − tileSizeY/2 + y_px·pixelHeight/1e6

Negative overlap (stitched file, scanned right-to-left): tile index = nx − 1 (upper-left tile).

### 6.6 Screening outputs
- `<name> (Hit list).tsv` + `HITS_<name>.rgn` (all hits).
- Chunks of `maxNrHits` (default 1000): `(Hit list a-b).tsv` + `HITS_<name>_a-b.rgn`.
  Optional **path optimization** per chunk (new): start at the hit closest to (0,0), greedy nearest
  neighbour using the 100 nearest neighbours, then 2-opt (best swap for the longest segments first,
  skip segment pairs shorter than 10 µm in total, max 1000 iterations / `maxOptimizationTime` s).
- `.rgn` format: Leica LAS X `StageOverviewRegions` XML; one CompoundShape "hits" with Point children
  (`<X>`, `<Y>` in m, 10 decimals, `Tag Cell_<i>`, random UUID per item) + StackList entries.
- Hits-only traces plot with baseline / response windows drawn and shaded.
- Hit / non-hit kymographs, histograms, density plots; hit-position map (mm, one colour per chunk, tile
  outlines); `Cell_coordinates.tsv` (all cells, all tiles: Tile, Cell, Cell total, px and m positions);
  `Stage_positions.txt`.

### 6.7 Re-apply mode (`reapply_boolean`)

**Python port:** screening can be changed interactively in each dashboard (live recompute in the browser by
`templates/screening.js`, a line-by-line mirror of `events` / `screening` / `kymograph.smooth_time`;
parity is tested on 160 parameter combinations with identical results, and the dashboard -> TOML ->
`fast-hippos reapply --override` round trip reproduced the identical 334 hits on the 50_50 crop).
`fast-hippos reapply` re-runs events, metrics, hits, outputs and dashboards from the saved traces.

Fiji re-apply mode:
Skip segmentation and measurement; reload from the output folder: labelmap (with stage metadata in
Info), ROIs, kymograph(s), rank vector, additional-channel kymograph, intensity, traces plot (for the frame
interval), stim/cal frames; then rerun hit finding only.

---

## 7. Per-image outputs

`(weighted lifetime).tif`, `(labelmap_cells).tif`, `(intensity & labelmap).tif`, `(kymograph).tif`,
`(kymograph sorted).tif`, `(kymograph smoothed).tif`, `(kymograph additional channel).tif`,
`(rank vector).tif`, `(lifetime traces plot).tif`, `(lifetime & intensity RGB overlay).tif`,
`(lifetime histogram).tif`, `(density plot).tif`, `(scatterplot MEAN_INTENSITY|PIXEL_COUNT|ch<k>).tif`,
`(ROIs).zip`, `_Cell_statistics.tsv`, `_lifetime.tsv`, `_intensity.tsv`, `_Stim_&_Cal_frames.txt`,
`_log.txt`.

---

## 8. Companion tools

- **Stitch_tiles.ijm** — Grid/Collection stitching (snake by rows; Right & Down, or Left & Down for
  negative overlap), no registration; pixel size corrected by (w−1)/w (Leica export error); writes the
  Info metadata block of §6.5.
- **Inspect_and_select_traces_.ijm** — interactive: hover/click in RGB overlay, traces plot or sorted
  kymograph highlights the same cell in all views; click opens a zoomed single-cell movie; ctrl-drag on
  the sorted kymograph or a ROI selects multiple cells → `Selected_cells` table + `.rgn`.
  Python equivalent: a napari widget (later phase).

---

## 9. Known issues in v0.9.5 and how the Python port handles them

Decision (2026-10-08): fix all bugs in the port. Fiji line numbers refer to `reference/fiji_v0.9.5`.

| # | Issue in Fiji v0.9.5 | Location | Python port |
|---|---|---|---|
| I1 | FD-FLIM parameters (`phases`, `freq`, `reference`, `tau_ref`, `tauPhiOrTauMod`, `FDFLIM_SPAD_camera`) are commented out but used -> FD-FLIM path crashes | L56-62, L3162, L3698ff | fixed: `[fdflim]` settings; phase/modulation lifetimes computed in `modalities.fd_flim` (no external plugin). Reading `.fli` itself still needs a reader (TIFF/npy phase stacks work) |
| I2 | `hit_max_response_to_avg_baseline_choice` undefined -> crash for "relative to avg baseline" + "higher" | L2747 | fixed: separate metric `response_max_diff_pop` with its own op |
| I3 | `singleFrame == true;` is a comparison, not an assignment | L693 | fixed (no global state) |
| I4 | `x == NaN` is always false -> NaN traces are never invalidated | L2585, L2587 | fixed: NaN fails every gate and criterion |
| I5 | Circularity filter misaligned (mask from labels before size filtering, applied after relabelling); filtered cells get mean 0, which passes with `minCellBrightness = 0` (default) -> effectively no filter; circularity can be > 1 | L3984-3998 | fixed: all filters on the same label ids; circularity clipped to 1 |
| I6 | "mean response difference" ignores the time window; in absolute/fraction modes the `mean response` column stores the untimed mean, not the tested value | L2617, L2641-2671 | fixed: separate metrics, all `mean` metrics use the timed window; reported = tested value |
| I7 | AND logic counts non-zero criterion columns -> a true value of 0 fails; depends on column order | L2904 | fixed: boolean `pass_<metric>` columns |
| I8 | `differentiateArray` drops the last difference; peak - 1 compensates | L4625 | fixed: centred 2nd derivative; same frames for interior transitions |
| I9 | `optimizePath` reorders only `AbsPosX/AbsPosY`; saved chunk tables then mix positions and cells | L1379-1380, L1237 | fixed: whole rows reordered, `visit_order` column |
| I10 | `register_hit` reads `intensity ch<k>` from the wrong row (off by one, ignores tile offset) | L3008 | fixed (one table per image, indexed by cell) |
| I11 | `Y (um)` uses `pixelWidth` | L3001 | fixed |
| I12 | Only rising responses (rise time, gates) | - | kept, documented (the baseline-deviation gate is now two-sided: abs(cell - population) <= X) |
| I13 | ImageJ string `==` is case-insensitive | various | fixed (enum) |
| I14 | Position refinement: coordinate rows misaligned with labels. **Observed in real Fiji output** (Fiji output of the `Allchannels_merged_50_50` data set): only 70 of 4935 hits (1.4 %) have their `.rgn` position inside their own cell; e.g. hit "Cell 9" carries the position of label 10, "Cell 11" of label 13. Lifetime criteria are evaluated on the correct cell, so the coordinates point at different cells. Without refinement (centroids) positions are correct. Probable cause: the CLIJ2 erodeLabels / statistics step renumbers or drops labels (not verified in Fiji). | L2338-2400 | fixed: positions indexed by label id; vanished labels fall back to the centroid |
| I15 | "Smooth traces" is documented to apply to hit detection, but `find_hits` receives the unsmoothed kymograph | L923 | fixed: smoothed kymograph used for metrics when `smooth_traces > 0` |
| I16 | Separate tile files without stitched metadata: tile size = single-tile width / number of tiles -> wrong tile offset | L1293ff | fixed: one image = one tile |
| I17 | Stim/cal detection threshold = sensitivity x std(d2); std is dominated by the transitions, so a large calibration step hides a clear stimulation (seen on synthetic data: stimulation peak 20x noise, missed) | L3073 | changed: robust noise sigma (MAD); default sensitivity 5. Fiji sensitivity values do not transfer |
| I18 | Calibration window starts one frame before calibration (includes the last response frame), while the response window excludes it | find_hits | fixed: calibration = [calibration_frame, end) |
| I19 | Cell lifetime (TCSPC) = intensity-weighted mean of per-pixel amplitude-weighted lifetimes. Since I_p = (A1+A2)·τ_p, a pixel's weight grows with its own lifetime: the result is >= the amplitude-weighted lifetime of the cell, with equality only if all pixels have the same lifetime. Pixel noise therefore biases it upward, most for dim cells. Synthetic (~40 photons/px): bias +0.037 ns (pooled: +0.0001 ns), noise sd 0.027 vs 0.021 ns. Real 50_50 crop: median baseline 2.388 (Fiji) vs 2.308 ns (pooled); dimmest 20 % of cells +0.072 ns, brightest +0.006 ns; median response amplitude 0.734 vs 0.787 ns | measure_lifetime_traces | changed: pooled amplitudes per cell (only option). Thresholds from Fiji screens do not transfer 1:1 |

## 10. Validation against Fiji (real data)

`Allchannels_merged_50_50.tif` (TCSPC, 2 lifetime components + additional channel), 1024 x 1024 centre crop, Fiji labelmap cropped identically,
manual frames Fiji "5,26" = Python 6/27. 976 cells fully inside the crop. The lifetime comparison
was made with the Fiji estimator (`kymograph.weighted_lifetime`, still used for Fast FLIM / TauContrast);
the default TCSPC estimator is now the pooled one (I19), which deliberately differs:

| Quantity | max |Python - Fiji| |
|---|---|
| weighted lifetime kymograph (30 frames) | 4.8e-7 ns |
| additional-channel kymograph | 0 |
| cell area | 0 px |
| centroid | 0.005 px |
| absolute stage position (centroid) | 0.12 um (pixel = 1.52 um) |

Cellpose 3 (cyto3) and Cellpose 4 (cpsam) run from their own separate Python environments
(1037 and 1106 cells on the crop, ~45 s each including model loading).

## 11. Python design (as implemented)

| Module | Content | Fiji counterpart |
|---|---|---|
| `config` | TOML settings (dataclasses) | script parameters, dialogs, IJ Prefs |
| `io` | TIFF / .lif / .npy reading, calibrated TIFF writing | Bio-Formats, Jython helper |
| `modalities` | intensity and lifetime per modality (incl. FD-FLIM) | `calculate_lifetime_and_intensity_*` |
| `preprocess` | drift and bidirectional correction (on raw channels) | `correct_drift`, `correct_bidirectional_phase` |
| `segmentation` | projection, Cellpose 3/4 (in-process or other env), labelmap, threshold; filters; statistics | `segment_cells*` |
| `pixel_classifier` | random-forest nuclei classifier (replaces Labkit) | Labkit |
| `kymograph` | per-label weighted lifetime via `np.bincount`, temporal smoothing | `measure_*` |
| `events` | stim/cal detection, windows, response order | `measure_lifetime_traces` |
| `screening` | metrics, gates, criteria, classification | `find_hits` |
| `stage` | stitched metadata, tile geometry, positions, path optimization, `.rgn` | `register_hit`, `optimizePath`, `generate_rgn_file` |
| `pipeline` | per-image processing, re-apply, run-level screening output | main macro body |
| `dashboard`, `viewer_data`, `templates/` | self-contained HTML dashboards + run index | all image/plot windows, Inspect_and_select_traces |
| `cli` | `fast-hippos run / reapply / init-config / train-classifier / demo` | - |

Dashboard (`templates/dashboard/*`, assembled into one self-contained HTML by `dashboard.py`):
`core.js` (state, layered redraw scheduling, selection), `plot.js`, `viewer.js` (overview + lazily loaded
tile pyramid; tiles are `.js` files calling `FHTile(key, dataURL)` so they load from `file://`),
`traces.js` (lines / quantile bands / density), `kymo.js`, `dist.js`, `scatter.js`, `cellcard.js`,
`table.js`, `screenui.js` (live screening panel, histogram sliders, timeline, route), `export.js`,
`main.js`. Every panel draws on separate canvas layers (base / selection / hover) so hover stays cheap with
thousands of selected cells.

Still open: `.fli` reader; StarDist nuclei route (macro "to do"); manual segmentation (draw in napari or
Fiji and load as labelmap); dashboard size for long/large data (frames are lossless PNG: ~1.4 MB per
1024^2 frame on noisy data).

## 12. Large images (tested on the full data set)

`Allchannels_merged_50_50.tif`: 4089 × 2556 px, 30 frames, 3 channels, 1.9 GB; Fiji labelmap (10239 cells).

| Step | Result |
|---|---|
| `fast-hippos run` (labelmap, screening, tiles) | 2.5 min |
| `fast-hippos reapply` (screening + dashboards, no segmentation) | 30 s |
| dashboard.html (overview 1:4, all 30 frames embedded) | 45 MB |
| tiles (levels 1:1 and 1:2, 512² px, 1280 + 360 files) | 526 MB |
| browser: zoom to full resolution, step 10 frames | ~55 ms per frame including tile loading; 160 MB JS heap |
| hover with all 1066 cells selected (crop data set) | 3 ms (was 78 ms before layering) |

Tiles are only written when the image is larger than `display.dashboard_max_size`; `dashboard_tiles = false`
skips them (the dashboard then shows the overview only).

