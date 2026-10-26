# Questions and problems

## Starting

??? question "Nothing happens when I double-click the shortcut"
    FAST-HIPPOS may still be starting (the first start after an installation or update takes longer). If it is
    already running, the shortcut opens its window in the browser again. Otherwise open PowerShell in the
    FAST-HIPPOS folder and run `uv run fast-hippos-cli gui`: the console then shows what goes wrong.

??? question "The window says Cellpose is not available"
    FAST-HIPPOS looks for Cellpose in its own environment and in the environments set under *Cell segmentation →
    Advanced settings*. Set the `python.exe` of an environment with the Cellpose version that the model needs:
    Cellpose 3 for `cyto3` and `nuclei`, Cellpose 4 for `cpsam`. See [Installation](../start/install.md#4-cellpose).

??? question "Cellpose runs on the CPU, not on the GPU"
    The Cellpose environment needs PyTorch with CUDA support. *Use GPU* must also be on (*Cell segmentation →
    Advanced settings*). The label under the Cellpose model shows what was found.

## The analysis

??? question "My experiment has no calibration"
    Tick *No calibration* (*Stimulation and calibration*). Only the stimulation is then looked for, and the response
    lasts until the end of the movie; the calibration gate is not used.

??? question "The stimulation or the calibration was not found, or found at the wrong frame"
    Open the dashboard of the image, drag *S* and *C* to the right frames, and click *↻ Apply* (these settings
    for this image) or *↻ Apply as own timing*. See
    [Settings for single images](../guide/own-settings.md). If detection fails often, lower the *Detection threshold*
    (*Stimulation and calibration → Advanced settings*), or set the frames in the window.

??? question "Too many or too few cells"
    Check the outlines in the dashboard. With Cellpose, set the *Cell diameter* (in pixels) instead of 0, or try
    another model. *Minimum cell size* removes debris; the advanced settings also filter on circularity and
    intensity.

??? question "Many cells are not valid, or there are no hits at all"
    The quality gates remove them (the log warns when hardly any cells pass). Look at the histograms of the gates in
    the dashboard: is the calibration response in the range of *calibration − baseline*? The gates are in the unit
    of the measured value; the default range (0.5–1 ns) suits the usual lifetime sensors. For ratio and intensity
    data the gates start off; set them from their histograms. Without hit criteria no cell is a hit.

??? question "No .rgn files were written"
    The images have no stage positions (the window warns about this). See
    [where the stage positions come from](../guide/microscope.md#where-the-stage-positions-come-from).

??? question "The positions of the .rgn file don't land on the cells in the LAS X Navigator"
    Microscopes differ in how their stage axes relate to the Navigator. Change *.rgn: swap stage X and Y*,
    *.rgn: invert X* or *.rgn: invert Y* (*Screening → Advanced settings*) and click *Re-apply all images*; see
    [stage coordinates and the .rgn frame](../guide/microscope.md#stage-coordinates-and-the-rgn-frame).

??? question "I changed the criteria in the dashboard, but the .rgn files did not change"
    Changes in a dashboard only affect that page until you click *↻ Apply* (or *↻ Apply as own timing*), or
    save the hits with *Hits → .rgn*. The Apply buttons only appear in dashboards opened from the FAST-HIPPOS window.

??? question "Can I analyze images with different protocols?"
    Yes. Every image is analyzed on its own. Leave the stimulation frames on automatic, or give single images
    [their own settings](../guide/own-settings.md). The hit criteria are those of the window, for every image; to
    compare images they should be the same (see [Are the images comparable?](../guide/screen.md#are-the-samples-comparable)).

## Results

??? question "I only have one image. Do I need an experiment?"
    You choose an experiment folder (it may be empty, and the window proposes one next to your image), and the image gets a
    folder in it. Everything works as for a screen, and the experiment overview is just short. See
    [Your first analysis](../start/first-analysis.md).

??? question "Where are my results?"
    In the folder of the image, inside the experiment folder you chose; see [the output folder](../guide/output-folder.md).
    *Open its folder* in the Run card opens it.

??? question "I ran the analysis again, and my previous results are gone"
    Analyzing an image of the same name again (tick it in the *Images* card) replaces its previous results, after asking. Give the image another
    name (its row in the *Images* card) to keep both. If a run did not finish, the previous results are still in
    `_previous_run` in the folder of the image.

??? question "Can someone without FAST-HIPPOS look at the results?"
    Yes: send the experiment folder (or the folder of one image, with its `frames/` and `tiles/`). The overviews (`index.html`) and the dashboards open in any browser.

## Still stuck?

Report it on [GitHub](https://github.com/Jalink-lab/FAST-HIPPOS-Python/issues), with the log (`run_log.txt` in the
folder of the image) and the settings file.
