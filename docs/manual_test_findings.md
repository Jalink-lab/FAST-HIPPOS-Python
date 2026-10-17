# Manual test run 2026-10-17: confirmed findings

Six agents followed the manual as new users (walk-through, ratio, intensity, edge cases, several images, command line + tiles),
two skeptics verified every report: 48 confirmed, 7 refuted. Sorted by severity.

## 1. Default quality gates are FLIM values in ns: with a ratio sensor every cell is invalid and there are 0 hits; the manual gives a ratio user no guidance

**major** · both · guide/choosing-hits.md (Quality gates), reference/settings.md (Gate: calibration − baseline, Gate: |baseline − population|), help/faq.md ('Many cells are not valid')

- **Expected:** A ratio user should get either defaults that suit a ratio, or a clear instruction in the manual. The manual should say that the gates are in the units of the measured value (ratio units here) and how to choose them for a ratio, for instance relative to the baseline ratio.
- **Actual:** In image 1 all 116 cells fail the calibration − baseline gate; image 2 has 1 valid cell of 114. That gives 0 hits, although the true calibration rise (about 1.15 ratio units) is a perfectly good calibration. choosing-hits.md describes the gates without any unit or default. settings.md gives [0.5, 1.0] and 0.2 without units. Only the FAQ mentions '(0.5–1 ns) suits the usual sensors; for another sensor, set it to the response you expect'. Nothing explains the 0.2 baseline-deviation gate for a ratio, whose meaning depends on the baseline ratio of the sensor.
- **Fix:** Manual: in choosing-hits.md (Quality gates) and the settings.md gate texts, say that the gates are in the unit of the measured value, that the defaults are meant for TCSPC lifetimes in ns, and that for ratio or intensity data you should set them from the gate histograms in the dashboard or switch them off. Program (optional): leave the gates off by default for ratio and intensity, or warn when almost no cells are valid (see the log finding).

## 2. Setting only one of the two frames switches off detection of the other

**major** · both · reference/settings.md (Stimulation frame / Calibration frame), guide/window.md

- **Expected:** settings.md says 'Stimulation frame: Empty = found automatically as the first clear jump' and 'Calibration frame: Empty = found automatically as the second jump'. With calibration 49, the stimulation at frame 15 should therefore still be detected.
- **Actual:** run2 log: 'Manual stimulation / calibration frames: None / 49'. events.json: stimulation null, detected false, baseline [0,48], response [0,0]. All response metrics are empty and there are 0 hits in 200 cells. There is no warning in the Run card or the log that no stimulation was found. run4 shows the reverse: 'Manual stimulation / calibration frames: 15 / None', calibration null, detected false. So 'empty' means 'none' as soon as the other field is set.
- **Fix:** Program (preferred): when only one frame is set, detect the other with detect() (e.g. take the detected transition that is not the given one). At least warn when the response window is empty. Otherwise, the manual and hover texts must say: 'Empty = found automatically, but only when both frames are empty; if the other frame is set, empty means none.'

## 3. Threshold + watershed misses every cell dimmer than about 1/3 of the brightest cells (about 23 % of the cells), and no setting can change that

**major** · both · guide/window.md (Cell segmentation), reference/settings.md (Segmentation)

- **Expected:** Round, well-separated cells with a brightness of 300-2000 counts per channel on a background of 10 (contrast of 30x or more) should all be found. If the automatic threshold cannot do that, there should be a setting to lower it, and the manual should explain how the threshold is chosen.
- **Actual:** 116 of 150 cells were found in image 1 and 114 of 150 in image 2. The missed cells are exactly the dim ones: brightness 306-600, while all cells span 306-1957. 3 of the 16 weak responders are among them and so could never be hits. With this method the window hides the cell diameter field and shows no threshold or gamma setting ('Gamma before segmentation' sits under Advanced: Cellpose and is not shown). The manual only says 'a classical segmentation, without Cellpose'.
- **Fix:** In segment(), apply the gamma (prepare_for_cellpose or the plain gamma) for method 'threshold' too. Show diameter and gamma for the threshold method in gui.py. In window.md and settings.md, add a sentence: 'Threshold + watershed uses an automatic (Otsu) threshold; dim cells can be missed: use a gamma such as 0.5'.

## 4. No way to say 'no calibration'; automatic detection takes the decay of a transient as the calibration

**major** · both · guide/window.md (Stimulation and calibration), guide/choosing-hits.md (Timing), reference/analysis.md section 4, help/faq.md

- **Expected:** Per the truth, stimulation at 15 (A) and 20 (B) and no calibration. The manual should say how to analyse movies that have a stimulation but no calibration. It only describes 'Baseline only', for movies without any stimulation.
- **Actual:** The log says 'Detected stimulation at frame 15 and calibration at frame 17' (B: 20 and 22). In events.json the response is [15,16], so the response is only 2 frames long and frames 17-49 count as 'calibration'. All rise_time_frames are 1 and response_fraction is 1. Nothing tells the user the calibration is suspicious. In the window, the calibration field rejects 50 ('calcium_A.tif has 50 frames (0-49), but the calibration frame is set to 50'). Empty means 'automatic'. The only accepted workaround is 49, which throws away a frame. The dashboard does accept an empty C ('cal – (set)') and then computes correctly.
- **Fix:** Manual (window.md Stimulation and calibration, choosing-hits.md Timing): 'Without a calibration: set the stimulation frame and leave the calibration empty (it is then none), per image if needed.' Program: add a 'No calibration' tick box in the events settings, used by detect() to look for one transition only. Optionally, warn when the detected calibration is less than a few frames after the stimulation.

## 5. Default quality gates are in ns, so they make every intensity cell invalid, without explanation

**major** · both · guide/choosing-hits.md (Quality gates), help/faq.md ('Many cells are not valid'), reference/settings.md

- **Expected:** Either intensity-appropriate gate defaults, or a warning when the gates are lifetime-based or there is no calibration. Gate inputs and hover texts should not say 'ns' for intensity data.
- **Actual:** 0 valid cells, 0 hits in 200 cells. The only message is 'Screening: 0 hits in 100 cells'; nothing says it is the gates. The dashboard shows 'calibration − baseline 97 fail –  ns' and '|baseline − population| ≤ 99 fail ns'. The hover texts say 'Lowest allowed calibration response (ns)' and 'Largest allowed difference from the population baseline (ns)'. For data without a calibration, the calibration gate cannot be meaningful at all. The FAQ only mentions the 0.5-1 ns range 'for the usual sensors'.
- **Fix:** Use the gates' lifetime defaults only for lifetime modalities, and off (None) for intensity and ratio (in config or in the GUI when the image type changes). Use D.is_lifetime ? 'ns' : D.unit in the dashboard gate labels. Log 'N of M cells pass the quality gates' per image. Add a note to choosing-hits.md/faq.md that the default gates are for lifetimes.

## 6. Settings applied from a dashboard are lost once the FAST-HIPPOS window is reloaded or reopened; Re-apply screening then silently goes back to the old screening

**major** · program · guide/choosing-hits.md (Apply the settings), guide/window.md (Settings files: 'FAST-HIPPOS remembers the last settings')

- **Expected:** choosing-hits.md says that after applying 'the FAST-HIPPOS window shows the new settings, so that a later Re-apply screening or Run analysis uses them too', and window.md says FAST-HIPPOS remembers the last settings. A reopened window should therefore start with the applied settings: gate [0.5, 2.5], criterion 0.12.
- **Actual:** After the reload the window has gate [0.5, 1] and criterion 0.15 again (the settings of the last Run). Re-apply screening uses them, and every hit disappears without any warning. Log: 'Screening: 0 hits in 116 cells (0.0 %)' and run_summary.tsv shows valid 0 / 1. The same happens before any run: settings changed in the window (images, image type, segmentation method) are back to the defaults after a page reload, so the remembered settings are only updated by Run or Re-apply.
- **Fix:** In apply_from_dashboard, after reapply_settings, also write the applied [events]/[screening]/[display] into LAST_SETTINGS when it belongs to the same output folder (extend _remember_image_settings to merge the whole applied settings, not only 'image').

## 7. A stage positions file with too few positions, or a header line, passes the checks, then the run fails after the images with a raw traceback

**major** · program · guide/microscope.md (Where the stage positions come from), guide/window.md (Checks)

- **Expected:** A red check before the run, e.g. 'Stage positions file has 2 positions for 3 images' or 'line 1 is not a number', as for a missing file (that one does give a red check: 'Stage positions file not found: …').
- **Actual:** The checks say '✓ Ready to run'. The short file fails only after all images have been segmented and measured: 'ValueError: Stage positions file has 2 positions; image 2 has none' (0-based index, so it means the 3rd image), shown as a Python traceback in the log. The header file fails at once with 'ValueError: could not convert string to float: 'x''. In a real screen the first failure comes after hours of segmentation.
- **Fix:** In checks.py, when screening is enabled and a text positions file is given: try read_positions_file and report 'Stage positions file: line X is not a number' or 'has N positions for M images' as a problem (red). In read_positions_file, skip non-numeric header lines and give a plain error naming the image (1-based).

## 8. Timing set with 'Apply to all images' is not kept by the window: after reopening or reloading the window, Re-apply / Run analysis quietly go back to the old timing

**major** · program · choosing-hits.md (Apply the settings: 'the FAST-HIPPOS window shows the new settings, so that a later Re-apply screening or Run analysis uses them too')

- **Expected:** The window keeps the applied global timing (stimulation 9, calibration 30; response window 6 after S). A later Re-apply or Run uses it, or at least warns that the window's timing differs from the run.
- **Actual:** Only the window tab that was open during the Apply has the new values in memory (S.events = [8,30]). A freshly loaded window shows the old settings (stimulation and calibration empty, response window -1). last_settings.toml in WS\home\.fast_hippos still holds stimulation_frame = "" after the Apply, while the own settings ([image."imgB"]) are saved there. Re-apply then quietly reverted out\settings_used.json from stimulation 9, calibration 30, response window [6, after_stimulation] to None/None, [-1, before_calibration]. The Run card gave no warning about the timing; it warned only about the own settings.
- **Fix:** After an Apply from a dashboard, merge the applied [events]/[screening]/[display] into last_settings.toml (when it belongs to that output folder), as is already done for [image].

## 9. Cell diameter hidden for Threshold + watershed; the manual does not say what the threshold method uses

**minor** · both · guide/window.md (Cell segmentation), reference/settings.md (segmentation.diameter)

- **Expected:** Either a cell diameter or size setting for the watershed, or a manual statement that the threshold method needs none.
- **Actual:** The card only shows 'Minimum cell size (px)'; Cell diameter disappears. The manual describes Threshold + watershed in one line, 'a classical segmentation, without Cellpose', with no parameters. It worked well on my data (100 of 100 cells).
- **Fix:** Show segmentation.diameter for the threshold method as well, with a hover text such as 'Typical cell diameter (px); used for smoothing and for splitting touching cells; 0 = 20 px'. In window.md, add one line: 'Threshold + watershed uses the Cell diameter and Minimum cell size.'

## 10. microscope.md and settings.md disagree on what a positions text file does, and on the route gain

**minor** · both · guide/microscope.md, reference/settings.md

- **Expected:** Consistent statements.
- **Actual:** microscope.md says a text file 'replaces the positions in the images' and the .lif is 'used only for images without positions of their own'. settings.md says 'Only for images without stage positions of their own' for both. The route gain is 'typically 15–20 % shorter' in microscope.md and '13–18 % shorter' in settings.md.
- **Fix:** Change the hover text in gui.py (and so settings.md) to: 'A text file with X Y in metres per image (replaces the positions in the images), or the .lif file of the experiment (used only for images without positions of their own).' Use one route figure on all pages and in the hover.

## 11. CLI 'run' and 'reapply' do not write or update fast_hippos_settings.toml in the output folder

**minor** · both · reference/command-line.md, guide/output-folder.md, guide/own-settings.md

- **Expected:** command-line.md: 'Every run saves its settings as fast_hippos_settings.toml in the output folder'. output-folder.md lists the file as 'the settings of the run, to open in the window or use on the command line'.
- **Actual:** A CLI run writes no fast_hippos_settings.toml at all. W/p1/results only has settings_used.json, run.json and the rest. After a CLI reapply, the file written earlier by the GUI is not updated: it still says value = 2 (time 14:44:18), while settings_used.json has 3.355 (14:50:03). A GUI Re-apply does update it (value 3.36, 14:50:48). So someone who later opens the file with Open settings..., or reruns from it, gets settings that do not match the hits and .rgn files.
- **Fix:** Write fast_hippos_settings.toml from pipeline.run (both run and reapply, after clear_run) rather than only in the GUI, so the CLI and the GUI behave the same.

## 12. tile_positions.tsv is written into the input tile folder even when the MetaData folder is present

**minor** · both · guide/microscope.md (Tile scans)

- **Expected:** microscope.md mentions tile_positions.tsv being saved next to the tiles only when the MetaData folder is missing and a .lif is chosen as Stage positions file. The stitched image with its positions goes into the output folder.
- **Actual:** Every run or stitch writes tile_positions.tsv into the INPUT tile folder, also when MetaData is there. GUI log: 'Tile positions written to ...\tiles_data\tiles\tile_positions.tsv'. Stitch: 'Tile positions written to st\tiles3\tile_positions.tsv'. This changes the raw data folder, and it can fail on a read-only or shared data drive. The copied original also already held one from earlier runs.
- **Fix:** Simplest: in microscope.md, say that FAST-HIPPOS saves the tile positions it reads (from MetaData or the .lif) as tile_positions.tsv next to the tiles, and that you delete it to read them again. Alternatively, save the sidecar only when the positions came from a .lif.

## 13. mean_intensity is a sum over all frames, not a mean intensity, and is undocumented; 'Minimum cell intensity' has no usable scale

**minor** · both · reference/metrics.md (mean_intensity is missing), reference/settings.md (Minimum cell intensity)

- **Expected:** A mean pixel intensity per cell in camera counts (here about 1876 in C2 and 2560 in C1 for cell 1), and an entry in metrics.md, because it appears in the dashboard table, scatter plot, kymograph sorting and overview.
- **Actual:** Cell 1 has mean_intensity 152317, which is above the uint16 maximum. It matches the sum of C1+C2 over the 40 frames (the intensity_projection.tif maximum is 185199). metrics.md does not list mean_intensity (or area_px or circularity). A user who sets 'Minimum cell intensity' from the camera values would filter almost nothing.
- **Fix:** Divide the projection by the number of projected frames before cell_statistics and filter_labels (so it is a per-frame mean in camera counts), and add mean_intensity, area_px and circularity to metrics.md. Or keep the values and document them as 'mean of the sum projection over the frames' in metrics.md and in the Minimum cell intensity text.

## 14. A movie without stimulation is made 'baseline only' automatically: no QC flag, a grey dot, events_detected=True, and the documented Baseline-only step has nothing to do

**minor** · both · guide/overview.md (QC), guide/window.md (Stimulation and calibration), guide/choosing-hits.md, guide/own-settings.md

- **Expected:** overview.md: flag 'no stimulation / calibration: none found, while most images have one' (2 of 3 images have one); the QC dot is green, orange or red. window.md says to tick Baseline only for movies without stimulation, which suggests the user must do it, per image via Apply to this image only.
- **Actual:** The log says 'WARNING No stimulation or calibration detected; treating the whole trace as baseline'. flat_3 gets no 'no stimulation' flag, only 'no hits', with a grey dot (class qcdot info), a colour the manual does not mention. run_summary.tsv says events_detected=True and baseline_only=True for flat_3, although nothing was detected. The dashboard already has 'baseline only' ticked, and Apply to this image only says: 'Nothing to apply to this image only: change its stimulation frames (Timing) or its response window first.' A movie whose stimulation was simply missed is silently treated the same way.
- **Fix:** overview._flags: also add 'no_stimulation' when ev['baseline_only'] and ev['detected'] (automatic fallback) and most images have a stimulation. overview.md: mention the grey dot for 'no hits'. window.md: add 'when no stimulation is found, the image is analysed as baseline only (log warning)'.

## 15. A per-image settings table for an image name that is not in the run is ignored without any warning

**minor** · both · reference/command-line.md

- **Expected:** A warning such as 'own settings for unknown image plateb', since the table has no effect. The manual does not say what the image name of a .tif or a tile folder is either: for the tile folder 'tiles' it is 'testforbram_STITCHED'.
- **Actual:** Nothing is logged. plateB uses automatic detection ('Detected stimulation at frame 12'). Because the file has an [image] part, the run's own settings of plateB are also silently dropped. A wrong key inside the table, by contrast, is rejected.
- **Fix:** In pipeline.run (or checks.py): warn 'Own settings for image "plateb" match no image of the run (images: …)' for every settings.image key that is not an image name. In command-line.md: 'the image name as shown in the overview and dashboard: the file name without extension, <prefix>_STITCHED for a tile folder'.

## 16. The walk-through calls every cell below 0.6 ns a hit, but quality gates remove half of them

**minor** · manual · start/first-analysis.md (step 5 and step 7)

- **Expected:** From 'Cells that rise less than 0.6 ns become hits' a new user expects that every cell with response_mean_diff < 0.6 is a hit.
- **Actual:** The criterion row says '28 pass', but there are only 13 hits. The quality gates, on by default and never mentioned in the walk-through, remove 15 of them (e.g. cell 44: response_mean_diff 0.231 but 'fails gates'). A new user sees 28 vs 13 with no explanation on this page.
- **Fix:** In step 2 of 'Screen for hits' (or at step 7), add: '…become hits, provided they also pass the quality gates, which are on by default (see Choosing the hits).'

## 17. rise_time_frames is one more than 'frames after the stimulation'

**minor** · manual · reference/metrics.md (rise_time_frames)

- **Expected:** metrics.md: 'Frames after the stimulation until the cell reaches the rise fraction'. Fast cells reach 100 % at frame S, so 0. Slow cells first exceed 75 % at S+7, so 7.
- **Actual:** Fast cells: rise_time_frames = 1.0 (all 120). Slow cells: 8.0 (all 40). The count apparently includes the stimulation frame.
- **Fix:** metrics.md and the config.py/gui.py hover texts: 'Number of response-window frames up to and including the first frame in which the cell reaches the rise fraction (1 = already in the first frame after the stimulation).'

## 18. The stage-position axis convention is not documented: file X,Y become .rgn/abs X=-Y, Y=-X

**minor** · manual · guide/microscope.md (Where the stage positions come from); reference/metrics.md

- **Expected:** The manual says the file holds 'the X and Y stage position (in metres) of every image'. A user checking the .rgn or hits.tsv expects to find these X and Y back.
- **Actual:** stim_1 (file X=0.001, Y=0.002) gets abs_x_m ≈ -0.00202 and abs_y_m ≈ -0.00104; stim_2 (0.003, 0.004) gets -0.00404/-0.00304. The .rgn <X>/<Y> are the same values. Afterwards I read the code: src/fast_hippos/stage.py documents this as intended (abs_x = -stage_Y …, validated on the Stellaris). The manual does not explain it anywhere, and abs_x_m/abs_y_m are not documented at all (grep finds nothing in the manual).
- **Fix:** microscope.md: say that the positions file holds the stage X/Y as stored in the .lif/OME-XML metadata (the same as Bio-Formats shows), and that the .rgn files and abs_x_m/abs_y_m are in the LAS X Navigator frame (X = −stage Y, Y = −stage X, measured to the cell). Add abs_x_m/abs_y_m to metrics.md or output-folder.md.

## 19. The detection threshold is listed as a per-image setting, but neither the manual nor the dashboard gives a way to set it per image

**minor** · manual · own-settings.md (table 'What can differ per image': 'detection threshold')

- **Expected:** A detection threshold (events.sensitivity) control that 'Apply to this image only' can make the image's own, or a description in the manual of another way to set it.
- **Actual:** Timing has only stim, cal, margin, baseline only, response window, smoothing and rise. The inputs are #evs, #evc, #evm, #evb, #rw, #rm, #sm and #rf; there is no sensitivity input. The 'Apply to this image only' confirmation lists only stimulation, calibration, baseline only, margin and the response window. The section 'Give an image its own settings' describes the dashboard only.
- **Fix:** In own-settings.md, mark the detection threshold as 'settings file only' and link to the [image."name"] section of command-line.md, or add a sensitivity input to the dashboard Timing section.

## 20. First run needs internet and takes about 2 minutes, not 'about a minute'

**minor** · manual · start/first-analysis.md (step 6), start/install.md

- **Expected:** The manual says 'With a GPU this takes about a minute for the three images' and never mentions a download.
- **Actual:** The first run took 125 s: Cellpose downloads the cyto3 model (about 40 s for image 1). The second run took 66 s. Neither install.md nor first-analysis.md says that the first Cellpose run downloads the model and needs internet.
- **Fix:** In first-analysis.md step 6 (or install.md section 4), add: 'The first time, Cellpose downloads its model (internet needed), so the first run takes a minute longer.'

## 21. .rgn file names use the image name, not the output folder name, when a run has one image

**minor** · manual · guide/microscope.md, guide/output-folder.md

- **Expected:** microscope.md: 'HITS_<run>.rgn ... <run> is the name of the output folder', so HITS_tile_out.rgn and HITS_out.rgn.
- **Actual:** The single-image runs write HITS_testforbram_STITCHED.rgn and HITS_testforbram_STITCHED_1-1000.rgn (the image name). Only the 2-image run uses the folder name: HITS_multi_run.rgn and HITS_multi_run_1-2.rgn.
- **Fix:** microscope.md: '<run> is the name of the output folder, or the name of the image when the run has only one image.'

## 22. UnicodeDecodeError traceback in the Run log on the first Cellpose run (model download)

**minor** · program · start/first-analysis.md (step 6), start/install.md (4. Cellpose)

- **Expected:** A clean log for a new user's very first run.
- **Actual:** Right after 'Running Cellpose 3 via …' the log shows a Python traceback: 'Exception in thread Thread-2 (_readerthread): … File "…\encodings\cp1252.py" … UnicodeDecodeError: 'charmap' codec can't decode byte 0x8f in position 156'. The run then continues and the results are correct. The second run, with the model already cached, has no traceback. Cellpose downloaded cyto3 into <ws>\home\.cellpose\models during that first run.
- **Fix:** Pass encoding='utf-8', errors='replace' to both subprocess.run calls (segmentation.py:107 and gui.py:691).

## 23. False warning 'The Images list differs from the images of that run' when only the path spelling differs

**minor** · program · guide/window.md (Run card checks)

- **Expected:** No warning: these are the same three files.
- **Actual:** The Run card warns: '! The Images list differs from the images of that run: Re-apply screening processes the run's images, not the list'.
- **Fix:** Compare the paths on the server: os.path.normcase(Path(p).resolve()) for the list and for run.json inputs (the _key() helper in gui.py already does this), and pass the result to the page. Alternatively, make _resolve use os.path.abspath instead of resolve().

## 24. Dashboard quality gates show 'ns' for ratio data

**minor** · program · guide/dashboard.md, guide/choosing-hits.md (reference/metrics.md says 'Lifetime' stands for the ratio)

- **Expected:** Ratio units, or no unit. Everywhere else the dashboard correctly says 'Ratio (ch1 / ch2)': colour bar, trace y-axis, distribution x-axis, top-bar range.
- **Actual:** The gate inputs are followed by 'ns'. Their hover texts are 'Lowest allowed calibration response (ns)', 'Highest allowed calibration response (ns)' and 'Largest allowed difference from the population baseline (ns)'. The criterion hover says 'in the unit of the metric (e.g. ns)'.
- **Fix:** Fill the unit span and the titles from D.is_lifetime ? 'ns' : D.unit (or leave the unit out for ratio data), as main.js does for the other labels.

## 25. The log does not say that the quality gates removed (almost) all cells

**minor** · program · guide/window.md (Run card log)

- **Expected:** When there are 0 hits because 0 cells are valid, the log or the Run card should say so (for example '0 valid of 116 cells: check the quality gates').
- **Actual:** The log only says 'Screening: 0 hits in 116 cells (0.0 %)' and 'Screening total: 0 hits in 230 cells'. Nothing in the window points to the gates. The cause only shows in the overview QC (low valid fraction) or in the dashboard ('0 valid').
- **Fix:** Log 'Screening: N hits in M cells (V valid)', and log a warning when V/M is very low (e.g. < 20 %): 'few cells pass the quality gates; check the gate ranges'.

## 26. 'No hit criteria: every valid cell becomes a hit', but no cell becomes a hit

**minor** · program · guide/window.md (Run card checks; Screening), reference/settings.md (Hit criteria)

- **Expected:** The Run card warning says 'No hit criteria: every valid cell becomes a hit' (the window hint says 'no criteria: all valid cells are listed'), so 100 valid cells should give 100 hits.
- **Actual:** cells.tsv has 100 valid and 0 hits; the log says 'Screening: 0 hits in 100 cells (0.0 %)'. The dashboard shows '100 cells 100 valid 0 hits'.
- **Fix:** Choose one behaviour and make the messages match it. Simplest: change both texts to 'No hit criteria: no cell becomes a hit (add criteria here or in the dashboard)'. If 'all valid cells' is wanted, set hit = valid in screening.py and screening.js.

## 27. The settings file of the previous run is overwritten, not moved into _previous_run

**minor** · program · guide/output-folder.md (Running again)

- **Expected:** output-folder.md says the files of the run are moved into _previous_run, so that nothing is lost when the run is stopped. fast_hippos_settings.toml is one of the run's files, so the old one should be in _previous_run and moving it back should restore the run completely.
- **Actual:** _previous_run holds everything except fast_hippos_settings.toml. The top-level toml was overwritten by the stopped run's settings (big_*.tif, other criteria). The confirmation also leaves fast_hippos_settings.toml out of 'Files of that run'. After 'move them back', the folder has the old results with the new run's settings file.
- **Fix:** In Job.start, move an existing fast_hippos_settings.toml into _previous_run, or write the new toml under a temporary name and rename it after clear_run. Also add the file to _RUN_OUTPUTS so that it is listed in 'Files of that run'.

## 28. A failed or stopped first run into an empty folder creates an empty _previous_run and claims the previous results are kept there

**minor** · program · guide/output-folder.md

- **Expected:** There was no previous run, so no _previous_run and no message about one.
- **Actual:** The log says 'ERROR The run did not finish. The results of the previous run are kept in ...\out_header\_previous_run; move them back to use them again.' and an empty _previous_run folder is created (out_short\_previous_run too).
- **Fix:** Only create _previous_run when plan['folders'] + plan['files'] is not empty. Otherwise, remove an empty one before printing the message, and print it only when the folder is not empty.

## 29. Settings -> TOML of a dashboard also writes the calibration frame when only S was changed, so it fixes C for all images

**minor** · program · reference/command-line.md (reapply --override), guide/choosing-hits.md

- **Expected:** Only the changed stimulation frame is carried over, and plateA keeps its automatically detected calibration (45, which is also the truth).
- **Actual:** The file has [events] stimulation_frame = 14 and calibration_frame = 40. After the reapply, plateA logs 'Manual stimulation / calibration frames: 14 / 40', so its calibration window starts 5 frames too early. The untouched C value of plateB was turned into a fixed frame for every image.
- **Fix:** Fix it together with the events.py finding: let an empty calibration_frame be detected while S is set, and have the export write calibration_frame = "" (automatic) when C was auto-detected and not touched. Until then, the Apply/TOML confirmation should say that both S and C are fixed for all images.

## 30. The Run card and the log give contradictory messages about .rgn files for images without stage positions

**minor** · program · guide/window.md (Run card: 'images without stage positions get no .rgn files')

- **Expected:** One consistent message. window.md says these images get no .rgn files, and the log agrees.
- **Actual:** The Run card warns: 'Not every image has stage positions: hits are found, but their .rgn positions are not real (Screening, advanced: Stage positions file)'. That suggests the .rgn files hold fake positions. The log says 'WARNING No stage position for ratio_img1: its 7 hits are not in the .rgn files', and no .rgn file is written. During the run itself the log also says 'No stage position for ratio_img1: using (0, 0)'.
- **Fix:** gui.html line 456: 'Not every image has stage positions: their hits are found but left out of the .rgn files (Screening, advanced: Stage positions file)'. Optionally reword pipeline.py line 491 to 'No stage position for %s: its hits will not go into the .rgn files'.

## 31. Dialogs and log call the calibration 'automatic' when it is actually 'none'

**minor** · program · guide/choosing-hits.md (Apply the settings), guide/own-settings.md

- **Expected:** The confirmation text says the calibration is none or absent, which is what is applied.
- **Actual:** Dialog: 'The timing set here (stimulation frame 15, calibration frame automatic) is used for all images'. The image-only dialog lists '• calibration frame automatic'. The log then says 'Own settings of this image: ... calibration_frame automatic' and on the next line 'Manual stimulation / calibration frames: 20 / None'. events.json has calibration null and response [20,50]. The saved TOML has calibration_frame = "", which in the window means 'automatic'.
- **Fix:** In export.js (line 105 and describeOwn) and pipeline._describe_own: when one of stimulation_frame/calibration_frame is set and the other is null, write 'none' for the unset one. Write 'automatic' only when both are unset.

## 32. A complete run silently deletes the kept _previous_run (the only copy of the last good run) after a stopped run

**minor** · program · guide/output-folder.md (Running again), help/faq.md

- **Expected:** Before step 4 the window warns that the output folder holds a _previous_run with an earlier complete run, and the confirmation says it will be deleted. Better still, a kept _previous_run is never deleted by a later run without an explicit choice.
- **Actual:** The Run card shows '✓ Ready to run' with no warning. The confirmation only says the folder 'holds the results of an earlier run' and lists 'Files of that run: run.json, run_log.txt, settings_used.json'; it never mentions _previous_run. When the run completes, out_stop\_previous_run, with the complete 14:53 run (its .rgn files, hits.tsv and image folders), is deleted. The FAQ says 'If a run did not finish, the previous results are still in _previous_run', but they are lost at the next complete run.
- **Fix:** In gui.html start(): when o.previous_run is true (pipeline.py run_info already returns it) and the run in the folder is incomplete, say 'The folder holds an unfinished run (its files are deleted) and, in _previous_run, the complete run of <date>, which is deleted when the new run is complete. Move it back first to keep it.' Optionally show an orange check for it.

## 33. The window's warning about missing stage positions says the .rgn positions are 'not real', but no .rgn files are written

**minor** · program · guide/window.md (Checks), guide/microscope.md, help/faq.md

- **Expected:** Per window.md ('images without stage positions get no .rgn files'), microscope.md ('their hits get no .rgn file') and the FAQ ('No .rgn files were written'), the warning should say these hits get no .rgn file.
- **Actual:** The warning reads 'Not every image has stage positions: hits are found, but their .rgn positions are not real (Screening, advanced: Stage positions file)', which suggests .rgn files with fake positions. In fact no .rgn files are written, which matches the manual. The log says 'No stage position for stim_1: using (0, 0)' and 'its 15 hits are not in the .rgn files'.
- **Fix:** Reword gui.html line 456: 'Not every image has stage positions: their hits are left out of the .rgn files (Screening, advanced: Stage positions file)'.

## 34. Re-apply after setting a Stage positions file gives no hint that a new run is needed

**minor** · program · guide/output-folder.md (Running again), guide/microscope.md

- **Expected:** output-folder.md says the stage positions file only changes with a new run. The window should then warn that the stage positions file differs from the run in the folder (as it does when the image list differs), or Re-apply should say it ignores it.
- **Actual:** The orange warning disappears and the card shows '✓ Ready to run', which suggests the problem is solved. The confirmation mentions only generically '…and the stage positions file, which only change with a new run'. After the re-apply there are still no .rgn files, and the log still says 'No stage position for stim_1: its 15 hits are not in the .rgn files', without pointing to Run analysis.
- **Fix:** In gui.html checks: when the output folder holds a run whose stage_positions_file differs from the window's, add the orange check 'The stage positions file differs from the run in the output folder: only Run analysis uses it'.

## 35. Bidirectional correction of tiles gives a float32 stitched image with negative values (twice the size)

**minor** · program · guide/microscope.md (Tile scans), reference/command-line.md (stitch)

- **Expected:** The stitched image keeps the uint16 photon counts or amplitudes of the tiles (or at least non-negative values), so the file has about the same size.
- **Actual:** bidir.tif is float32 with min -10.005 and max 269.68 (94,374,802 bytes). Without correction it is uint16, 0..278 (47,188,678 bytes). Negative TCSPC amplitudes can disturb the amplitude-weighted lifetime of dim pixels. A user who turns on 'Correct bidirectional scanning phase' for a tile folder also gets a stitched file in the output folder that is twice as large.
- **Fix:** In stitch_tiles, after apply_bidirectional, clip at 0 and cast back to the tiles' original integer dtype (np.rint, then astype) when the input was an integer type. Optionally do the same in preprocess.correct_bidirectional.

## 36. Stand-alone stitch overwrites an existing <prefix>_STITCHED.tif without warning

**cosmetic** · both · reference/command-line.md

- **Expected:** A warning or a refusal, since the second command replaces the first result. The manual also does not say where stitch writes its output (--help: next to the folder).
- **Actual:** Both commands print 'Wrote st\testforbram_STITCHED.tif'. The second silently replaces the first.
- **Fix:** In command-line.md, say: 'writes <prefix>_STITCHED.tif next to the tile folder (or --output)'. Optionally, refuse or warn when the file exists, as init-config does.

## 37. Hover highlight is orange, not yellow; the hover tooltip shows max Δ instead of the criterion metric

**cosmetic** · manual · guide/dashboard.md (Everything is linked), start/first-analysis.md (Things to try)

- **Expected:** dashboard.md: 'the cell is highlighted in yellow everywhere'. With the walk-through criterion response_mean_diff < 0.6, the tooltip would show that value.
- **Actual:** The highlight in the image, traces and scatter is orange. The tooltip reads 'Cell 246 · 2.224 ns · hit / max Δ 0.603 · baseline 2.227'. That max Δ (response_max_diff) is above 0.6, which can confuse a user who just made a hit criterion of < 0.6; response_mean_diff (0.491) only appears in the Cell card.
- **Fix:** dashboard.md: 'highlighted in yellow (orange in the light theme) everywhere'. Showing the criterion metrics in the tooltip is an optional improvement.

## 38. The output-folder page lacks a few files and does not say how to restore from _previous_run

**cosmetic** · manual · guide/output-folder.md, help/faq.md

- **Expected:** Every file of the run explained, and the restore step described (the program says 'move them back to use them again').
- **Actual:** hit_positions.png, run.json and hit_chunks.json are not in the tree. Neither page says that you restore a stopped run by moving the contents of _previous_run back up (and deleting the partial files of the stopped run first).
- **Fix:** Add the three files to the tree (e.g. hit_positions.png: map of the hits and routes; run.json, hit_chunks.json: bookkeeping). Add a sentence: 'To go back to the previous run, delete the partial results of the stopped run and move the contents of _previous_run back into the output folder.'

## 39. Manual contradicts itself on whether the bidirectional phase correction is once for all tiles or per tile

**cosmetic** · manual · guide/microscope.md vs reference/settings.md (and stitch --help)

- **Expected:** One consistent description.
- **Actual:** microscope.md says the phase is corrected '(once for all tiles)'. settings.md says 'For tile folders and .lif tile scans it is done per tile'. stitch --help says 'bidirectional phase correction per tile along this axis'. The program logs a single value, 'Bidirectional phase correction per tile (along y): 0.90 px', and the TIFF Info has 'Bidirectional correction per tile (px): 0.9'. That reads as one shift measured once and applied to each tile, which matches microscope.md, but the other two texts suggest a separate measurement per tile.
- **Fix:** Use one wording everywhere (microscope.md, the hover/settings.md, stitch --help and the log): 'one shift, measured once over all tiles and applied to each tile before stitching'.

## 40. Route improvement figure differs between pages (15–20 % vs 13–18 %)

**cosmetic** · manual · guide/microscope.md vs reference/settings.md

- **Expected:** The same number on both pages.
- **Actual:** microscope.md says 'typically 15–20 % shorter'. settings.md (the hover text) says 'typically 13–18 % shorter than always going to the nearest next hit'.
- **Fix:** Use one figure in gui.py's hover text (and so settings.md), microscope.md and analysis.md.

## 41. The dashboard screenshot and the GUI screenshot do not match what the numbered steps produce

**cosmetic** · manual · start/first-analysis.md (step 7 figure dashboard_views.png, step 1 figure gui.png)

- **Expected:** The same view as dashboard_views.png, whose lifetime range is 2.00–3.60.
- **Actual:** The lifetime range is 2.10–3.40 (automatic). The 2.0–3.6 in the screenshot comes from [display] min_lifetime/max_lifetime in example_settings.toml, which the steps never mention. gui.png also shows '5 hidden advanced settings changed from the defaults'; after loading example_settings.toml I get '4 hidden advanced settings changed'.
- **Fix:** Remove [display] from example_settings.toml and retake the screenshots. Or add one sentence to step 7: 'the screenshot uses a colour range of 2.0–3.6 ns (Display card), as in example_settings.toml'.

## 42. Non-responders get arbitrary rise times, so 'OR rise time > N' also selects them

**cosmetic** · manual · guide/choosing-hits.md (Hit criteria, AND/OR example), reference/metrics.md

- **Expected:** The manual's example 'OR rise time > 5' for slow cells suggests rise time on its own identifies slow responders.
- **Actual:** Non-responders have rise_time_frames between 1 and 25 (median 7-9), because they take 75 % of their noise maximum. A criterion 'rise_time_frames > 4' on its own selects most non-responders. I needed an AND criterion response_max_diff > 300 to exclude them; with it, the hits matched the truth exactly.
- **Fix:** Add to metrics.md (rise_time_frames): 'Only meaningful for cells that respond; for non-responders it follows the noise. Combine it with an AND criterion on the response (e.g. response_max_diff) to select slow responders only.'

## 43. Header still says 'last used settings' after Defaults

**cosmetic** · program · guide/window.md (Settings files)

- **Expected:** The header shows that default settings are now active, as it does at first start ('default settings').
- **Actual:** The header keeps saying '· last used settings'. The toast says that the defaults were restored. Open settings does update the header ('settings from <path>').
- **Fix:** In the bReset handler, add $("from").textContent = "default settings".

## 44. Internal key names appear in user-facing texts ('after_stimulation', 'window anchor after_stimulation')

**cosmetic** · program · own-settings.md

- **Expected:** The same wording as the controls: 'after S' or 'after stimulation'.
- **Actual:** The confirmation reads '• response window anchor after_stimulation'. The window list and the Run/Re-apply confirmations read 'response window 5, window anchor after_stimulation'. The log line reads 'response_window 5, response_window_anchor after_stimulation', and the imgC line 'baseline_only False'.
- **Fix:** Add a value map (after_stimulation → 'after S', before_calibration → 'before C') to ownValue/describeOwn in export.js and in gui.html:667, and use labels in _describe_own as well.

## 45. Cellpose message points to 'Advanced → Segmentation', but the card is 'Cell segmentation' and the field is under 'Cellpose environments'

**cosmetic** · program · start/install.md (4. Cellpose)

- **Expected:** The same names as install.md: 'Cell segmentation → Advanced settings → Cellpose 3 environment (python.exe)'.
- **Actual:** The label says 'Cellpose 3 not found in this environment: set its python.exe under Advanced → Segmentation'. The Run card says 'Cellpose 3 is not available (Advanced → Segmentation)'. No card or heading is called 'Segmentation': the field is in the Cell segmentation card under the subheading CELLPOSE ENVIRONMENTS. install.md's 'No Cellpose' tab also says 'Segmentation → Threshold + watershed'.
- **Fix:** In gui.html lines 257 and 451, use 'Cell segmentation → Advanced settings → Cellpose environments'. install.md needs no change.

## 46. 'mean_intensity' holds the sum over frames, not a mean

**cosmetic** · program · guide/dashboard.md (Cells table), reference/metrics.md (not listed)

- **Expected:** About 1000-1200 (the cells' mean intensity per frame) for my cells.
- **Actual:** mean_intensity = 60210.8 for a cell with baseline 1112 over 50 frames, which is the sum of the frames. It is also offered as a scatter and kymograph axis and is not documented in metrics.md.
- **Fix:** See the ratio mean_intensity finding: divide the projection by the number of frames (or rename the column) and document it in metrics.md.

## 47. Run card warning after ✕ names images whose own settings did not change

**cosmetic** · program · own-settings.md (Remove them)

- **Expected:** A warning about imgC only, e.g. 'imgC's own settings will be removed at the next Re-apply'.
- **Actual:** 'The run in the output folder has other own settings of single images (imgB, imgC) than this window'. This reads as if imgB also differs. The Re-apply confirmation itself was clear: imgB keeps its own settings, and they are removed for imgC.
- **Fix:** In gui.html line 443, list only the names whose own settings differ between o.run.image_settings and S.image (or those removed with ✕).

## 48. Config errors on the command line come out as a full Python traceback

**cosmetic** · program · reference/command-line.md

- **Expected:** A short message such as 'settings.toml line 2: unescaped \ in a string (use / or \\)', 'Unknown setting diamter in [segmentation]' or 'No tile positions ...'.
- **Actual:** A 20- to 40-line traceback through tomllib, config.py or stitch.py, with the useful message only on the last line, e.g. 'ValueError: Unknown setting(s) in [SegmentationSettings]: diamter' (the class name, not the TOML section). The GUI Images card also shows the raw 'ValueError: No tile positions for ...'. That text says 'no .lif file given' but does not point to the Stage positions file setting, which is where the manual says to give it.
- **Fix:** In cli.main, wrap from_toml and stitch_folder in try/except (ValueError, tomllib.TOMLDecodeError) and print 'Error: <message>' to stderr (exit code 2). In config.py, report the TOML section name instead of cls.__name__. In stitch.py line 277, add '(give one with --lif, or as Stage positions file under Screening → Advanced settings)'.

## Refuted

- No relative (percent) response value, although ratio users think in percent change: This is a feature request (a ΔR/R0 metric), not a defect. The manual is correct: metrics.md defines the response metrics as absolute differences, and the tester's screen worked. Nothing in the manual is wrong or misleading.
- rapid_response_ratio missing from the dashboard table and scatter axes: Refuted. I opened a copy of the tester's own dashboard (intensity/out/run3/calcium_A/dashboard.html, copied to verify1/dashA) in headless Edge. The #sx option list ends with rapid_response_ratio, and tableColumns() includes rapid_response_ratio. The tester most likely missed the last entry of the list.
- The Images card does not show whether an image has stage positions: The Images card does show it. gui.html:234-235 adds a green 'stage position' chip (or 'stitched · stage positions') to every image that has one. The tester's images had no positions, so no chip appeared, which is correct. A positions file does not change the per-image chips, and the manual does not claim it does; the Stage positions file field then says whether the images carry positions (gui.html:339). An explicit 'no stage position' chip would be clearer, but the manual statement is not wrong.
- Undocumented relation between stage_positions.txt values and the .rgn / abs_x_m coordinates (sign and axes): The swap and the sign change are intended. The stage.py module docstring says the stage frame is converted to the .rgn frame as abs_x = -stage_Y ..., abs_y = -stage_X ..., 'validated on the Leica Stellaris stage', the same convention as for .lif metadata. The text file holds stage X and Y as the manual says. The tester's expectation that abs_x_m ≈ file X was a wrong assumption, and a user who copies stage X/Y from LAS X gets correct .rgn positions. At most a nice-to-have note.
- The log of a re-run lists fewer moved files than the confirmation and than were actually moved: Intended and harmless. clear_run deliberately leaves the bookkeeping files (_QUIET: run.json, run_log.txt, settings_used.json) out of the returned list for the log (pipeline.py line 258). The confirmation lists them, and they are moved. Nothing is lost or misreported in a way that matters.
- The confirmation of 'Apply to all images' leaves out a changed response-window anchor: Not harmful. export.js line 109 names only the own-setting keys that imgC itself had and that change (here response_window). The anchor change is an ordinary global screening change, applied exactly as the user set it in the dashboard. The dialog presents the whole thing as 'Use these screening settings for all images', and it does not list criteria or other global changes either. The result matched what the user chose.
- 'µm' shows up as a garbled character in 'stitch --help' in the Windows console: Depends on the environment, not a program defect for the documented use. Piped through Git Bash, Python writes cp1252 byte 0xB5 (verified with od: '\265 m'), which mintty (UTF-8) shows as garbage. The manual tells users to run the commands in PowerShell, where Python writes to the console with WriteConsoleW and 'µm' shows correctly.
