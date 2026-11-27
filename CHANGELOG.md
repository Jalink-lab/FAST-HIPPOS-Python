# Changelog

The notes of a version (`## <version>`) are shown by FAST-HIPPOS when it offers that version as an update.

## 0.1.0b4

- **Cellpose on Intel Macs.** Installing Cellpose failed there, because PyTorch 2.6.0 has no version for Intel Macs.
  FAST-HIPPOS now installs PyTorch 2.2.2, the last version for Intel Macs, and Cellpose then runs on the processor.
  An Apple-silicon Mac that runs the installation under Rosetta gets a note on how to install the faster version.

## 0.1.0b3

Gates, hits by hand that behave, and readable names.

- **Gates.** Draw a region in the scatter plot of a dashboard (*✎ Gate*, then a box or lasso): cells inside it (or
  outside) are hits. A gate is a hit criterion like the others, so *Re-apply all images* uses it for every image.
- **Readable names.** Cell values are shown as *Peak response*, *Baseline*, *Area (µm²)*… with their meaning as a
  tooltip. Hit criteria and gates can also use *Mean intensity*, *Area (µm²)* and *Circularity*.
- **New column names in the tables** (`cells.tsv`, hit lists), e.g. `peak_response` (was `response_max_diff`) and
  `area_(um2)`. Settings and results of earlier versions are read with the new names; scripts of your own that read the
  tables need them too. The list is in the manual: *Reference → Cell values*.
- **Hits chosen by hand.** *Add selection* and *Remove selection* start from the hits of the criteria, show the new
  hits at once, and are kept when the dashboard is opened again.
- **Curve fits** in the scatter plot of the overview: linear, exponential, logarithmic and sigmoid, with parameters,
  standard errors and R², and an export.
- The classification of the additional channel has a logarithmic histogram (on by default).
- Questions and messages appear in a FAST-HIPPOS dialog instead of the browser's.
- *Apply* in a dashboard asks about that image only.

Known limitations of this beta:

- **Check the stage positions of hits in stitched `.lif` tile scans on real cells.** FAST-HIPPOS places 512-pixel tiles
  512 pixels apart, while LAS X measures from centre to centre (511).
- The experiment overview shows the first readout only.
- Several readouts work for `.lif` files with a LAS X fit, not yet for TIFFs.
- Cell values differ from the Fiji macro, which averages a cell in another way.

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
