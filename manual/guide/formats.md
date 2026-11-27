# Image formats

FAST-HIPPOS reads time-lapse images from several file formats. Add them with **Add images…** in the
[Images card](window.md#images). A file with several images (series or scenes) gets one row per image in the Images
list, and every row is analyzed in a folder of its own.

| Format | Extensions | Several images in a file | Pixel size and frame interval | Screening |
|---|---|---|---|---|
| **Leica LIF** | `.lif` | yes, every series | from the file | **yes** |
| **TIFF exported from LAS X** | `.tif` with its `MetaData` folder | no | from the file | **yes** |
| **Tile folder from LAS X** | a folder of `.tif` tiles | stitched into one image | from the file | **yes** |
| **ImageJ / Fiji TIFF** | `.tif`, `.tiff` | no | from the file | **yes**, with a [stage positions file](microscope.md#where-the-stage-positions-come-from) |
| **OME-TIFF** | `.ome.tif`, `.ome.tiff` | yes, every series | from the OME metadata | no |
| **Zeiss CZI** (beta) | `.czi` | yes, every scene | from the file | no |

## Screening is for Leica data

*Screen for hits* writes the stage positions of the hits as `.rgn` files for the LAS X Navigator, so that the Leica
microscope can revisit them. It is therefore available for Leica data only. CZI and OME-TIFF images are analyzed in
full (segmentation, traces, metrics, dashboards and overviews), but without hits. With such an image in the list and
*Screen for hits* on, the Run card says what to change before the analysis starts.


## FLIM data in a .lif file { #flim-in-lif }

A Leica `.lif` holds the FLIM fit that you made in LAS X, so you do not have to export TIFFs. Add the `.lif` with
**Add images…**, with the image type *Fitted TCSPC data / TauSeparation*:

- Every image of the file gets one row. The parts of its FLIM analysis (phasor, decay and fit maps) are not listed.
- FAST-HIPPOS reads LAS X's photon counts and mean photon arrival time per pixel. That image is the photon-weighted mean
  of the lifetimes of the components, so it works for a fit with any number of components.
- The lifetimes **τ₁** and **τ₂** are read from the file and greyed out in the window.
- An image with FLIM data **that was not fitted** in LAS X starts unticked. Fit it in LAS X and save the file first.

### Several FLIM readouts { #flim-readouts }

When the fit has several FLIM channels, for instance cAMP and calcium, the *Images* card shows a **FLIM readouts** table.
Give each readout a name, and untick one to leave it out.

- The **first ticked readout** finds the cells. All readouts are measured in exactly the same cells.
- **Timing.** Each readout has its own stimulation and calibration, detected in its own trace. To set a frame by hand,
  fill it in for that readout; empty means *as under Stimulation and calibration*. In the dashboard of a readout, *Apply as
  own settings* keeps a timing for that readout of that one image.
- **Dashboards.** *Readout* in the top bar of a dashboard switches to the other readout, at the same frame. The cell panel
  shows the trace of the other readout as a dashed line on its own scale, and the scatter plot can use its values
  (`Calcium.peak_response`, or *Calcium @ frame*).
- **Hits.** Hit criteria belong to the first readout and can use the metrics of the other one, for instance
  `peak_response > 0.3` AND `Calcium.peak_response < 0.1`. There is one hit list and one set of `.rgn` files, and
  every readout shows the same hits.
- **Files.** The first readout is directly in the folder of the image, a further readout in a subfolder with its name
  (`plate 1\Calcium\`). `cells.tsv` and `hits.tsv` of the first readout also hold the metrics of the other readout.
- The overview of the experiment shows the first readout.

## Zeiss CZI (beta)

- Every scene is an image. A tile scan is read as one image, already stitched by the Zeiss reader.
- A colour image gets one channel each for red, green and blue.
- Images with both z-slices and time frames are not supported. Neither are files with other varying dimensions, such as
  phases or views; FAST-HIPPOS names them when it refuses the file.
- On a Mac with an Intel processor CZI files cannot be read: export them as TIFF.

!!! warning "Not yet tested on real Zeiss files"
    CZI reading has been tested on files written with Zeiss's own library, not yet on time-lapses from a Zeiss
    microscope. Check the pixel size and frame interval shown in the Images table. If the frame interval is missing, set
    *Default frame interval* in the advanced settings of the Images card.

## OME-TIFF

The pixel size and frame interval come from the OME metadata. Files whose name ends in `.ome.tif` or `.ome.tiff` get
one row per series. An OME-TIFF with another name is also recognized, but only its first series is read.
