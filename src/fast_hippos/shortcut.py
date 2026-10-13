"""Desktop shortcut (Windows) that starts the FAST-HIPPOS GUI, with the logo as icon."""

from __future__ import annotations

import subprocess
import sys
from importlib import resources
from pathlib import Path

from PIL import Image

from .gui import STATE_DIR


def make_icon(path: Path) -> Path:
    src = resources.files("fast_hippos").joinpath("templates", "icon.png")  # 256 px
    with resources.as_file(src) as f:
        img = Image.open(f).convert("RGBA")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


def gui_executable() -> Path:
    """fast-hippos.exe (the GUI without console) next to the interpreter of this environment."""
    exe = Path(sys.executable).with_name("fast-hippos.exe")
    if not exe.exists():
        raise FileNotFoundError(f"{exe} not found: reinstall FAST-HIPPOS in this environment (uv sync)")
    return exe


def create_desktop_shortcut(name: str = "FAST-HIPPOS") -> Path:
    if sys.platform != "win32":
        raise OSError("Desktop shortcuts are only made on Windows")
    icon = make_icon(STATE_DIR / "fast_hippos.ico")
    exe = gui_executable()
    # the Desktop may be redirected (e.g. to OneDrive); ask Windows where it is
    script = (
        "$d = [Environment]::GetFolderPath('Desktop');"
        f"$l = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d '{name}.lnk'));"
        f"$l.TargetPath = '{exe}'; $l.WorkingDirectory = '{Path.home()}'; $l.IconLocation = '{icon},0';"
        "$l.Description = 'FAST-HIPPOS: single-cell FLIM traces and hit identification'; $l.Save();"
        "Write-Output $l.FullName"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise OSError(f"Could not create the shortcut: {r.stderr.strip()}")
    return Path(r.stdout.strip())
