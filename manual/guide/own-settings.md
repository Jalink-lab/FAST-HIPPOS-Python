# Settings for single images

All images of an experiment are analyzed with the settings of the window, so that they can be compared. Sometimes
one image needs different timing: its stimulation started a few frames later, its calibration was missed by the
automatic detection, or its response is so slow that it needs another response window. For these cases an image can
get **its own settings**, without changing those of the other images.

What can differ per image:

| | |
|---|---|
| Stimulation | stimulation frame, calibration frame, *no calibration*, *baseline only*, margin, and the detection threshold (only in a [settings file](../reference/command-line.md#settings-files)) |
| Response window | length, anchor (*after S* / *before C*) and margin |

Everything else, in particular the quality gates and the hit criteria, stays that of the window: a hit means the
same for all images that you compare.

## Give an image its own settings

1. Open the dashboard of the image from the FAST-HIPPOS window (the *Image* menu in the top bar, or via an overview).
2. In the Screening pane, correct the timing: drag *S* and *C*, or type the frames. Change the response window if
   needed.
3. Click **↻ Apply as own timing**.

FAST-HIPPOS shows exactly what will become the image's own settings, e.g. *stimulation frame 7, calibration frame 22*.
After you confirm, it re-applies the image (its hit list, `.rgn` files and the experiment overview), and the
dashboard reloads. Other images are not changed.

!!! note "Several images in one run"
    A run made with a settings file on the command line can hold several images. They keep their results, but the
    hit list, the `.rgn` files and their routes of the run are made again, so that they include the corrected image.

## Where you see them

- **Dashboard**: an *own settings* label in the top bar (hover over it for the values), and the timing shows *(this
  image)* instead of *(auto)* or *(set)*.
- **FAST-HIPPOS window**: under *Stimulation and calibration*, a list of the images with their own settings.
- **Overview**: an *own settings* label next to the image name, and *image* next to its stimulation and calibration
  frames.
- **Log**: *Own settings of this image: …* for each such image.
- **Output folder**: in `settings_used.json` and `fast_hippos_settings.toml`, and as a column of `run_summary.tsv`.

## Remove them

In the FAST-HIPPOS window, click ✕ next to the image under *Stimulation and calibration*, and then *Re-apply this
image* (or *Run analysis*). The image then uses the settings of the window again.

## How they combine with *Apply*

**↻ Apply** uses the screening settings of the dashboard for this image (see
[Choosing the hits](choosing-hits.md#apply-the-settings)). From the dashboard of an image with its own settings:

- If you changed the timing there, that timing replaces the own timing of this image, and becomes the timing of the
  window (use *Apply as own timing* to keep it for this image only).
- Its own response window stays, unless you changed the response window there.

**↻ Re-apply all images** (Run card) keeps the own settings of every image.

## Images of the same name

Own settings belong to images by name. The window keeps them only for the images in the Images list and for the
current image; **＋ New image** drops the others. When you analyze images of the same names again (`Position 1` …),
check the list under *Stimulation and calibration*. The window warns about it, and the confirmation of *Run analysis*
lists the images that will use their own settings.
