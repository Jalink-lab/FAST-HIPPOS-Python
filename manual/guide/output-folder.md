# The output folder

Each run writes its results in the output folder you choose in the *Images* card. **One output folder holds one
run**: the images analyzed together, with one combined hit list.

## What is in it

```text
example_run/
├── index.html                 the run overview
├── HITS_example_run.rgn       stage positions of all hits
├── HITS_example_run_1-75.rgn  … in files of at most 1000 positions, each with its route
├── hits.tsv                   the hit list
├── hits_1-75.tsv              … per .rgn file, in visiting order
├── cell_coordinates.tsv       positions of all cells
├── run_summary.tsv            the images table of the overview
├── hit_positions.png          a map of the hits and their routes
├── run_log.txt                the log
├── fast_hippos_settings.toml  the settings of the run, to open in the window or use on the command line
├── settings_used.json         the same, as the program used them
├── run.json, hit_chunks.json  bookkeeping of the run (which files it wrote; the hits per .rgn file)
├── example_screen_1/          one folder per image
│   ├── dashboard.html         the dashboard
│   ├── cells.tsv              all cells: position, size, values, gates, hit or not
│   ├── lifetime_traces.tsv    the trace of every cell (and additional_traces.tsv)
│   ├── labels.tif             the segmentation: one number per cell
│   ├── weighted_lifetime.tif  the lifetime image (time-lapse)
│   ├── intensity_projection.tif
│   ├── kymograph*.tif, traces.png
│   └── tiles/                 full-resolution parts of large images, for the dashboard
├── example_screen_2/
└── …
```

The `.tsv` files are tab-separated tables: open them in Excel, or in Python or R. The TIFF images open in Fiji.

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
needed while measuring (smoothing of the lifetime overlay, the size of the dashboards, the stage positions file).

The *Apply* buttons in the dashboards do a re-apply too; see [Choosing the hits](choosing-hits.md#apply-the-settings).
