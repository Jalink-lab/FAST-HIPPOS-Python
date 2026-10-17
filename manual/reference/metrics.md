---
title: Cell values (metrics)
---

# Cell values (metrics)

FAST-HIPPOS measures these values for every cell. They can be used in hit criteria, for sorting the hits, as axes of the scatter plots and for colouring the cells in the dashboard. *Lifetime* stands for the measured quantity: the ratio for ratio imaging, the intensity for intensity-only data.

| Name | Meaning |
|---|---|
| `baseline_mean` | Average lifetime of the cell before the stimulation (its baseline). |
| `response_mean_abs` | Average lifetime of the cell in the response window (the value itself, not the change). |
| `response_mean_diff` | Average change of the lifetime in the response window, compared with the cell's own baseline (lifetime − baseline). |
| `response_fraction` | How much of its maximal response the cell keeps in the response window: response_mean_diff ÷ response_max_diff (1 = sustained, near 0 = transient). |
| `response_max_abs` | Highest lifetime of the cell between the stimulation and the calibration. |
| `response_max_diff` | Largest change of the lifetime after the stimulation, compared with the cell's own baseline. The usual measure of how strongly a cell responds. |
| `response_max_diff_pop` | Largest lifetime after the stimulation minus the average baseline of all cells (instead of the cell's own baseline). |
| `rise_time_frames` | Number of frames of the response up to and including the first frame in which the cell reaches the rise fraction (e.g. 75 %) of its maximal response (1 = already in the first frame after the stimulation). Small = fast responder. Only meaningful for cells that respond: combine it with an AND criterion on the response. |
| `rapid_response_ratio` | Average response in the second half of the response period divided by that in the first half. Above 1 = still rising, below 1 = fading. |
| `calibration_mean` | Average lifetime of the cell during the calibration (maximal stimulation). |
| `calibration_diff` | Response to the calibration: calibration_mean − baseline_mean. Shows whether the sensor works in this cell. |
| `baseline_dev_pop` | How much the baseline of the cell differs from the average baseline of all cells. |
| `additional_intensity` | Intensity of the additional channel in the cell (mean over time, or the first frame). |

## Other values in the tables

These are in `cells.tsv` and in the Cells table of the dashboard (and can be shown in the scatter plot).

| Name | Meaning |
|---|---|
| `area_px` | Size of the cell in pixels. |
| `mean_intensity` | Mean pixel value of the cell per frame, over the frames used for the segmentation, in the units of the image (photon counts or amplitudes). The *Minimum cell intensity* filter uses the same value. |
| `circularity` | 4π · area / perimeter²: 1 for a circle, lower for irregular shapes. |
| `centroid_x, centroid_y` | Centre of the cell in the image (pixels). |
| `pos_x_px, pos_y_px` | The position used for the hit: the centre of the cell, or of its nucleus with a nuclei classifier (pixels). |
| `abs_x_m, abs_y_m` | That position as a stage position (metres), as written to the .rgn files: in the frame of the LAS X Navigator (see [Back to the microscope](../guide/microscope.md#where-the-stage-positions-come-from)). |
| `class_additional` | 1 when the cell is positive for the additional channel (classification on), else 0. |
| `valid` | The cell passes the quality gates. |
| `hit` | The cell is a hit. |
