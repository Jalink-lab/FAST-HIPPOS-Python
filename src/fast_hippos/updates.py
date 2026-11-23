"""Updates: is there a newer version on GitHub, and installing it.

The check asks the GitHub API for the releases of the repository (nothing else is sent), at most once a day in the
background, and whenever the user presses "Check for updates". The repository also holds the 'example-data' release,
so only releases with the Windows setup attached count.

The update downloads the release's source archive into the installation folder and runs its
`installer/install.py --update` detached. That script waits until this program has stopped, shows its progress on the
window's port (the browser tab follows it), installs, and starts the new version. Settings and results are not
touched, and the Cellpose environments stay as they are.

Only an installation made by the setup or install.sh can update itself (it has `bin/uv` and a `python` folder); a
developer's checkout is updated with git.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from . import __version__

REPOSITORY = "Jalink-lab/FAST-HIPPOS-Python"
ASSET = re.compile(r"FAST-HIPPOS-Setup-.+\.exe$")
DAY = 24 * 3600
CHECK_EVERY = DAY  # the background check; the button checks at any time
MARKER = "in-progress"  # in <installation>/update while an update runs: holds the port that shows its progress
_RANK = {"dev": 0, "a": 1, "b": 2, "rc": 3}


def releases_url() -> str:
    # FAST_HIPPOS_UPDATE_URL: for tests, a file:// or http:// URL with the same JSON as the GitHub API
    return os.environ.get("FAST_HIPPOS_UPDATE_URL") or f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=30"


def version_key(text: str) -> tuple:
    """Sortable version: 1.2.3.dev1 < 1.2.3a1 < 1.2.3b1 < 1.2.3rc1 < 1.2.3."""
    m = re.match(r"v?(\d+)\.(\d+)(?:\.(\d+))?(?:\.?(dev|a|b|rc)(\d*))?", str(text).strip())
    if not m:
        return (0,)
    return (int(m[1]), int(m[2]), int(m[3] or 0), _RANK[m[4]] if m[4] else 9, int(m[5] or 0))


def is_newer(version: str, current: str = __version__) -> bool:
    return version_key(version) > version_key(current)


def pick_latest(found: object) -> dict | None:
    """The newest published release with the setup attached, from the JSON of the GitHub API."""
    best = None
    for rel in found if isinstance(found, list) else []:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        setup = next((a.get("browser_download_url") for a in rel.get("assets", []) if ASSET.search(a.get("name", ""))), None)
        if not setup:
            continue  # for instance the example data
        info = {"version": str(rel.get("tag_name", "")).lstrip("v"), "notes": rel.get("body") or "",
                "page": rel.get("html_url", ""), "setup": setup, "source": rel.get("zipball_url", ""),
                "date": (rel.get("published_at") or "")[:10]}
        if best is None or version_key(info["version"]) > version_key(best["version"]):
            best = info
    return best


def latest(timeout: float = 15) -> dict | None:
    req = urllib.request.Request(releases_url(), headers={"Accept": "application/vnd.github+json",
                                                          "User-Agent": "FAST-HIPPOS-update-check"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return pick_latest(json.loads(r.read().decode("utf-8")))


# ---- the installation

def layout() -> dict | None:
    """The installation this program runs from: its folder and uv. None for a developer's checkout."""
    target = Path(sys.prefix).resolve().parent
    win = sys.platform == "win32"
    uv = target / "bin" / ("uv.exe" if win else "uv")
    if not uv.is_file() or not (target / "python").is_dir():
        return None
    return {"target": target, "uv": uv, "windows": win}


def install_env(target: Path) -> dict:
    env = {**os.environ, "UV_PYTHON_INSTALL_DIR": str(target / "python"), "UV_CACHE_DIR": str(target / "cache"),
           "UV_NO_PROGRESS": "1", "PYTHONIOENCODING": "utf-8"}
    env.pop("VIRTUAL_ENV", None)
    return env


def running_update() -> str | None:
    """The URL that shows an update in progress, if one runs (a second start must not touch the files)."""
    where = layout()
    if where is None:
        return None
    try:
        port = int((where["target"] / "update" / MARKER).read_text().strip())
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/update-progress", timeout=1):
            return f"http://127.0.0.1:{port}/"
    except (OSError, ValueError):
        return None


def _download(url: str, dest: Path, progress) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "FAST-HIPPOS-update"})
    with urllib.request.urlopen(req, timeout=60) as r, dest.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 16):
            f.write(chunk)
            done += len(chunk)
            progress(done, total)


def start_install(info: dict, port: int, progress) -> None:
    """Download and unpack the new version, then hand over to its install.py (detached). The caller then stops
    this program."""
    where = layout()
    if where is None:
        raise RuntimeError("This FAST-HIPPOS was not installed with the setup or install.sh: update it with git.")
    target, work = where["target"], where["target"] / "update"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    archive = work / "source.zip"
    _download(info["source"], archive, progress)
    with zipfile.ZipFile(archive) as z:
        z.extractall(work / "source")
    script = next((work / "source").glob("*/installer/install.py"), None)
    if script is None:
        raise RuntimeError("The downloaded version has no installer/install.py.")
    cmd = [str(where["uv"]), "run", "--no-project", "--python", "3.12", str(script), "--target", str(target),
           "--uv", str(where["uv"]), "--update", "--wait", str(os.getpid()), "--serve", str(port)]
    if not where["windows"]:
        cmd.append("--shortcut")
    (work / MARKER).write_text(str(port))
    out = (work / "update-output.log").open("wb")
    kwargs = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
              if where["windows"] else {"start_new_session": True})
    try:
        subprocess.Popen(cmd, cwd=str(work), env=install_env(target), stdout=out, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, close_fds=True, **kwargs)
    except OSError:
        (work / MARKER).unlink(missing_ok=True)
        raise


# ---- what the window asks for

class Updater:
    """The update state of the window. The user's choices are kept in `path` (updates.json)."""

    def __init__(self, path: Path):
        self.path = path
        self.data = {"check": True, "last_check": 0, "snooze_until": 0, "skip": "", "latest": None}
        try:
            self.data.update(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        self.lock = threading.Lock()
        self.checking = False
        self.error = ""
        self.installing: dict = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        except OSError:
            pass

    def due(self) -> bool:
        return bool(self.data["check"]) and time.time() - float(self.data.get("last_check") or 0) > CHECK_EVERY

    def offer(self) -> bool:
        """Whether the window should offer the newer version by itself (not skipped, not snoozed)."""
        new = self.data.get("latest")
        return bool(self.data["check"] and new and is_newer(new["version"]) and new["version"] != self.data.get("skip")
                    and time.time() >= float(self.data.get("snooze_until") or 0))

    def info(self) -> dict:
        d = self.data
        new = d.get("latest")
        return {"current": __version__, "latest": new, "newer": bool(new and is_newer(new["version"])), "offer": self.offer(),
                "check": bool(d["check"]), "last_check": d.get("last_check") or 0, "checking": self.checking,
                "error": self.error, "can_install": layout() is not None, "repository": REPOSITORY,
                "installing": self.installing}

    def check(self) -> dict:
        """Ask GitHub now. A failure (no internet) is reported, and the last answer stays."""
        with self.lock:
            if self.checking:
                return self.info()
            self.checking = True
        try:
            found = latest()
            self.data.update(latest=found, last_check=time.time())
            self.error = ""
            self._save()
        except Exception as e:  # noqa: BLE001 - shown in the window
            self.error = f"Could not reach GitHub ({type(e).__name__})."
        finally:
            self.checking = False
        return self.info()

    def check_if_due(self) -> dict:
        if self.due() and not self.checking:
            threading.Thread(target=self.check, daemon=True).start()
        return self.info()

    def choice(self, action: str) -> dict:
        new = self.data.get("latest") or {}
        if action == "later":
            self.data["snooze_until"] = time.time() + 7 * DAY
        elif action == "skip":
            self.data["skip"] = new.get("version", "")
        elif action in ("auto_on", "auto_off"):
            self.data["check"] = action == "auto_on"
        else:
            raise ValueError(f"Unknown choice: {action}")
        self._save()
        return self.info()

    def start(self, port: int, busy: bool, stop_program) -> dict:
        """Install the newer version; `stop_program` is called once the installer has taken over."""
        new = self.data.get("latest")
        if busy:
            raise ValueError("An analysis is running. Update when it has finished.")
        if not new or not is_newer(new["version"]):
            raise ValueError("There is no newer version.")
        if layout() is None:
            raise ValueError("This FAST-HIPPOS was not installed with the setup or install.sh: update it with git.")
        if self.installing.get("state") == "downloading":
            return self.info()
        self.installing = {"state": "downloading", "permille": 0, "version": new["version"]}

        def progress(done: int, total: int) -> None:
            self.installing["permille"] = int(1000 * done / total) if total else 0

        def work() -> None:
            try:
                start_install(new, port, progress)
                self.installing["state"] = "restarting"
                time.sleep(0.8)  # the page hears about it before the program stops
                stop_program()
            except Exception as e:  # noqa: BLE001 - shown in the window; the program keeps running
                self.installing = {"state": "failed", "error": str(e)}

        threading.Thread(target=work, daemon=True).start()
        return self.info()
