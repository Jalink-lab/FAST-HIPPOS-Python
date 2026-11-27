---
title: Cell values (metrics)
---

# Cell values (metrics)

FAST-HIPPOS measures these values for every cell. The program (the window, the dashboards and the overviews) shows them by their **name**, with the meaning as a tooltip; the files (`cells.tsv`, the hit lists, the settings and `screening_from_dashboard.toml`) use the **column**. *Lifetime* stands for the measured quantity: the ratio for ratio imaging, the intensity for intensity-only data.

A *response* is a change from the cell's own baseline; *during* means the value itself. The *response window* (Timing, in the dashboard and the window) decides which frames the mean values use; the peak values use the whole response, from the stimulation to the calibration.

## Values of the response

Hit criteria and gates can use these, and they can sort the hits, colour the cells and be an axis of the scatter plots. With several FLIM readouts, the values of another readout are shown as *readout · name* (e.g. *cAMP · Peak response*) and are in the files as `readout.column`.

| Name | Column in the files | Meaning |
|---|---|---|
| Baseline | `baseline_mean` | Average lifetime of the cell before the stimulation (its baseline). |
| Mean during response | `response_mean_abs` | Average lifetime of the cell in the response window (the value itself, not the change). |
| Mean response | `response_mean_diff` | Average change of the lifetime in the response window, compared with the cell's own baseline (lifetime − baseline). |
| Mean/peak response ratio | `response_fraction` | Mean response (in the response window) ÷ peak response (over the whole response). 1 = the cell is at its peak during the whole window; lower = only part of the time: a response that fades (transient), or one that rises slowly. With the response window at the end of the response (before C) it tells how much of its peak the cell keeps (sustained). |
| Peak during response | `response_max_abs` | Highest lifetime of the cell between the stimulation and the calibration. |
| Peak response | `response_max_diff` | Largest change of the lifetime after the stimulation, compared with the cell's own baseline. The usual measure of how strongly a cell responds. |
| Peak response vs. population baseline | `response_max_diff_pop` | Largest lifetime after the stimulation minus the average baseline of all cells (instead of the cell's own baseline). |
| Rise time (frames) | `rise_time_frames` | Number of frames of the response up to and including the first frame in which the cell reaches the rise fraction (e.g. 75 %) of its peak response (1 = already in the first frame after the stimulation). Small = fast responder. Only meaningful for cells that respond: combine it with an AND criterion on the response. |
| Late/early response ratio | `rapid_response_ratio` | Average response in the second half of the response period divided by that in the first half. Above 1 = still rising, below 1 = fading. |
| Mean during calibration | `calibration_mean` | Average lifetime of the cell during the calibration (maximal stimulation). |
| Calibration response | `calibration_diff` | Response to the calibration: mean during calibration − baseline. Shows whether the sensor works in this cell. |
| Baseline offset from population | `baseline_dev_pop` | How much the baseline of the cell differs from the average baseline of all cells. |
| Additional channel intensity | `additional_intensity` | Intensity of the additional channel in the cell (mean over time, or the first frame). |

## Measures of the cell

From the segmentation. Hit criteria and gates can use these too.

| Name | Column in the files | Meaning |
|---|---|---|
| Mean intensity | `mean_intensity` | Mean pixel value of the cell per frame, over the frames used for the segmentation, in the units of the image (photon counts or amplitudes). The *Minimum cell intensity* filter uses the same value. |
| Area (µm²) | `area_um2` | Size of the cell in µm²: the area in pixels times the pixel size squared. |
| Circularity | `circularity` | 4π · area / perimeter²: 1 for a circle, lower for irregular shapes. |

## Other columns of the tables

In `cells.tsv` and in the Cells table of the dashboard; not for criteria.

| Name | Column in the files | Meaning |
|---|---|---|
| Area (pixels) | `area_px` | Size of the cell in pixels. |
| Centre x, y (px) | `centroid_x, centroid_y` | Centre of the cell in the image (pixels). |
| Position x, y (px) | `pos_x_px, pos_y_px` | The position used for the hit: the centre of the cell, or of its nucleus with a nuclei classifier (pixels). |
| Stage x, y (m) | `abs_x_m, abs_y_m` | That position as a stage position (metres), as written to the .rgn files: in the frame of the LAS X Navigator (see [Back to the microscope](../guide/microscope.md#stage-coordinates-and-the-rgn-frame)). |
| Additional channel class | `class_additional` | 1 when the cell is positive for the additional channel (classification on), else 0. |
| Valid | `valid` | The cell passes the quality gates. |
| Hit | `hit` | The cell is a hit. |
| Response rank | `response_rank` | Rank of the cell in the order of mean response (0 = lowest). |
