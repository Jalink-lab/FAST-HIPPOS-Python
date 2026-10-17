# Installation

FAST-HIPPOS runs on Windows, macOS and Linux; these instructions are for Windows, where it is used most. You need
about 2 GB of disk space, and for Cellpose preferably a computer with an NVIDIA graphics card (GPU).

## 1. Install uv

FAST-HIPPOS is a Python program. [uv](https://docs.astral.sh/uv/) installs it, with the right Python version and
everything it needs, in a folder of its own, without touching other Python installations.

Open **PowerShell** (Start menu → type *PowerShell*) and run:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close PowerShell and open it again, so that it finds `uv`.

## 2. Download FAST-HIPPOS

=== "With git"

    ```powershell
    cd C:\Programs                 # or any folder you like
    git clone https://github.com/Jalink-lab/FAST-HIPPOS-Python.git
    cd FAST-HIPPOS-Python
    ```

    With git, `git pull` later gets the newest version.

=== "Without git"

    On [the GitHub page](https://github.com/Jalink-lab/FAST-HIPPOS-Python), click *Code → Download ZIP*, unpack it
    (for instance to `C:\Programs\FAST-HIPPOS-Python`) and go to that folder in PowerShell:

    ```powershell
    cd C:\Programs\FAST-HIPPOS-Python
    ```

!!! tip "Not in OneDrive, SURFdrive or Dropbox"
    Python environments consist of thousands of small files, which synchronization programs handle badly. Put
    FAST-HIPPOS in a local folder, or, if it must be in a synchronized folder, keep its environment out of it: run
    `$env:UV_PROJECT_ENVIRONMENT = "C:\envs\FAST-HIPPOS"` before each `uv` command below.

## 3. Install

```powershell
uv sync --extra lif
```

This creates the environment (in the subfolder `.venv`) with all that FAST-HIPPOS needs, including support for Leica
`.lif` files. It takes a few minutes the first time.

Then put a shortcut with the FAST-HIPPOS logo on the desktop:

```powershell
uv run fast-hippos-cli shortcut
```

Double-click it: FAST-HIPPOS opens in your web browser. Continue with [your first analysis](first-analysis.md).

## 4. Cellpose

FAST-HIPPOS uses [Cellpose](https://www.cellpose.org/) to find the cells. Cellpose 3 (models such as `cyto3`) and
Cellpose 4 (Cellpose-SAM, model `cpsam`) are different programs that cannot be installed together, so FAST-HIPPOS can
use them from environments of their own. Choose one of these:

=== "Cellpose already installed"

    If Cellpose is installed in another environment on the computer, tell FAST-HIPPOS where its `python.exe` is: in
    the window under *Cell segmentation → Advanced settings → Cellpose 3 environment (python.exe)* (or *Cellpose 4 environment*). The
    window checks it at once and shows the Cellpose version and whether the GPU is used.

=== "Install Cellpose in FAST-HIPPOS"

    ```powershell
    uv sync --extra lif --extra cellpose3    # or: --extra cellpose4
    ```

    For the GPU, PyTorch must be installed with CUDA support; see the
    [Cellpose installation instructions](https://cellpose.readthedocs.io/en/latest/installation.html).

=== "No Cellpose"

    Without Cellpose you can still segment with a threshold (*Segmentation → Threshold + watershed*), or use a label image
    made elsewhere, e.g. in Fiji (*Segmentation → Existing label image*).

!!! info "Without a GPU"
    Cellpose also runs on the processor, only much slower: minutes instead of seconds per image. Everything else in
    FAST-HIPPOS does not need a GPU.

## Updating

```powershell
cd C:\Programs\FAST-HIPPOS-Python
git pull          # or download the ZIP again
uv sync --extra lif
```

Your settings are kept (they are stored in your user folder, in `.fast_hippos`).
