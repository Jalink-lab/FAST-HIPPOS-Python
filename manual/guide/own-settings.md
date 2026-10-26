# Settings for single images

All samples of an experiment are analyzed with the settings of the window, so that they can be compared. Sometimes
one image needs different timing: its stimulation started a few frames later, its calibration was missed by the
automatic detection, or its response is so slow that it needs another response window. For these cases an image can
get **its own settings**, without changing those of the other samples. (The image belongs to a sample; a sample made
with a settings file may hold several images, and then the other images of the sample keep their settings too.)

What can differ per image:

| | |
|---|---|
| Stimulation | stimulation frame, calibration frame, *no calibration*, *baseline only*, margin, and the detection threshold (only in a [settings file](../reference/command-line.md#settings-files)) |
| Response window | length, anchor (*after S* / *before C*) and margin |

Everything else, in particular the quality gates and the hit criteria, stays that of the sample: a hit means the
same for all images that you compare.

## Give an image its own settings

1. Open the dashboard of the image from the FAST-HIPPOS window (the *Image* menu in the top bar, or via an overview).
2. In the Screening pane, correct the timing: drag *S* and *C*, or type the frames. Change the response window if
   needed.
3. Click **↻ Apply to this image only**.

FAST-HIPPOS shows exactly what will become the image's own settings, e.g. *stimulation frame 7, calibration frame 22*.
After you confirm, it re-applies the sample of the image (its hit list, `.rgn` files and overview, and the experiment
overview), and the dashboard reloads. Other samples are not changed.

!!! note "Several images in a sample"
    A sample made with a settings file can hold several images. They keep their results, but the hit list, the
    `.rgn` files and their routes of the sample are made again, so that they include the corrected image.

## Where you see them

- **Dashboard**: an *own settings* label in the top bar (hover over it for the values), and the timing shows *(this
  image)* instead of *(auto)* or *(set)*.
- **FAST-HIPPOS window**: under *Stimulation and calibration*, a list of the images with their own settings.
- **Overviews** (of the sample and of the experiment): an *own settings* label next to the image name, and *image* next to its stimulation and calibration
  frames.
- **Log**: *Own settings of this image: …* for each such image.
- **Output folder**: in `settings_used.json` and `fast_hippos_settings.toml`, and as a column of `run_summary.tsv`.

## Remove them

In the FAST-HIPPOS window, click ✕ next to the image under *Stimulation and calibration*, and then *Re-apply this
sample* (or *Run analysis*). The image then uses the settings of the window again.

## How they combine with *Apply to all images*

**Apply to all images** uses the screening settings of the dashboard for all images of the sample (see
[Choosing the hits](choosing-hits.md#apply-the-settings)). From the dashboard of an image with its own settings:

- If you changed the timing there, that timing becomes the timing of **all** images of the sample, this one included:
  its own timing is replaced.
- Its own response window stays, unless you changed the response window there.
- Other images with their own settings keep them. The confirmation message names them.

**Re-apply all samples** (Run card) keeps the own settings of every image.

## Images in a new sample

Own settings belong to images by name, and are kept by the FAST-HIPPOS window for later runs (**＋ New sample** empties
them). When you analyze images of the same names again (`Position 1` …), check the list under *Stimulation and
calibration*. The window warns about it, and the confirmation of *Run analysis* lists the images that will use their
own settings.
