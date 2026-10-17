# Interactive run Overview: design

## Decisions of the user (2026-10-17), overriding the recommendation below where they differ

1. Both goals in the first version: screening (table, per-image hit maps, .rgn exports) and comparing samples
   (response over time, metric distributions / scatter, QC).
2. Per-cell data embedded in the page (up to 5000 cells per image, all hits kept, about 0.5 MB per image): accepted.
3. No 'Stage layout' mode in the first version.
4. QC flags as proposed, but only where they apply: not all experiments have a calibration, or even a stimulation
   (events.baseline_only, or nothing detected / set). No 'events missing' or 'no calibration response' flags when the
   experiment has no such stimulus. The comparison of samples must also work when the run did not screen (no hits:
   hide hit columns, hit maps and hit exports, keep table, QC, response and distributions).
5. Usually one protocol: overlaid curves, aligned on the stimulation when there is one (otherwise on frame 0 / time),
   with each image's curve switchable on and off.
6. Table columns as proposed, without route length (things can be added later).

Estimate: a few hours of session work in the build steps below; commit after every step.

---

Recommended design: interactive Run Overview for FAST-HIPPOS

Judgement of the three designs

- Reuse-first. This is the best base. It has the lowest build risk because the page is assembled from drawing code the dashboard already runs. It also looks and behaves like the dashboard. Each step leaves a working page that is better than today's. Its weak points:
  - The golden-angle cellColor gives loud colours that do not change with the theme, which does not fit the subtle UI the user wants.
  - Overlaid histograms get hard to read with more than about 3 images.
  - It has no QC signals.
  - Its hits table and .rgn exports are thin.
- Quality-comparison. Most useful of the three when the images are different samples, which is the stated need. Its strengths are QC flags in Python with the threshold stated in each tooltip, a per-image distribution layout, and a shared common.css/common.js. It is also the heaviest:
  - ten QC rules, KDE violins, a scatter panel and a figure export;
  - a pipeline change to keep drift shifts;
  - per-cell columns of up to 20,000 cells per image.
  
  That is a lot of build and tuning risk for the first version.
- Screen-operator. Best on the practical microscope side:
  - a hits table with global rank, chunk and visit order;
  - .rgn export per image, for the selection and for the original chunks, with the same chunking and naming as Python;
  - a test that compares the JS .rgn output with stage.write_rgn;
  - an explicit "Stage layout" mode for runs where the images are positions on one slide;
  - a "started / reapplied" chip, and a hover thumbnail.
  
  Its histogram-only approach, without per-cell data, rules out a scatter view.

The recommendation below uses reuse-first as the skeleton. It adds the colour tokens, the shared common files, a small QC flag set and per-image distribution rows from quality-comparison. From screen-operator it takes the hits table, the export set, stage layout mode and the thumbnails.

1) What the user gets

- index.html stays a single self-contained page, opened from file:// or through the GUI, and it reloads automatically after a reapply.
- Images are treated as separate samples. Each image has one fixed colour, used in every panel.
- At the top is a sortable images table with multi-select. Each column has a hover explanation, and a few clear QC flags point at images that need a closer look.
- Selecting rows fills three linked comparison panels:
  - population response over time;
  - per-image metric distributions, or a metric-vs-metric scatter;
  - one small hit map per image.
- A hits table for the selection links straight to dashboard.html#cell=N.
- Exports: .rgn files (per image, for the selection, or the original run chunks), TSV tables and PNG.
- The light/dark theme and the ◐ toggle are the same as in the dashboard.

2) Layout and panels

The page uses the dashboard's grid, panel and chip styles, from a shared common.css.

Header:
- Logo, run title (out.name).
- Chips:
  - images;
  - cells (valid %);
  - hits (% of valid);
  - unit;
  - screening on/off;
  - "started / reapplied <time>" from run.json;
  - a selection chip ("3 of 12 images · 4,210 cells · 37 hits") when anything is selected.
- On the right: ◐ theme toggle, an Export menu and a Run files menu. Run files is grouped as Tables, Regions, Plots, Logs/settings and Stitched.

Panel A, Images table:
- Full width, 24 px rows, plain <table>. No virtual scrolling is needed below about 200 images.
- A thin QC strip under the table holds one chip per active flag type, for example "2 images: low valid %". Clicking a chip selects the flagged images, and hovering it shows the rule and its threshold.

Panel B, Population response (left, about 60 %):
- Default "overlay": one band per selected image, in its colour. Each band is the 25-75 % range with the median line. The outer 10-90 % band is drawn only when exactly one image is selected. Above 6 selected images only the medians are drawn.
- Toggle "small multiples": one mini plot per image with a shared y axis. Each mini plot shows the 10/25/50/75/90 % band, the hit median as a --hit line, and its own window shading. Use this when the protocols differ.
- X axis: seconds relative to the stimulation frame (default), or frames.
- Window shading comes from shadeWindows. In overlay mode it uses the first selected image, with a note "windows of <image>" when the selected images have different events.
- Toggles: "all valid cells" or "hits only", and "lock y to whole run" so the axis does not jump when the selection changes.

Panel C, Metric (right, about 40 %):
- The metric selector uses the dashboard scatter's option list and the config.METRICS descriptions as tooltips, with a log toggle.
- Mode "distribution" (default): one row per selected image, in table order, on a shared metric axis. Each row is a normalised histogram in the image colour, with a quartile box and median, and the hits as --hit ticks. Thresholds of criteria that use this metric are dashed vertical lines, with the criterion text as tooltip. Hovering a row shows n, median, IQR and the fraction passing.
- Mode "scatter": metric X against metric Y for the cells of the selected images, coloured per image. Hits get a --hit ring. Log axes are optional. The code is adapted from scatter.js.

Panel D, Hit positions:
- Only shown when screening is on and at least one image has stage geometry.
- "Per image" (default): small multiples of about 220 px, one per selected image, each on its own tile extent. Details are in section 4.
- "Stage layout": one shared stage-coordinate map. Each image's tile footprint is filled lightly in its colour, its hits are dots, and the chained run route is drawn in --accent. Use this when the images are positions on one slide, which is the "not always different samples" case.

Panel E, Hits (collapsed by default):
- Hits of the selected images, sortable.
- Columns: swatch and image, global rank, chunk, visit order, cell, x and y in mm, the criterion metrics, and the sort_by metric.
- Ranks and visit order stay run-global, so they can be compared between images.

On narrow screens all panels stack in one column. Every panel title has a short hover explanation.

Images in scope:
- An empty selection shows the hint "Select images in the table" in B, C and D.
- On first load all images are selected if there are 6 or fewer, otherwise the first 6.
- Small multiples cap at 12, with the notice "showing 12 of N".

3) Images table columns

Every header has a tooltip. All columns sort, and numbers are right-aligned. Columns without data in this run are hidden.

- Checkbox and swatch: the image's fixed colour, the same in all panels.
- #: run index.
- Image: the name, linked to <img>/dashboard.html. When display.dashboard is off or the file is missing, it is plain grey text with the tooltip "dashboard not written (display.dashboard off)". This fixes today's dead link.
- QC: a dot (ok / warn / bad). Its tooltip lists the flags that fired, with value and threshold.
- Cells: number of segmented cells.
- Valid: cells that pass the validity gates (baseline deviation, calibration difference), as count and %.
- Hits: hit count. Screening only.
- Hit %: hits / valid, with a thin inline bar in the image colour. The tooltip gives the run median.
- Baseline: median baseline_mean over valid cells, in the run unit (ns for lifetime).
- Response: median of the first criterion's response metric over valid cells (default response_mean_diff). The tooltip names the metric.
- Hit response: median of the same metric over the hits only.
- Cal Δ: median calibration_diff. It checks that the calibration stimulus worked.
- Frames · Δt: T and the frame interval in s, for example "300 · 2.0 s".
- Stim / Cal: event frames, with a small tag "auto" (detected) or "set". "–" means not found. A frame in warning tint differs from the run's most common value.
- Class+: % of cells with class_additional = 1. Only when an additional channel is used.
- Area: number of tiles and scanned area in mm².
- Route: route length in mm through this image's hits, and the chunk ids it belongs to, for example "12.4 mm · 1, 2". Screening only.
- Folder: link to the image folder.

Optional columns (Cal Δ, Hit response, Area, Route) can be shown or hidden with a column chooser (⋮), remembered in localStorage.

A cell is tinted with --warn or --bad only when a QC rule fires on its value. There is no other colouring.

QC flags (computed in Python, thresholds in one module constant, shown in tooltips; warnings only, they never filter anything):
- few_cells: fewer than 25 % of the run median, or fewer than 20 cells.
- low_valid: valid fraction below 70 % (warn) or below 40 % (bad).
- events_missing: stimulation or calibration not found while the settings expect it.
- event_offset: the stimulation frame differs from the run's most common frame by more than 3 frames. The tooltip says this only applies when all images share one protocol.
- no_cal_response: |Cal Δ median| below 2 × the median of baseline_dev_pop.
- no_geometry: screening is on but the image has no stage positions, so its hits cannot be visited.
- zero_hits: information only.

4) Interactions

Selection follows file-manager conventions:
- Click a row: select only that row.
- Ctrl/Cmd-click or the checkbox: toggle the row.
- Shift-click: select a range in the current sort order.
- Header checkbox: select all or none. Esc: clear.
- ↑/↓ moves focus, Space toggles, Enter opens the dashboard.
- The table's sort order sets the order of images in panels B, C, D and E.

Single image versus several:
- One image: B shows its full band plus its hit band. C distribution mode colours hits and non-hits as in dist.js. D shows one larger map.
- Several images: each image draws in its own colour. The table swatches serve as the legend, so no separate legend is drawn.

Linked hover:
- Hovering a table row brings that image's band to the front and thickens it, outlines its histogram row, its points and its map, and fades the other images to 35 %. Hovering an image in any panel highlights its table row.
- The row tooltip shows a small projection thumbnail (open decision 1).
- Hovering a hit on a map or in the hits table highlights it in both.

Hit maps:
- Units are mm with y up (-abs_y, as in Fiji), equal aspect, and a scale bar instead of axes.
- Contents: tile outlines in --line, hits as --hit dots, and the route polyline in visit order in the image colour, with a start marker.
- When a chunk crosses images, each map draws its own part of the route plus a faint stub where the route leaves the image, with "from <image>" at the start.
- Toggle "same scale": all maps use the same mm per pixel.
- Images without geometry get a "no stage positions" placeholder card.
- The hover tooltip shows cell, rank, chunk, visit order and x/y in mm.

Links to dashboards:
- From the image name, Enter on a row, the ↗ on each small-multiple header, a map dot, a scatter point or a hits row. Hit links go to dashboard.html#cell=N, which main.js already handles.
- All hrefs are relative, so the output folder stays movable. Under the GUI, the dashboards are below the root that open_path already adds (p.parent for index.html), so no GUI change is needed.
- Each dashboard header gets a "↑ Overview" link to ../index.html, shown only when that file exists.

Exports (Export menu). Each uses download(), so they work from file://. The default scope is the selection, with "All images" as an option.
- RGN per image: HITS_<run>_<image>.rgn in visiting order, split into _a-b files at screening.max_hits_per_rgn, with the same naming as Python.
- RGN for the selection, combined: one route across the selected images. When screening.optimize_path is on, it is re-optimised with FHScreen.optimizePath, starting from the centre of the first tile of the first selected image (Python's rule), and chunked the same way.
- Original run chunks: links to the existing HITS_<run>_<a>-<b>.rgn files.
- Hits TSV: the hits table columns, for the scope.
- Images TSV: the table as shown, in the current sort order, with the QC flags. The same table is also written to disk as run_summary.tsv.
- Cells TSV: the per-cell columns embedded for the scope. Note that these may be a subsample (section 5).
- PNG of the current panel, composited on the theme background with a colour-to-name legend.

Persistence follows the dashboard convention (key "fast-hippos:" + location.pathname, every access in try/catch, values validated on restore):
- localStorage: theme, hidden columns, chosen metric(s), log flags, trace mode, x axis, axis lock, map mode.
- sessionStorage: selection, sort, scroll, so they survive the _WATCH reload after a reapply. Restored image names are checked against the current data.

5) Data to add at run time

All of this is embedded in index.html and computed from arrays already in memory. The only new file on disk is run_summary.tsv. Raw kymos are not embedded.

New function: build_overview_data(results, settings, out, hits_df, thumbs), in a new overview.py. write_index becomes a thin wrapper that calls it.

Per image:
- Identity:
  - name, index, folder;
  - href, null when no dashboard was written (check display.dashboard and Path.exists);
  - n_cells, n_valid, n_hits, frames, frame_interval, unit;
  - the full Events.to_dict(), for window shading and the auto/set tag.
- Table scalars:
  - medians, and IQR where useful, of baseline_mean, the response metric, calibration_diff and mean_intensity;
  - hit-response median;
  - class+ %;
  - tile count and area in mm²;
  - route_mm and chunk ids;
  - the flag list.
- Bands: 10/25/50/75/90 % per frame of kymo_smoothed, for valid cells and for hits, computed with np.nanpercentile(axis=1). Stored with float_b64 as 2 × 5 × T Float32, about 12 kB per image at T = 300.
- Per-cell columns:
  - cell, hit, valid, abs_x_m, abs_y_m, the numeric METRICS columns, area_px, mean_intensity, circularity;
  - each column stored as Float32 b64;
  - capped at 5,000 cells per image as a seeded random subsample that always keeps every hit, with a "subsample n of N" note in the panel. Table counts and medians always use all cells.
  - Size is about 0.5 MB per image, about 5 MB for 10 images.
- Geometry:
  - tiles;
  - hits {cell, x, y, rank, chunk, visit};
  - per-image route segments plus exit and entry stubs, built in Python from hits_df and the chunks. This replaces today's O(n²) indexOf matching in JS.
- thumb: an optional 128 px PNG data URL of projection8 (open decision 1).

Run level:
- version, title, screening flag;
- the criteria (metric, op, value, value2) and logic, sort_by, max_hits_per_rgn, optimize_path;
- config.METRICS descriptions and the QC rule texts;
- started / reapplied from pipeline.run_info(out);
- the chunks;
- a run-wide y range: auto_range over the band 10 and 90 % values, or display.min/max_lifetime when those are set;
- the file list.

Pipeline changes (built on the uncommitted pipeline.py, not on HEAD):
- run() keeps the hits DataFrame that write_screening_outputs returns and passes it on. Today it is thrown away.
- run() collects projection8 from the ViewerData it already loads for each image, for the thumbnails.
- run() writes run_summary.tsv and adds it to _RUN_OUTPUTS.

6) Build plan

Step 1: data contract (about 0.5 day). Comes first.
- overview.py: build_overview_data, QC_RULES, bands, capped columns, route segments, run_summary.tsv.
- The run() plumbing described above.
- Tests:
  - payload keys and band shape 5 × T;
  - hit count equals the rows in hits.tsv;
  - href is null when the dashboard is off;
  - the cap keeps all hits;
  - flags fire on synthetic results.

Step 2: shared front-end base (about 0.5 day). Can run alongside Step 1 once the field names are agreed.
- Move the global-free parts into templates/common.js:
  - from core.js: css, fmt, b64, colour helpers, the layer scheduler, wrapTitle, the tooltip;
  - all of plot.js;
  - download, uuid and rgnXml from export.js;
  - readStore/writeStore from persist.js.
- Move the :root tokens, light/dark rules and header/chip/panel styles into common.css.
- Add tokens --img-0 to --img-7 (8 muted hues, defined for light and dark, never the hit pink), --route-*, --warn and --bad.
- Parameterise shadeWindows(ctx, P, ev) and drawBand. The dashboard keeps its own calls through small wrappers.
- The existing dashboard tests and the JS compile test must still pass.

Step 3: page shell and table (about 1 day).
- templates/overview/page.html with a literal </head>, __FH_DATA__ and the logo/icon placeholders.
- _overview_template() following the pattern of _dashboard_template.
- Header, chips and ◐ toggle; the table with tooltips, multi-sort, multi-select and keyboard; the QC strip; persistence; the Run files menu; the "↑ Overview" link in the dashboards.
- Tests: JS compile test, rendered page has no __FH_ placeholders left, data parses.

Step 4: comparison panels (about 1 day). Panels B and C, hover linking, the axis lock, and the scatter adapted from scatter.js.

Step 5: maps, hits table and exports (about 1 day).
- Panel D in both modes, and Panel E.
- All exports, including the JS .rgn chunk compared with stage.write_rgn under py_mini_racer.
- PNG export.
- Remove the old templates/index.html.

Step 6: check on a real multi-image output (about 0.5 day). Light and dark theme; screening on and off; dashboards off; opened from file:// and through the GUI with a reapply.

Total is about 4 to 4.5 days of focused work.

On your question whether Ultracode would help: partly. Step 1, and agreeing its field names, has to come first. After that, Steps 2 and 3 can run in parallel with the Python tests, and Steps 4 and 5 touch separate panels and can also run in parallel. Run one after another in a single session, the steps are also manageable, so parallel work saves time without being essential.

7) Open decisions

1. Thumbnails in the table and tooltip, at 128 px. Recommendation: yes. They make samples easy to recognise. run() already loads ViewerData, and the cost is about 10 kB per image.
2. How far to go with QC flags. Recommendation: the 7 fixed rules listed in section 3, warnings only, every threshold stated in its tooltip. No GUI settings for now; add them later if the defaults prove wrong.
3. Default trace view. Recommendation: an overlay of medians with the 25-75 % band, aligned on stimulation in seconds, with a single click to small multiples. If your runs usually mix protocols, small multiples should be the default instead.
4. A drift column, which needs pipeline.py to keep the drift-correction shifts and store them in meta.json and load_result. Recommendation: leave it out of the first version. It touches processing code, and the baseline and calibration flags already catch most acquisition problems.

Files involved (none edited; all under C:\Users\b.vd.broek\surfdrive\FAST-HIPPOS\Python):
- src\fast_hippos\dashboard.py
- src\fast_hippos\pipeline.py
- src\fast_hippos\templates\index.html
- src\fast_hippos\templates\dashboard\ (core.js, plot.js, traces.js, export.js, persist.js, scatter.js, style.css, page.html, main.js)
- src\fast_hippos\templates\screening.js
- tests\test_pipeline.py
- tests\test_dashboard_js.py