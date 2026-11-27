# Changelog

The notes of a version (`## <version>`) are shown by FAST-HIPPOS when it offers that version as an update.

## 0.1.0b3

- **Cellpose on Intel Macs.** Installing Cellpose failed there, because PyTorch 2.6.0 has no version for Intel Macs.
  FAST-HIPPOS now installs PyTorch 2.2.2, the last version for Intel Macs, and Cellpose then runs on the processor.
  An Apple-silicon Mac that runs the installation under Rosetta gets a note on how to install the faster version.

## 0.1.0b2

A simpler way of working, and FLIM directly from the `.lif`.

- **The experiment comes first.** A bar at the top shows the open experiment, with your recent experiments, *New* and
  *Open*. An experiment remembers its images, also those not analyzed yet.
- **One Images table** with every image of the experiment: tick, name, label, status, hits and *Open*.
- **A single image needs no setup.** Click *Add images…* and accept the proposed folder; the dashboard opens when it is done.
- **One folder per image.** New results are in `<experiment>\<image>`. Experiments of earlier versions keep working.
- **FLIM from the `.lif`.** FAST-HIPPOS reads the LAS X fit directly, with the lifetimes from the file: no TIFF export.
- **Several FLIM readouts**, e.g. cAMP and calcium, on the same cells, each with its own timing and dashboard. Hit criteria
  can combine them into one hit list and one set of `.rgn` files.

Known limitations of this beta:

- **Check the stage positions of hits in stitched `.lif` tile scans on real cells.** FAST-HIPPOS places 512-pixel tiles
  512 pixels apart, while LAS X measures from centre to centre (511).
- The experiment overview shows the first readout only.
- Several readouts work for `.lif` files with a LAS X fit, not yet for TIFFs.
- Cell values differ from the Fiji macro, which averages a cell in another way.

## 0.1.0b1

First release with an installer.

- **Installer.** A Windows setup that needs no administrator rights, and `install.sh` for macOS and Linux. Python and
  all packages are installed in one folder of their own.
- **Updates.** FAST-HIPPOS looks for a new version once a day. *Check for updates* in the top bar checks at any time and
  installs the update. Settings and results are not touched.
- **Cellpose setup.** The *Cell segmentation* section shows Cellpose 3 and 4 on this computer. FAST-HIPPOS looks for
  existing installations and asks whether to use one, or to install Cellpose with FAST-HIPPOS. You can also choose your
  own `python.exe`, or search all drives.
- **More image formats.** OME-TIFF and Zeiss `.czi` (beta, not yet tested on real Zeiss time-lapses), with one row per
  series or scene. Screening stays available for Leica data only.
- `.lif` files are now read with `liffile`, which replaces the deprecated `readlif` and also opens files that `readlif`
  could not read. `.lif` support is part of every installation.
