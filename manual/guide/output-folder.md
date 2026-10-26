# The output folder

All results go into the **experiment folder** that you choose in the *Images* card. Every image gets a folder of its
own in it, named as in the Images list: **one image folder holds one run** of one image, with its hit list and `.rgn`
files. The experiment folder itself holds the overview of all images, which may come from different input folders. (A run of several images in one folder, with
one combined hit list, can still be made with a settings file on the
[command line](../reference/command-line.md).)

## What is in it

```text
example_screen_1/               one image: its folder in the experiment folder
├── index.html                 the overview of this image alone
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
│   ├── frames/                the frames of the dashboard, one file each
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

The experiment folder holds one such folder per image, and adds `index.html` (the overview of all images),
`experiment_summary.tsv` (its images table, with the label and the source of each image) and, after
*Re-apply all images*, `experiment_log.txt`; see [A screen of many images](screen.md).

!!! tip "Sharing"
    The overview and the dashboards work without FAST-HIPPOS. The frames of a dashboard are files of their own, in
    its `frames/` folder, and large images have a `tiles/` folder. To share the results of an image, copy its whole
    folder, with `frames/` and `tiles/`. To share the experiment, copy the whole experiment folder.

## Running again

An image that already has results in the experiment folder (an image of the same name) is unticked in the Images
list. When you tick it and click **Run analysis**, its results are replaced. FAST-HIPPOS first lists exactly what
will be replaced (the folders and the files of the run), and moves them into a subfolder `_previous_run` of the image
folder before it starts. When the new run is complete,
`_previous_run` is deleted; if the run is stopped or fails, it is kept, so nothing is lost. Other files in the
folder are never touched. To keep both runs, give the image another name.

To go back to the previous run after a stopped run: delete the partial results of the stopped run (the image folders
and the files listed above), and move the contents of `_previous_run` back into the image folder. Do this before
the next complete run, which deletes `_previous_run` (the window reminds you).

**Re-apply this image** keeps the segmentation and the traces of the current image, and redoes the rest with the
current settings: stimulation detection, screening, hit lists, `.rgn` files, overview and dashboard. It takes
seconds. It always processes the image *as analyzed*, also when the Images list in the window has changed since; the
window warns when they differ. **Re-apply all images** does this for every image of the experiment.

What a re-apply can change: the stimulation and calibration, the screening, the hit lists and `.rgn` files, and the
display settings. What only a new run changes: the images, the segmentation, the traces, and a few settings that are
needed while measuring (the size of the dashboards, the stage positions file).

The *↻ Apply* buttons in the dashboards do a re-apply too; see [Choosing the hits](choosing-hits.md#apply-the-settings).
