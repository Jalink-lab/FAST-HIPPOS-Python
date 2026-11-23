# Changelog

The notes of a version (`## <version>`) are shown by FAST-HIPPOS when it offers that version as an update.

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
