# How the analysis works

What FAST-HIPPOS does with your images, step by step. You don't need this to use it, but it helps to judge the
results.

## 1. Reading and pre-processing

The images are read with their channels, frame interval, pixel size and stage positions. Optionally, the phase
offset of bidirectional scanning is corrected (needed for some fast scans), and the drift of the sample is corrected
by registering every frame to a reference frame.

## 2. Segmentation

The cells are found once, in a projection over time of the intensity, optionally of a part of the frames or
of a separate channel. The result is a label image: every cell a number. Cells can then be removed by size,
circularity and intensity. The cells do not move with time: the same outlines are used in every frame.

## 3. Traces

For every cell and every frame, FAST-HIPPOS computes one value from all pixels in the cell:

| Image type | Value of a cell |
|---|---|
| Fitted TCSPC (two components) | the amplitudes A₁ and A₂ of all pixels are pooled: τ = Σ(A₁τ₁ + A₂τ₂) / Σ(A₁ + A₂) |
| Fast FLIM, TauContrast, frequency-domain FLIM | the intensity-weighted mean lifetime |
| Ratio imaging | ΣC₁ / ΣC₂ |
| Intensity only | the mean intensity |

The mean intensity of the additional channel, if any, is measured too.

## 4. Stimulation and calibration

If the frames are not set, they are detected in the average trace of all cells: a stimulation or calibration shows up
as a sudden step, a peak in the second derivative of the trace. When one frame is set, the other is detected (the
strongest step after the stimulation, or before the calibration); with *No calibration* only the stimulation is
looked for. A peak counts when it stands out from the noise of
the trace by the *detection threshold* (5 × the noise σ by default; lower is more sensitive). The noise is estimated
robustly, so that a large calibration step does not hide a smaller stimulation.

The frames then divide every trace into the **baseline** (before the stimulation), the **response** (between the
stimulation and the calibration) and the **calibration**, leaving out a *margin* of one frame before each transition.

## 5. Cell values

From these parts, every cell gets a set of values, such as its baseline, its mean and maximal response, its rise time
and its calibration response. See [Cell values](metrics.md).

## 6. Screening

1. **Quality gates** keep the cells whose traces can be trusted: they respond to the calibration
   (*calibration − baseline* within a range), and their baseline is close to that of all cells. These are the
   *valid* cells.
2. **Classification** (optional) splits the cells on the intensity of the additional channel (on a log scale), by
   Otsu's method or a threshold you set.
3. **Hit criteria**: a valid cell is a hit when it passes all AND criteria, and at least one of the OR criteria (if
   there are any). Alternatively the hits are picked by hand.

The dashboard recomputes all of this in the browser, with the same results as the analysis.

## 7. Hit positions and routes

The stage position of a hit is the stage position of its image plus the offset of the cell in the image (its
centre, or the centre of its nucleus with a nuclei classifier). The hits are split into `.rgn` files of at most 1000
positions, and the order within each file is optimized to make the route of the stage short: a nearest-neighbour
route, improved by 2-opt and Or-opt moves, typically 13–18 % shorter than nearest neighbour alone.

## Speed and large images

On a stitched 1.9 GB data set (4089 × 2556 px, 30 frames, 3 channels, 10 239 cells), on a computer with a Quadro
RTX 3000 GPU (6 GB):

| Step | Time |
|---|---|
| Cellpose on the GPU | 1 min (`cyto3`, automatic diameter) to 2 min (`cpsam`) |
| everything else (measurement, screening, routes, dashboard with tiles) | about 2 min |
| re-applying the screening | 15–30 s |

Images larger than 1024 px are shown in the dashboard as an overview, while full-resolution tiles are loaded for the
visible area when zooming in, so that the dashboard stays responsive.

## Compared with the Fiji version

The Python version follows the workflow of the [Fiji macro](https://imagej.net/plugins/fast-hippos) v0.9.5, with
these differences:

- TCSPC cell lifetimes pool the fitted amplitudes of all pixels; the Fiji version averages the pixel lifetimes,
  weighted by intensity. The values differ slightly, most for dim cells, so thresholds do not transfer exactly.
- Frames count from 0 and denote the first frame with the stimulus: Fiji frames *s,c* become stimulation frame
  *s* + 1 and calibration frame *c* + 1.
- The stimulation detection uses a robust noise estimate.
- The Labkit step that puts the hit positions on the nuclei is replaced by a pixel classifier.
- Tiles are stitched by their stage positions, without Fiji.
