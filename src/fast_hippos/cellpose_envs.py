"""Cellpose on this computer: installed with FAST-HIPPOS, or found in the user's own environments.

Searching only looks at folder and file names (it starts no Python and changes nothing). The quick search covers the
places where environments usually are; "Search all drives" walks the fixed drives. What is found is only offered: the
window asks whether to use it or to install Cellpose with FAST-HIPPOS.

Installed copies live next to the program, in `<installation>/cellpose3-env` and `cellpose4-env`.
"""

from __future__ import annotations

import json
import os
import re
import string
import subprocess
import sys
import threading
from importlib import metadata
from pathlib import Path

from . import updates

CONDA_NAMES = ("miniconda3", "anaconda3", "miniforge3", "mambaforge", "micromamba", ".conda", ".mamba")
ENV_FOLDERS = (".virtualenvs", "envs", "venvs", ".venvs")
SKIP_DIRS = {"$recycle.bin", "system volume information", "windows", "node_modules", ".git", "__pycache__",
             "windowsapps", "temp", "tmp", "recovery", "perflogs"}
_DIST = re.compile(r"^cellpose-(\d+(?:\.\d+)*)[^/\\]*\.dist-info$", re.IGNORECASE)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def env_python(env: Path) -> Path | None:
    """The Python of an environment folder (conda: python.exe in the folder; venv: Scripts\\python.exe; bin/python)."""
    for rel in ("python.exe", "Scripts/python.exe", "bin/python"):
        if (env / rel).is_file():
            return env / rel
    return None


def cellpose_version(env: Path) -> str | None:
    """The Cellpose version in an environment folder, from its package metadata."""
    sites = [env / "Lib" / "site-packages", *(env / "lib").glob("python*/site-packages")]
    for site in sites:
        try:
            for entry in os.scandir(site):
                m = _DIST.match(entry.name)
                if m:
                    return m[1]
        except OSError:
            continue
    return None


def bundled(version: int) -> str | None:
    """The Python of the Cellpose installed with FAST-HIPPOS, if it is there."""
    where = updates.layout()
    if where is None:
        return None
    env = where["target"] / f"cellpose{version}-env"
    python = env_python(env)
    return str(python) if python and cellpose_version(env) else None


def installed_major() -> int | None:
    """The Cellpose version in FAST-HIPPOS's own environment (from the metadata: importing it takes seconds)."""
    try:
        return int(metadata.version("cellpose").split(".")[0])
    except (metadata.PackageNotFoundError, ValueError):
        return None


def _is_env(path: Path) -> bool:
    return (path / "pyvenv.cfg").is_file() or (path / "conda-meta").is_dir()


def usual_places(home: Path | None = None) -> list[Path]:
    """Folders that may be environments, in the places where they usually are."""
    home = home or Path.home()
    bases = [home, home / "AppData" / "Local", home / "AppData" / "Local" / "Continuum"]
    if sys.platform == "win32":
        bases += [Path(os.environ.get("ProgramData", r"C:\ProgramData")), Path(r"C:\\")]
    else:
        bases += [Path("/opt")]
    out: list[Path] = []
    for base in bases:
        for name in CONDA_NAMES:
            out.append(base / name)
            out += _children(base / name / "envs")
    conda_list = home / ".conda" / "environments.txt"  # conda's own list of its environments
    try:
        out += [Path(line.strip()) for line in conda_list.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        pass
    for base in (home, Path(r"C:\\") if sys.platform == "win32" else Path("/opt")):
        for name in ENV_FOLDERS:
            out += _children(base / name)
    for parent in (home, home / "Documents", home / "projects", Path(r"C:\PythonProjects")):
        for child in _children(parent):
            out += [child, child / ".venv", child / "venv", child / "env"]
    return out


def _children(folder: Path) -> list[Path]:
    try:
        return [Path(e.path) for e in os.scandir(folder) if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []


def fixed_drives() -> list[Path]:
    """The local hard drives (no network shares, USB sticks or optical drives)."""
    if sys.platform != "win32":
        return [Path.home()]
    import ctypes

    return [Path(f"{d}:\\") for d in string.ascii_uppercase
            if ctypes.windll.kernel32.GetDriveTypeW(f"{d}:\\") == 3]  # DRIVE_FIXED


def walk_for_envs(roots: list[Path], cancelled, progress=None):
    """Yield every environment below `roots`. Does not go into environments, system folders or links."""
    stack = list(roots)
    seen = 0
    while stack and not cancelled():
        folder = stack.pop()
        seen += 1
        if progress and seen % 500 == 0:
            progress(seen, str(folder))
        if _is_env(folder):
            yield folder
            continue
        try:
            with os.scandir(folder) as it:
                for e in it:
                    if e.name.lower() not in SKIP_DIRS and e.is_dir(follow_symlinks=False):
                        stack.append(Path(e.path))
        except OSError:
            continue


class CellposeSetup:
    """What the Cellpose part of the window shows: installed copies, what was found, and a running search or install."""

    def __init__(self, state_dir: Path):
        self.cache = state_dir / "cellpose_found.json"
        self.lock = threading.Lock()
        self.found: dict[str, dict] = {}
        try:
            self.found = {f["python"]: f for f in json.loads(self.cache.read_text(encoding="utf-8"))
                          if Path(f["python"]).is_file()}
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self.search_state: dict = {"running": False, "full": False, "done": False, "folders": 0, "where": ""}
        self._cancel = False
        self.install_state: dict = {"running": False}
        self._progress_file: Path | None = None

    # ---- searching

    def _add(self, env: Path) -> None:
        where = updates.layout()
        if where and env.resolve().is_relative_to(where["target"]):
            return  # the copies of this installation are shown as installed
        version, python = cellpose_version(env), env_python(env)
        if version and python:
            with self.lock:
                self.found[str(python)] = {"python": str(python), "version": version, "major": int(version.split(".")[0])}

    def _save(self) -> None:
        try:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            self.cache.write_text(json.dumps(list(self.found.values()), indent=1), encoding="utf-8")
        except OSError:
            pass

    def search(self, full: bool = False) -> dict:
        with self.lock:
            already = self.search_state["running"]
            if not already:
                self.search_state = {"running": True, "full": full, "done": False, "folders": 0, "where": ""}
                self._cancel = False
        if already:
            return self.state()

        def progress(n: int, where: str) -> None:
            self.search_state.update(folders=n, where=where)

        def work() -> None:
            try:
                if full:
                    for env in walk_for_envs(fixed_drives(), lambda: self._cancel, progress):
                        self._add(env)
                else:
                    for env in dict.fromkeys(usual_places()):
                        if self._cancel:
                            break
                        if env.is_dir() and _is_env(env):
                            self._add(env)
                self._save()
            finally:
                self.search_state.update(running=False, done=True, cancelled=self._cancel)

        threading.Thread(target=work, daemon=True).start()
        return self.state()

    def cancel_search(self) -> dict:
        self._cancel = True
        return self.state()

    # ---- installing

    def install(self, version: int) -> dict:
        where = updates.layout()
        if version not in (3, 4):
            raise ValueError("Cellpose 3 or 4")
        if where is None:
            raise ValueError("Installing Cellpose needs an installation made with the setup or install.sh.")
        script = where["target"] / "program" / "installer" / "install.py"
        if not script.is_file():
            raise ValueError(f"Not found: {script}")
        with self.lock:
            if self.install_state.get("running"):
                raise ValueError("Cellpose is being installed already.")
            self._progress_file = where["target"] / f"cellpose{version}-progress.txt"
            self._progress_file.unlink(missing_ok=True)
            self.install_state = {"running": True, "version": version, "permille": 0, "status": "Starting", "lines": []}
        cmd = [str(where["uv"]), "run", "--no-project", "--python", "3.12", str(script), "--target", str(where["target"]),
               "--uv", str(where["uv"]), "--cellpose", str(version), "--cellpose-only", "--progress", str(self._progress_file)]

        def work() -> None:
            try:
                r = subprocess.run(cmd, cwd=str(where["target"]), env=updates.install_env(where["target"]),
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   creationflags=NO_WINDOW, check=False)
                self._read_progress()
                ok = r.returncode == 0 and bundled(version) is not None
                self.install_state.update(running=False, done=ok, failed=not ok)
                if not ok:
                    self.install_state["error"] = (r.stdout + r.stderr).strip()[-1500:] or "The installation stopped."
            except Exception as e:  # noqa: BLE001 - shown in the window
                self.install_state.update(running=False, failed=True, error=f"{type(e).__name__}: {e}")

        threading.Thread(target=work, daemon=True).start()
        return self.state()

    def _read_progress(self) -> None:
        """install.py writes: per mille, the step, the number of messages, then the last messages."""
        try:
            lines = self._progress_file.read_text(encoding="ascii", errors="replace").splitlines()
            self.install_state.update(permille=int(lines[0]), status=lines[1], lines=lines[3:][-8:])
        except (OSError, ValueError, IndexError, AttributeError):
            pass

    # ---- for the window

    def state(self) -> dict:
        if self.install_state.get("running"):
            self._read_progress()
        with self.lock:
            found = sorted(self.found.values(), key=lambda f: (f["major"], f["python"].lower()))
        return {"can_install": updates.layout() is not None, "bundled": {"3": bundled(3), "4": bundled(4)}, "found": found,
                "search": dict(self.search_state), "install": dict(self.install_state)}
