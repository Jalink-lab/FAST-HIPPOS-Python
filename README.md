<p align="center">
  <img src="docs/images/logo.png" alt="FAST-HIPPOS" width="180">
</p>

<h1 align="center">FAST-HIPPOS for Python</h1>

<p align="center">
  <b>F</b>LIM <b>A</b>nalysis of <b>S</b>ingle-cell <b>T</b>races for <b>H</b>it <b>I</b>dentification of
  <b>P</b>henotypes in <b>P</b>ooled <b>O</b>ptical <b>S</b>creening
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-beta-yellow" alt="Status: beta">
  <a href="https://jalink-lab.github.io/FAST-HIPPOS-Python/"><img src="https://img.shields.io/badge/user%20manual-online-1f6fd1" alt="User manual"></a>
</p>

> [!NOTE]
> **Beta.** The analysis has been checked against the [Fiji version](https://imagej.net/plugins/fast-hippos) and on
> test data, but one step has not been tried on the microscope yet: the `.rgn` files that this version writes. Before
> you rely on them, load one in the LAS X Navigator and check that the positions land on the cells (see
> [Back to the microscope](https://jalink-lab.github.io/FAST-HIPPOS-Python/guide/microscope/)). Settings and file
> formats may still change.

FAST-HIPPOS finds the cells that respond differently in a time-lapse experiment, and sends the microscope back to
exactly those cells. It segments the cells, measures a fluorescence lifetime (or ratio, or intensity) trace for every
cell, picks the cells whose response matches what you are looking for, and writes their stage positions as Leica
LAS X `.rgn` files, so that the microscope can revisit them for photoactivation, high-resolution imaging, FRAP, and so
on. Outside screening, it is a fast way to get single-cell traces out of a time-lapse, and to look at them.

It runs in your web browser, on your own computer: a window for the settings, an interactive dashboard per image in
which you can change the hit criteria and see the hits change at once, and an overview that compares all images of
an experiment (every image is analyzed in a run of its own, in a folder of its own).

<p align="center">
  <img src="manual/images/dashboard_views.png" alt="The dashboard of one image" width="100%">
  <br><sub>The dashboard of one image of the example screen: the hits (outlined in pink) are the cells that barely
  respond to the stimulation.</sub>
</p>

## User manual

**<https://jalink-lab.github.io/FAST-HIPPOS-Python/>**

- [Installation](https://jalink-lab.github.io/FAST-HIPPOS-Python/start/install/)
- [Your first analysis](https://jalink-lab.github.io/FAST-HIPPOS-Python/start/first-analysis/), with
  [example data](https://github.com/Jalink-lab/FAST-HIPPOS-Python/releases/tag/example-data)
- [Try the dashboard and the overview in your browser](https://jalink-lab.github.io/FAST-HIPPOS-Python/start/demo/),
  without installing anything
- [User guide](https://jalink-lab.github.io/FAST-HIPPOS-Python/guide/window/), [all settings](https://jalink-lab.github.io/FAST-HIPPOS-Python/reference/settings/),
  [command line](https://jalink-lab.github.io/FAST-HIPPOS-Python/reference/command-line/), and
  [how the analysis works](https://jalink-lab.github.io/FAST-HIPPOS-Python/reference/analysis/) (including the
  differences from the Fiji version)

## Quick installation

With [uv](https://docs.astral.sh/uv/), in PowerShell (details, and Cellpose, in the
[manual](https://jalink-lab.github.io/FAST-HIPPOS-Python/start/install/)):

```powershell
git clone https://github.com/Jalink-lab/FAST-HIPPOS-Python.git
cd FAST-HIPPOS-Python
uv sync --extra lif
uv run fast-hippos-cli shortcut   # a desktop shortcut that opens FAST-HIPPOS
```

## The paper

FAST-HIPPOS (in its Fiji version) and the screening method it serves are described in: Mukherjee S, van Tooren M,
Sfakianakis D, Kemps D, Klarenbeek J, Zanetti G, Kuiken HJ, Lieftink C, van den Broek B, Beijersbergen RL, Jalink K.
*Beyond Static Screens: optical pooled screening of signaling dynamics using time-lapse FLIM.* bioRxiv 2025.
[doi:10.1101/2025.07.11.664338](https://doi.org/10.1101/2025.07.11.664338)

This is the Python version of the [FAST-HIPPOS Fiji plugin](https://imagej.net/plugins/fast-hippos)
([GitHub](https://github.com/Jalink-lab/FAST-HIPPOS)), following the workflow of the Fiji macro v0.9.5.

## Development

```powershell
uv sync                 # includes the dev group (pytest, ruff, mini-racer)
uv run pytest           # Python tests, JavaScript parity and syntax tests, manual checks
uv run ruff check
```

- The program is in `src/fast_hippos`; the window is `gui.py` with `templates/gui.html`, the dashboard and the
  overview are assembled from `templates/dashboard/` and `templates/overview/` into self-contained HTML files.
- The full specification and the validation against Fiji are in [`docs/SPEC.md`](docs/SPEC.md); the reference macro
  is in [`reference/fiji_v0.9.5`](reference/fiji_v0.9.5).
- The user manual is in `manual/` (MkDocs, `uv sync --group docs`, then `mkdocs serve`); its screenshots, reference
  pages and demo are made by the scripts in `tools/manual`, see
  [`tools/manual/MAINTAINING.md`](tools/manual/MAINTAINING.md).

## License and credits

GPL-3.0-or-later. FAST-HIPPOS was developed by Bram van den Broek in the
[Jalink lab](https://github.com/Jalink-lab) at the Netherlands Cancer Institute (NKI), Amsterdam.
