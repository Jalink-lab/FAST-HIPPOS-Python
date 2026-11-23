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
- `.lif` support is now part of every installation.
