# The output folder

Every image is a sample, and every sample gets a folder of its own inside the experiment folder that you choose in
the *Images* card: **one folder holds one run** of one image, with its hit list and `.rgn` files. (A run of several
images in one folder, with one combined hit list, can still be made with a settings file on the
[command line](../reference/command-line.md).)

## What is in it

```text
example_screen_1/               one sample: its folder in the experiment folder
├── index.html                 the overview of the sample
├── HITS_example_screen_1.rgn  stage positions of all its hits
├── HITS_example_screen_1_1-24.rgn  … in files of at most 1000 positions, each with its route
├── hits.tsv                   the hit list
├── hits_1-24.tsv              … per .rgn file, in visiting order
├── cell_coordinates.tsv       positions of all cells
├── run_summary.tsv            the images table of the overview
├── hit_positions.png          a map of the hits and their routes
├── run_log.txt                the log
├── fast_hippos_settings.toml  the settings of the run, to open in the window or use on the command line
├── settings_used.json         the same, as the program used them
├── run.json, hit_chunks.json  bookkeeping of the run (which files it wrote; the hits per .rgn file)
├── example_screen_1/          the image: its dashboard and tables
│   ├── dashboard.html         the dashboard
│   ├── cells.tsv              all cells: position, size, values, gates, hit or not
│   ├── lifetime_traces.tsv    the trace of every cell (and additional_traces.tsv)
│   ├── labels.tif             the segmentation: one number per cell
│   ├── weighted_lifetime.tif  the lifetime image (time-lapse)
│   ├── intensity_projection.tif
│   ├── kymograph*.tif, traces.png
│   └── tiles/                 full-resolution parts of large images, for the dashboard
└── …
```

The `.tsv` files are tab-separated tables: open them in Excel, or in Python or R. The TIFF images open in Fiji.

In a [screen of several samples](screen.md) every sample has an output folder like this one, inside the experiment
folder, which adds `index.html` (the overview of all samples), `experiment_summary.tsv` (its images table, with
the sample and its label) and, after *Re-apply all samples*, `experiment_log.txt`.

!!! tip "Sharing"
    The overview and the dashboards work without FAST-HIPPOS. To share the results, copy the whole output folder
    (with the `tiles` folders), or for one image just its folder.

## Running again

**Run analysis** into a folder that already holds a run replaces that run. FAST-HIPPOS first lists exactly what will
be replaced (the image folders and the files of the run), and moves them into a subfolder `_previous_run` before it
starts. When the new run is complete, `_previous_run` is deleted; if the run is stopped or fails, it is kept, so
nothing is lost. Other files in the folder are never touched.

To go back to the previous run after a stopped run: delete the partial results of the stopped run (the image folders
and the files listed above), and move the contents of `_previous_run` back into the output folder. Do this before
the next complete run, which deletes `_previous_run` (the window reminds you).

**Re-apply screening** keeps the segmentation and the traces of the run in the folder, and redoes the rest with the
current settings: stimulation detection, screening, hit lists, `.rgn` files, overview and dashboards. It takes
seconds. It always processes the images *of the run*, also when the image list in the window has changed since; the
window warns when they differ.

What a re-apply can change: the stimulation and calibration, the screening, the hit lists and `.rgn` files, and the
display settings. What only a new run changes: the images, the segmentation, the traces, and a few settings that are
needed while measuring (the size of the dashboards, the stage positions file).

The *Apply* buttons in the dashboards do a re-apply too; see [Choosing the hits](choosing-hits.md#apply-the-settings).
