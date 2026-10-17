# Back to the microscope

The point of a screen is to do something with the hits: photoactivate them, image them at high resolution, follow
them over time. FAST-HIPPOS writes the stage positions of the hits as LAS X region files (`.rgn`), so that the
microscope can visit them one by one.

## The .rgn files

After a run with screening, the output folder holds:

| File | |
|---|---|
| `HITS_<run>.rgn` | all hits |
| `HITS_<run>_1-1000.rgn`, `HITS_<run>_1001-2000.rgn`, … | the hits in files of at most 1000 positions (*Hits per .rgn file*), each with its own short route |
| `hits_1-1000.tsv`, … | the same hits as tables, in visiting order |

`<run>` is the name of the output folder. Each file lists the positions in an order that keeps the stage travel
short: the route is optimized, typically 15–20 % shorter than going from each hit to the nearest next one. The
overview and the dashboards can draw these routes.

Load the `.rgn` file in LAS X as a set of positions, and set up the experiment that should run at every position.

!!! info "In LAS X"
    How positions are loaded depends on the LAS X version and the microscope. The `.rgn` files are the same as those
    of the Fiji version of FAST-HIPPOS.

Need other hits than the run gave? The dashboard (*Hits → .rgn*, *Selection → .rgn*) and the overview (*Export*) save
`.rgn` files of the current hits, of a hand-picked selection, or of a few images together.

## Where the stage positions come from

To compute the stage position of a cell, FAST-HIPPOS needs the stage position of its image, and the pixel size.
Usually these are read from the images:

- **Leica `.lif` files**: every image has its position in the file. A tile scan in a `.lif` is stitched, with the
  position of every tile.
- **TIFFs exported from LAS X**: from the `MetaData` folder that LAS X writes next to them. Keep it with the images.
- **Images stitched by FAST-HIPPOS, or by *Stitch tiles* in Fiji**: from their metadata.

The *Images* card shows for every image whether it has stage positions. For other images, choose a **Stage positions
file** under *Screening → Advanced settings*: a text file with the X and Y stage position (in metres) of every image,
in the order of the images, separated by spaces, tabs, commas or new lines (it replaces the positions in the
images); or the `.lif` file with the positions (used only for images without positions of their own).

Images without stage positions are still analyzed and screened, but their hits get no `.rgn` file; the window warns
about this before the run.

!!! tip "Hit positions on the nucleus"
    By default a hit position is the centre of the cell. With a *Nuclei classifier* (*Cell segmentation → Advanced*),
    trained on a few scribbles with `fast-hippos-cli train-classifier`, it becomes the centre of the nucleus, which is
    more precise for bean-shaped or irregular cells.

## Tile scans

A large area is usually imaged as a tile scan. LAS X can stitch it, but then the image keeps only one stage position,
while the screening needs the position of every tile. Instead:

1. In LAS X, **export the tiles**: one TIFF per tile (`name_s0.tif`, `name_s1.tif`, …), with the `MetaData` folder.
2. In the *Images* card, click **Add tile folder…** and choose the folder.

FAST-HIPPOS reads the position of every tile, corrects the bidirectional scanning phase if *Correct bidirectional
scanning phase* is on (once for all tiles), places each tile at its stage position, and saves the stitched image in
the output folder (`<name>_STITCHED.tif`), with the tile positions, so that it can be used again later. Tiles that
overlap are not blended yet: the later tile covers the earlier one.

If the `MetaData` folder is missing, choose the `.lif` file of the scan as *Stage positions file*: its positions are
then saved next to the tiles (`tile_positions.tsv`), and the `.lif` file is not needed again.
