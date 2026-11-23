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
