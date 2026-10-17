# Glossary

Additional channel
:   An extra channel whose intensity is measured per cell, e.g. a transfection marker. Cells can be classified as
    positive or negative on it.

Baseline
:   The part of a trace before the stimulation.

Calibration
:   A maximal stimulus at the end of the experiment, which shows how far the sensor can go in each cell. Used by the
    quality gates.

Criterion
:   A condition on a cell value, such as `response_mean_diff < 0.6`. AND criteria must all pass; of the OR criteria
    one is enough.

Dashboard
:   The interactive page of one image (`dashboard.html`).

Hit
:   A valid cell that meets the hit criteria (or that you picked by hand).

Kymograph
:   An image with one column per cell and one row per frame: all traces at once.

Lifetime
:   The fluorescence lifetime of the sensor in a cell, in ns. For ratio and intensity data, read *ratio* or
    *intensity*.

Output folder
:   The folder with the results of one run.

Overview
:   The page that compares the images of a run (`index.html`).

Quality gate
:   A condition that every hit must meet, to keep out cells whose traces cannot be trusted.

Re-apply
:   Redo the screening of a run with other settings, without segmenting and measuring again.

Response
:   The part of a trace between the stimulation and the calibration. The *response window* is the part of it whose
    average is the mean response.

.rgn file
:   A LAS X region file with stage positions, which the microscope can visit.

Run
:   One analysis of a set of images with one set of settings, in one output folder.

Stimulation
:   The stimulus whose effect is measured, e.g. adding an agonist. Its frame is the first frame with the stimulus.

Trace
:   The lifetime of one cell over time.

Valid cell
:   A cell that passes the quality gates.
