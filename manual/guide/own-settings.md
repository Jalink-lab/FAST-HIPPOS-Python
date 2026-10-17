# Settings for single images

All images of a run are analyzed with the same settings. Sometimes one image needs different timing: its
stimulation started a few frames later, its calibration was missed by the automatic detection, or its response is so
slow that it needs another response window. For these cases an image can get **its own settings**, without changing
those of the other images.

What can differ per image:

| | |
|---|---|
| Stimulation | stimulation frame, calibration frame, *no calibration*, *baseline only*, margin, and the detection threshold (only in a [settings file](../reference/command-line.md#settings-files)) |
| Response window | length, anchor (*after S* / *before C*) and margin |

Everything else, in particular the quality gates and the hit criteria, is the same for all images: a hit means the
same in every image.

## Give an image its own settings

1. Open the dashboard of the image from the FAST-HIPPOS window (or via the overview).
2. In the Screening pane, correct the timing: drag *S* and *C*, or type the frames. Change the response window if
   needed.
3. Click **↻ Apply to this image only**.

FAST-HIPPOS shows exactly what will become the image's own settings, e.g. *stimulation frame 7, calibration frame 22*.
After you confirm, it re-applies the screening to all images (the hit list and the `.rgn` files cover all of them),
and the dashboard reloads.

!!! note "Why all images are re-applied"
    The other images keep their results, but the combined hit list, the `.rgn` files and their routes are made
    again, so that they include the corrected image.

## Where you see them

- **Dashboard**: an *own settings* label in the top bar (hover over it for the values), and the timing shows *(this
  image)* instead of *(auto)* or *(set)*.
- **FAST-HIPPOS window**: under *Stimulation and calibration*, a list of the images with their own settings.
- **Overview**: an *own settings* label next to the image name, and *image* next to its stimulation and calibration
  frames.
- **Log**: *Own settings of this image: …* for each such image.
- **Output folder**: in `settings_used.json` and `fast_hippos_settings.toml`, and as a column of `run_summary.tsv`.

## Remove them

In the FAST-HIPPOS window, click ✕ next to the image under *Stimulation and calibration*, and then *Re-apply
screening* (or *Run analysis*). The image then uses the settings of all images again.

## How they combine with *Apply to all images*

**Apply to all images** from the dashboard of an image with its own settings:

- If you changed the timing there, that timing becomes the timing of **all** images, this one included: its own
  timing is replaced.
- Its own response window stays, unless you changed the response window there.
- Other images with their own settings keep them. The confirmation message names them.

## Images in a new run

Own settings belong to images by name, and are kept by the FAST-HIPPOS window for later runs. When you start a new
experiment with images of the same names (`Position 1` …), check the list under *Stimulation and calibration*. The
window warns about it, and the confirmation of *Run analysis* lists the images that will use their own settings.
