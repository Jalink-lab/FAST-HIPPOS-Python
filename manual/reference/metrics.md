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
| Baseline | `baseline` | Average lifetime of the cell before the stimulation (its baseline). |
| Mean during response | `mean_during_response` | Average lifetime of the cell in the response window (the value itself, not the change). |
| Mean response | `mean_response` | Average change of the lifetime in the response window, compared with the cell's own baseline (lifetime − baseline). |
| Mean/peak response ratio | `mean_peak_response_ratio` | Mean response (in the response window) ÷ peak response (over the whole response). 1 = the cell is at its peak during the whole window; lower = only part of the time: a response that fades (transient), or one that rises slowly. With the response window at the end of the response (before C) it tells how much of its peak the cell keeps (sustained). |
| Peak during response | `peak_during_response` | Highest lifetime of the cell between the stimulation and the calibration. |
| Peak response | `peak_response` | Largest change of the lifetime after the stimulation, compared with the cell's own baseline. The usual measure of how strongly a cell responds. |
| Peak response vs. population baseline | `peak_response_vs_population` | Largest lifetime after the stimulation minus the average baseline of all cells (instead of the cell's own baseline). |
| Rise time (frames) | `rise_time_(frames)` | Number of frames of the response up to and including the first frame in which the cell reaches the rise fraction (e.g. 75 %) of its peak response (1 = already in the first frame after the stimulation). Small = fast responder. Only meaningful for cells that respond: combine it with an AND criterion on the response. |
| Late/early response ratio | `late_early_response_ratio` | Average response in the second half of the response period divided by that in the first half. Above 1 = still rising, below 1 = fading. |
| Mean during calibration | `mean_during_calibration` | Average lifetime of the cell during the calibration (maximal stimulation). |
| Calibration response | `calibration_response` | Response to the calibration: mean during calibration − baseline. Shows whether the sensor works in this cell. |
| Baseline offset from population | `baseline_offset_from_population` | How much the baseline of the cell differs from the average baseline of all cells. |
| Additional channel intensity | `additional_channel_intensity` | Intensity of the additional channel in the cell (mean over time, or the first frame). |

## Measures of the cell

From the segmentation. Hit criteria and gates can use these too.

| Name | Column in the files | Meaning |
|---|---|---|
| Mean intensity | `mean_intensity` | Mean pixel value of the cell per frame, over the frames used for the segmentation, in the units of the image (photon counts or amplitudes). The *Minimum cell intensity* filter uses the same value. |
| Area (µm²) | `area_(um2)` | Size of the cell in µm²: the area in pixels times the pixel size squared. |
| Circularity | `circularity` | 4π · area / perimeter²: 1 for a circle, lower for irregular shapes. |

## Other columns of the tables

In `cells.tsv` and in the Cells table of the dashboard; not for criteria.

| Name | Column in the files | Meaning |
|---|---|---|
| Area (pixels) | `area_(px)` | Size of the cell in pixels. |
| Centre x, y (px) | `centroid_x_(px), centroid_y_(px)` | Centre of the cell in the image (pixels). |
| Position x, y (px) | `position_x_(px), position_y_(px)` | The position used for the hit: the centre of the cell, or of its nucleus with a nuclei classifier (pixels). |
| Stage x, y (m) | `stage_x_(m), stage_y_(m)` | That position as a stage position (metres), as written to the .rgn files: in the frame of the LAS X Navigator (see [Back to the microscope](../guide/microscope.md#stage-coordinates-and-the-rgn-frame)). |
| Additional channel class | `class_additional` | 1 when the cell is positive for the additional channel (classification on), else 0. |
| Valid | `valid` | The cell passes the quality gates. |
| Hit | `hit` | The cell is a hit. |
| Response rank | `response_rank` | Rank of the cell in the order of mean response (0 = lowest). |

## Column names of earlier versions

Before version 0.1.0b3 the columns had other names. FAST-HIPPOS reads settings files and results of earlier versions with the new names (re-applying an image writes its tables with them); scripts of your own that read the tables need the new names.

| Before 0.1.0b3 | Now |
|---|---|
| `baseline_mean` | `baseline` |
| `response_mean_diff` | `mean_response` |
| `response_max_diff` | `peak_response` |
| `response_mean_abs` | `mean_during_response` |
| `response_max_abs` | `peak_during_response` |
| `response_max_diff_pop` | `peak_response_vs_population` |
| `response_fraction` | `mean_peak_response_ratio` |
| `rise_time_frames` | `rise_time_(frames)` |
| `rapid_response_ratio` | `late_early_response_ratio` |
| `calibration_mean` | `mean_during_calibration` |
| `calibration_diff` | `calibration_response` |
| `baseline_dev_pop` | `baseline_offset_from_population` |
| `additional_intensity` | `additional_channel_intensity` |
| `area_um2` | `area_(um2)` |
| `area_px` | `area_(px)` |
| `centroid_x` | `centroid_x_(px)` |
| `centroid_y` | `centroid_y_(px)` |
| `pos_x_px` | `position_x_(px)` |
| `pos_y_px` | `position_y_(px)` |
| `abs_x_m` | `stage_x_(m)` |
| `abs_y_m` | `stage_y_(m)` |
