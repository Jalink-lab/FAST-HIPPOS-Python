# Installation

FAST-HIPPOS installs into one folder of its own, with its own Python. It needs no administrator rights and does not
touch other Python installations. You need about 1 GB of disk space, plus 1 to 5 GB for Cellpose. For Cellpose, a
computer with an NVIDIA graphics card (GPU) is preferable.

## Download

Everything is on the [latest release](https://github.com/Jalink-lab/FAST-HIPPOS-Python/releases/latest) page on GitHub.
Under **Assets** at the bottom:

- **Windows**: `FAST-HIPPOS-Setup-<version>.exe`.
- **macOS and Linux**: **Source code (zip)** or **Source code (tar.gz)**; unpack it.

## Windows

1. Download `FAST-HIPPOS-Setup-<version>.exe` and run it.
2. Windows may warn that the publisher is unknown, because the setup is not signed: choose **More info** and
   **Run anyway**.
3. Follow the steps. The setup downloads Python and the packages and shows what it is doing; this takes a few
   minutes. Everything is also written to `install-output.log` in the installation folder.

Start FAST-HIPPOS from the start menu, the desktop shortcut if you chose one, or `FAST-HIPPOS.exe` in the installation
folder (`%LOCALAPPDATA%\FAST-HIPPOS`). It opens in your web browser. Then [set up Cellpose](#cellpose).

Running the setup when FAST-HIPPOS is installed already offers **Update it** or **Remove it**.

Silent installation, for example for several computers:
`FAST-HIPPOS-Setup-<version>.exe /VERYSILENT /CELLPOSE=3` (`3`, `4`, `3,4` or `none`).

## macOS and Linux

In a terminal, in the folder with the downloaded program:

```bash
sh install.sh
```

The script fetches [uv](https://docs.astral.sh/uv/) (a small tool that installs Python and packages) and adds
FAST-HIPPOS to Applications (macOS) or the applications menu (Linux). It installs in `~/FAST-HIPPOS`.

## Cellpose

FAST-HIPPOS uses [Cellpose](https://www.cellpose.org/) to find the cells. Cellpose 3 (models such as `cyto3`) and
Cellpose 4 (Cellpose-SAM, model `cpsam`) are different programs that cannot be installed together, so each has its own
environment. You set them up in the window, under **Cell segmentation → Cellpose on this computer**.

FAST-HIPPOS looks for Cellpose in the usual places (conda, mamba, uv and venv folders). **Search all drives** looks
through all local hard drives, which can take several minutes. Searching only reads folder and file names. An
installation that is found is never used by itself. For each version you choose:

- **Use this installation**: run Cellpose from the environment that was found. Nothing in it is changed.
- **Install with FAST-HIPPOS**: download Cellpose with PyTorch into the FAST-HIPPOS folder. With an NVIDIA graphics
  card this takes about 4.5 GB, otherwise about 1.1 GB. You can keep working meanwhile.
- **Choose my own python.exe…**: point to any environment with that Cellpose version.

The row then shows where Cellpose comes from, its version and whether the GPU is used. **Change** makes another choice.

!!! info "Without Cellpose or a GPU"
    Without Cellpose you can still segment with a threshold (*Segmentation → Threshold + watershed*), or use a label
    image made elsewhere, e.g. in Fiji (*Segmentation → Existing label image*). Cellpose also runs on the processor,
    only much slower: minutes instead of seconds per image. Everything else in FAST-HIPPOS does not need a GPU.

## Updates

FAST-HIPPOS asks GitHub once a day whether there is a newer version; nothing else is sent. When there is one, a bar at
the top of the window offers it, with **What's new / update**, **Later** (for a week) and **Skip this version**.

**Check for updates**, next to the version at the top of the window, checks at any time and installs the update. There
you can also switch the daily check off. During an update FAST-HIPPOS closes, updates itself and comes back in the same
browser tab. Your settings, results and Cellpose stay as they are. An update waits until a running analysis has
finished.

## Removing

Windows: *Settings → Apps → FAST-HIPPOS → Uninstall*. macOS and Linux: remove the installation folder (`~/FAST-HIPPOS`
unless you chose another) and the app in `~/Applications` or the menu entry. This also removes a Cellpose installed
with FAST-HIPPOS, but not your own environments or your results. The remembered settings are in `.fast_hippos` in your
user folder.

## From source (for developers)

```powershell
git clone https://github.com/Jalink-lab/FAST-HIPPOS-Python.git
cd FAST-HIPPOS-Python
uv sync
uv run fast-hippos-cli shortcut
```

Update with `git pull` and `uv sync`. Keep the environment out of OneDrive, SURFdrive or Dropbox: set
`$env:UV_PROJECT_ENVIRONMENT = "C:\envs\FAST-HIPPOS"` before each `uv` command if the project folder is synchronized. A
copy from source can use a Cellpose that is found or chosen, but installs neither Cellpose nor updates from the window.
