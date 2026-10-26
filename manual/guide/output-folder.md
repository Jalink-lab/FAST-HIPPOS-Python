# The output folder

All results go into the **experiment folder** that you choose in the *Images* card. Every image is a sample, and every
sample gets a folder of its own in it: **one sample folder holds one run** of one image, with its hit list and `.rgn`
files. The experiment folder itself holds the overview of all samples. (A run of several images in one folder, with
one combined hit list, can still be made with a settings file on the
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

The experiment folder holds one such folder per sample, and adds `index.html` (the overview of all samples),
`experiment_summary.tsv` (its images table, with the sample and its label) and, after *Re-apply all samples*,
`experiment_log.txt`; see [A screen of several samples](screen.md).

!!! tip "Sharing"
    The overview and the dashboards work without FAST-HIPPOS. To share the results, copy the whole experiment folder
    (with the `tiles` folders), or for one sample just its folder.

## Running again

**Run analysis** of a sample that already has results in the experiment folder (a sample of the same name) replaces
them. FAST-HIPPOS first lists exactly what will be replaced (the image folders and the files of the run), and moves
them into a subfolder `_previous_run` of the sample folder before it starts. When the new run is complete,
`_previous_run` is deleted; if the run is stopped or fails, it is kept, so nothing is lost. Other files in the
folder are never touched. To keep both runs, give the new sample another name.

To go back to the previous run after a stopped run: delete the partial results of the stopped run (the image folders
and the files listed above), and move the contents of `_previous_run` back into the sample folder. Do this before
the next complete run, which deletes `_previous_run` (the window reminds you).

**Re-apply this sample** keeps the segmentation and the traces of the sample, and redoes the rest with the current
settings: stimulation detection, screening, hit lists, `.rgn` files, overview and dashboards. It takes seconds. It
always processes the images *of the sample as analyzed*, also when the image list in the window has changed since;
the window warns when they differ. **Re-apply all samples** does this for every sample of the experiment.

What a re-apply can change: the stimulation and calibration, the screening, the hit lists and `.rgn` files, and the
display settings. What only a new run changes: the images, the segmentation, the traces, and a few settings that are
needed while measuring (the size of the dashboards, the stage positions file).

The *Apply* buttons in the dashboards do a re-apply too; see [Choosing the hits](choosing-hits.md#apply-the-settings).
