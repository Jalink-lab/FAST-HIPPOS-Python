"""Install FAST-HIPPOS and, if asked, Cellpose; the same steps on Windows, macOS and Linux.

Run by the installers (setup.exe on Windows, install.sh on macOS and Linux, install.bat for developers), and by the
window when the user installs Cellpose or an update, as
    uv run --no-project --python 3.12 installer/install.py [options]
It needs only the standard library and uv.

Everything goes into one folder (--target): the program environment (.venv), the Cellpose environments (cellpose3-env,
cellpose4-env: the two versions cannot live together), the Python versions and the download cache. Removing that
folder removes the program. Settings (~/.fast_hippos) and results are never touched.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent  # the program: pyproject.toml, uv.lock, src
WINDOWS, MAC = sys.platform == "win32", sys.platform == "darwin"
# versions tested together
TORCH = ["torch==2.6.0", "torchvision==0.21.0"]
CELLPOSE = {3: ["cellpose==3.1.1.3"], 4: ["cellpose==4.2.1.1"]}
LOG: Path | None = None
# disk space in GB once installed
SIZE_PROGRAM = 0.5
SIZE_TORCH = {"gpu": 4.4, "cpu": 1.0}
SIZE_CELLPOSE = 0.1


class Progress:
    """For the Windows setup (--progress FILE): how far the installation is, the current step and the messages,
    in a small text file that the setup window reads every half second. Line 1: per mille done; line 2: the
    step; line 3: the number of messages so far; then the last messages.

    Steps count by their size. Within a step uv tells what it downloads ("Downloading torch (2.4GiB)", then
    "Downloaded torch" when done, as run() writes it); a download in progress is estimated from the time it takes."""

    SPEED = 8e6  # bytes per second assumed for a download in progress, until one finished

    def __init__(self, path: Path | None):
        self.path, self.lines, self.count = path, [], 0
        self.weights, self.step, self.status = [], -1, "Starting"
        self.files: dict[str, float] = {}  # file being downloaded -> bytes
        self.done_bytes = self.total_bytes = 0.0
        self.since, self.speed = time.time(), self.SPEED
        self.final = False
        if path:
            import threading
            threading.Thread(target=self._tick, daemon=True).start()

    def plan(self, weights: list[float]) -> None:
        self.weights = [max(w, 0.01) for w in weights]

    def next(self, status: str) -> None:
        self.step += 1
        self.status = f"Step {self.step + 1} of {len(self.weights)}: {status}"
        self.files.clear()
        self.done_bytes = self.total_bytes = 0.0
        self.since = time.time()
        self.write()

    def line(self, text: str) -> None:
        self.lines.append(text)
        self.count += 1
        del self.lines[:-300]
        m = re.match(r"Downloading (\S+) \(([\d.]+)\s*([KMG])iB\)", text)
        if m:
            size = float(m[2]) * {"K": 2**10, "M": 2**20, "G": 2**30}[m[3]]
            self.files[m[1]] = size
            self.total_bytes += size
            self.since = time.time()
        m = re.match(r"\s+Downloaded (\S+)$", text)
        if m and m[1] in self.files:
            size = self.files.pop(m[1])
            self.done_bytes += size
            seconds = time.time() - self.since
            if size > 50e6 and seconds > 2:
                self.speed = max(self.speed, size / seconds)

    def permille(self) -> int:
        if self.final:
            return 1000
        if not self.weights or self.step < 0:
            return 0
        part = 0.0
        if self.total_bytes:
            busy = sum(self.files.values())
            guess = min(0.95 * busy, (time.time() - self.since) * self.speed)
            part = 0.85 * (self.done_bytes + guess) / self.total_bytes
        if not self.files and self.total_bytes and self.done_bytes >= self.total_bytes:
            part = 0.9  # downloaded; installing
        total = sum(self.weights)
        return int(1000 * (sum(self.weights[:self.step]) + part * self.weights[self.step]) / total)

    def write(self) -> None:
        if not self.path:
            return
        text = "\n".join([str(self.permille()), self.status, str(self.count), *self.lines]) + "\n"
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(text, encoding="ascii", errors="replace")
            os.replace(tmp, self.path)
        except OSError:
            pass  # the setup is reading it: next time

    def done(self) -> None:
        self.final, self.status = True, "Ready"
        self.write()

    def _tick(self) -> None:
        while True:
            time.sleep(0.5)
            self.write()


PROGRESS = Progress(None)


def say(text: str) -> None:
    print(text, flush=True)
    for line in text.strip("\n").splitlines() or [""]:
        PROGRESS.line(line)
    if LOG:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {text}\n")


def run(uv: str, *args: str, env: dict | None = None) -> None:
    cmd = [uv, *args]
    if LOG:
        with LOG.open("a", encoding="utf-8") as f:
            f.write("$ " + " ".join(cmd) + "\n")
    # uv's messages go through say(): to the console, the log and the setup window
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env={**os.environ, **(env or {})},
                         text=True, encoding="utf-8", errors="replace", bufsize=1)
    for line in p.stdout:
        line = re.sub(r"\x1b\[[0-9;]*m", "", line.rstrip())
        say(re.sub(r"^(\s+)Downloading (\S+)$", r"\1Downloaded \2", line))  # uv's "done" line reads oddly
    if p.wait():
        raise SystemExit(f"\nThis step failed (exit code {p.returncode}): {' '.join(cmd)}\n"
                         "The messages above say why; an internet connection is needed.")


def python_of(env: Path) -> Path:
    return env / ("Scripts/python.exe" if WINDOWS else "bin/python")


def venv(uv: str, path: Path, python: str, env: dict) -> None:
    """An environment, unless it is there already (its python.exe may be in use by a running program). One that
    is only partly there (an uninstall while the program ran) is removed and made again."""
    if path.exists() and not healthy(path):
        say(f"Removing the incomplete environment {path}")
        shutil.rmtree(path, ignore_errors=True)
    if not python_of(path).is_file():
        run(uv, "venv", str(path), "--python", python, "--no-project", env=env)


def healthy(path: Path) -> bool:
    """Whether this environment's Python starts."""
    if not (python_of(path).is_file() and (path / "pyvenv.cfg").is_file()):
        return False
    try:
        return subprocess.run([str(python_of(path)), "-c", "import os, json"], check=False, capture_output=True,
                              timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def nvidia() -> bool:
    if MAC:
        return False
    try:
        return subprocess.run(["nvidia-smi", "-L"], check=False, capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _pe_end(data: bytes) -> int:
    """Where the program part of an .exe ends (what follows is appended data, such as uv's start script)."""
    import struct
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    sections, opt_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + opt_size
    end = max(struct.unpack_from("<II", data, table + 40 * i + 16)[1] + struct.unpack_from("<II", data, table + 40 * i + 16)[0]
              for i in range(sections))
    return end


def branded_launcher(src: Path, dst: Path, ico: Path) -> bool:
    """A copy of uv's launcher `src` with the icon of `ico` (Windows). Older uv launchers find their Python and
    script in data appended after the program part: that part is set aside while the icon is replaced, and
    appended again. Newer ones keep it in their resources, which stay (only the icon resources are added).
    Returns False (and leaves a plain copy) when the icon cannot be set."""
    import ctypes
    import struct
    data = src.read_bytes()
    end = _pe_end(data)
    dst.write_bytes(data)
    if not ico.is_file():
        return False
    appended = data[end:] if end < len(data) else b""
    try:
        icon = ico.read_bytes()
        _, kind, count = struct.unpack_from("<HHH", icon, 0)
        if kind != 1:
            return False
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.BeginUpdateResourceW.restype = ctypes.c_void_p
        k32.BeginUpdateResourceW.argtypes = [ctypes.c_wchar_p, ctypes.c_bool]
        k32.UpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ushort,
                                        ctypes.c_char_p, ctypes.c_uint]
        k32.EndUpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        dst.write_bytes(data[:end] if appended else data)  # the program part only; the rest is appended below
        h = k32.BeginUpdateResourceW(str(dst), False)
        if not h:
            raise OSError(ctypes.get_last_error())
        group = struct.pack("<HHH", 0, 1, count)
        for i in range(count):
            w, hh, colors, res, planes, bits, size, offset = struct.unpack_from("<BBBBHHII", icon, 6 + 16 * i)
            k32.UpdateResourceW(h, 3, 100 + i, 0, icon[offset:offset + size], size)  # RT_ICON
            group += struct.pack("<BBBBHHIH", w, hh, colors, res, planes, bits, size, 100 + i)
        for name in (1, 101):  # the group icon that Windows shows: the first one, by number
            k32.UpdateResourceW(h, 14, name, 0, group, len(group))  # RT_GROUP_ICON
        if not k32.EndUpdateResourceW(h, False):
            raise OSError(ctypes.get_last_error())
        if appended:
            with dst.open("ab") as f:
                f.write(appended)
        return True
    except (OSError, ValueError, AttributeError, struct.error) as e:
        say(f"  (the program icon could not be set: {e})")
        dst.write_bytes(data)
        return False


def shortcuts(target: Path, desktop: bool, menu: bool = True) -> None:
    exe = python_of(target / ".venv").parent / ("fast-hippos.exe" if WINDOWS else "fast-hippos")
    icons = target / "icons"  # kept with the program: the folder the installer ran from may be removed later
    icons.mkdir(exist_ok=True)
    for name in ("FAST-HIPPOS.ico", "FAST-HIPPOS.icns", "logo-512.png"):
        if (HERE / name).is_file():
            shutil.copy2(HERE / name, icons / name)
    if WINDOWS and exe.is_file():  # "FAST-HIPPOS.exe" in the program folder, with the logo as its icon
        launcher = target / "FAST-HIPPOS.exe"
        if branded_launcher(exe, launcher, icons / "FAST-HIPPOS.ico"):
            say(f"Made {launcher}")
        exe = launcher
    if not menu:
        return
    if WINDOWS:
        places = ["[Environment]::GetFolderPath('Programs')"] + (["[Environment]::GetFolderPath('Desktop')"] if desktop else [])
        for place in places:
            ps = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine({place}, 'FAST-HIPPOS.lnk')); "
                  f"$s.TargetPath = '{exe}'; $s.WorkingDirectory = '{target}'; $s.Description = 'FAST-HIPPOS'; "
                  f"$s.IconLocation = '{icons / 'FAST-HIPPOS.ico'}'; $s.Save()")
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], check=False)
    elif MAC:  # a small app in ~/Applications that starts the program (made here, so macOS does not block it)
        app = Path.home() / "Applications" / "FAST-HIPPOS.app" / "Contents"
        (app / "MacOS").mkdir(parents=True, exist_ok=True)
        (app / "Resources").mkdir(exist_ok=True)
        if (icons / "FAST-HIPPOS.icns").is_file():
            shutil.copy2(icons / "FAST-HIPPOS.icns", app / "Resources" / "FAST-HIPPOS.icns")
        start = app / "MacOS" / "FAST-HIPPOS"
        start.write_text(f'#!/bin/sh\nexec "{exe}"\n', encoding="utf-8")
        start.chmod(0o755)
        (app / "Info.plist").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
            "<key>CFBundleName</key><string>FAST-HIPPOS</string>"
            "<key>CFBundleExecutable</key><string>FAST-HIPPOS</string>"
            "<key>CFBundleIconFile</key><string>FAST-HIPPOS</string>"
            "<key>CFBundleIdentifier</key><string>nl.nki.fast-hippos</string>"
            "<key>CFBundlePackageType</key><string>APPL</string></dict></plist>\n", encoding="utf-8")
        say(f"Made {app.parent}")
    else:
        share = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        apps = share / "applications"
        apps.mkdir(parents=True, exist_ok=True)
        icon = str(icons / "logo-512.png")
        if (icons / "logo-512.png").is_file():  # in the icon theme too, where every desktop looks for it
            themed = share / "icons" / "hicolor" / "512x512" / "apps"
            themed.mkdir(parents=True, exist_ok=True)
            shutil.copy2(icons / "logo-512.png", themed / "fast-hippos.png")
            icon = "fast-hippos"
        (apps / "fast-hippos.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=FAST-HIPPOS\nComment=FLIM traces and hit identification\n"
            f'Exec="{exe}"\nIcon={icon}\nTerminal=false\nCategories=Science;Education;\n'
            "StartupWMClass=FAST-HIPPOS\n", encoding="utf-8")
        say(f"Made {apps / 'fast-hippos.desktop'}")


# ---- updating (installer --update, started by the program; see fast_hippos/updates.py)

UPDATE: dict = {}
APP_ID = "{A8EDC50D-8553-4561-9EB0-0947573A722E}_is1"  # FAST-HIPPOS.iss AppId: the entry under Apps
UPDATING_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>FAST-HIPPOS (updating)</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;font:15px system-ui,
sans-serif;background:#f4f5f7;color:#333}@media(prefers-color-scheme:dark){body{background:#1d1f23;color:#ddd}}
main{width:min(640px,92vw)}h2{font-weight:600}.bar{height:10px;border-radius:5px;background:#0002;overflow:hidden}
.bar div{height:100%;width:0;background:#5b3fe0;transition:width .4s}pre{font:12px Consolas,monospace;opacity:.75;
white-space:pre-wrap;max-height:40vh;overflow:auto}</style></head><body><main><h2>Updating FAST-HIPPOS</h2>
<p id="s">Starting</p><div class="bar"><div id="b"></div></div><pre id="l"></pre>
<p><small>Your settings, experiment and results stay as they are. The window comes back by itself.</small></p>
</main><script>
function back(){fetch("/",{cache:"no-store"}).then(r=>r.text()).then(t=>{if(t.indexOf("(updating)")<0)
location.reload();else setTimeout(back,1000);}).catch(()=>setTimeout(back,1000));}
(function poll(){fetch("/update-progress",{cache:"no-store"}).then(r=>r.json()).then(p=>{
document.getElementById("s").textContent=p.status;document.getElementById("b").style.width=p.permille/10+"%";
const l=document.getElementById("l");l.textContent=p.lines.join("\\n");l.scrollTop=l.scrollHeight;
setTimeout(poll,700);}).catch(()=>back());})();
</script></body></html>"""


def serve_progress(port: int) -> None:
    """While updating, the window's port shows the progress (the browser tab that started the update is
    there). Stopped just before the new version starts on the same port."""
    import http.server

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/update-progress"):
                body = json.dumps({"permille": PROGRESS.permille(), "status": PROGRESS.status,
                                   "lines": PROGRESS.lines[-14:]}).encode()
                kind = "application/json"
            elif self.path.startswith("/api/"):
                self.send_response(503)
                self.end_headers()
                return
            else:
                body, kind = UPDATING_PAGE.encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    class Server(http.server.ThreadingHTTPServer):
        allow_reuse_address = not WINDOWS
        daemon_threads = True

    import threading

    def go():
        for _ in range(120):  # the program still has the port until it has stopped
            try:
                UPDATE["server"] = Server(("127.0.0.1", port), Handler)
                break
            except OSError:
                time.sleep(0.5)
        else:
            return
        UPDATE["server"].serve_forever()

    threading.Thread(target=go, daemon=True).start()


def wait_for(pid: int, seconds: float = 120) -> None:
    """Until the program that started the update has stopped (its files are then free)."""
    end = time.time() + seconds
    if WINDOWS:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if h:
            k32.WaitForSingleObject(h, int(seconds * 1000))
            k32.CloseHandle(h)
    else:
        while time.time() < end:
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.3)
    time.sleep(1.0)  # its Cellpose processes stop with it


def program_version(source: Path) -> str:
    text = (source / "src" / "fast_hippos" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return m[1] if m else "?"


def set_windows_version(version: str) -> None:
    """The version shown under Apps (the setup wrote it at installation)."""
    if not WINDOWS:
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + APP_ID,
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
    except OSError:
        pass  # installed with install.bat or install.sh


def finish_update(target: Path, ok: bool) -> None:
    """Stop showing the progress and start FAST-HIPPOS (the new version, or after a failure the one that
    is there), on the same port; the browser tab reloads into it."""
    (target / "update" / "in-progress").unlink(missing_ok=True)
    if not ok:
        time.sleep(20)  # time to read what went wrong
    server = UPDATE.get("server")
    if server:
        server.shutdown()
        server.server_close()
    exe = target / "FAST-HIPPOS.exe" if WINDOWS else python_of(target / ".venv").parent / "fast-hippos"
    cmd = [str(exe), "--after-update"] + (["--port", str(UPDATE["port"])] if UPDATE.get("port") else [])
    if WINDOWS:
        subprocess.Popen(cmd, cwd=str(target), creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                         close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(cmd, cwd=str(target), start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv: list[str] | None = None) -> None:
    global LOG, PROGRESS
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--target", required=True, help="the folder to install in")
    p.add_argument("--uv", default=os.environ.get("UV") or shutil.which("uv") or "uv", help="the uv to use")
    p.add_argument("--cellpose", default="none", help="Cellpose versions to install: 3, 4, 3,4 or none")
    p.add_argument("--cellpose-only", action="store_true", help="only install Cellpose (the program is there already)")
    p.add_argument("--device", choices=["auto", "gpu", "cpu"], default="auto", help="PyTorch for the NVIDIA card or the processor")
    p.add_argument("--shortcut", action="store_true", help="add the program to the start menu / Applications")
    p.add_argument("--desktop", action="store_true", help="also put a shortcut on the desktop (Windows)")
    p.add_argument("--progress", help="a file in which the setup or the window follows the installation")
    p.add_argument("--update", action="store_true", help="update the installation in --target to this version "
                   "(started by the program: installs this version, then starts it)")
    p.add_argument("--wait", type=int, help="with --update: the process id of the FAST-HIPPOS to wait for")
    p.add_argument("--serve", type=int, help="with --update: show the progress on this port (the window's)")
    args = p.parse_args(argv)
    if args.cellpose not in ("none", "", "3", "4", "3,4", "4,3"):
        raise SystemExit(f"--cellpose must be 3, 4, 3,4 or none: {args.cellpose}")
    versions = sorted(int(v) for v in args.cellpose.split(",") if v in ("3", "4"))

    target = Path(args.target).resolve()
    target.mkdir(parents=True, exist_ok=True)
    LOG = target / "install.log"
    PROGRESS = Progress(Path(args.progress) if args.progress else None)
    # Python versions and the download cache inside the program folder: removing the folder removes all.
    env = {"UV_PYTHON_INSTALL_DIR": str(target / "python"), "UV_CACHE_DIR": str(target / "cache"),
           "UV_PYTHON_PREFERENCE": "only-managed"}
    gpu = nvidia() if args.device == "auto" else args.device == "gpu"
    size = SIZE_TORCH["gpu" if gpu else "cpu"] + SIZE_CELLPOSE
    weights = ([] if args.cellpose_only else [SIZE_PROGRAM]) + [size] * len(versions) + ([] if args.cellpose_only else [0.01])
    PROGRESS.plan(weights)
    steps, step = len(weights), 0

    def next_step(text, short):
        nonlocal step
        step += 1
        PROGRESS.next(short)
        say(f"\n[{step}/{steps}] {text}")

    if args.update:
        UPDATE.update(port=args.serve, target=target)
        if args.serve:
            serve_progress(args.serve)
        if args.wait:
            PROGRESS.status = "Waiting for FAST-HIPPOS to close"
            wait_for(args.wait)
    say(f"FAST-HIPPOS: {'updating' if args.update else 'installing'} in {target} ({platform.system()} {platform.machine()})")
    if not args.cellpose_only:
        next_step("The program", "Python and the program")
        if (target / ".venv").exists() and not healthy(target / ".venv"):
            say("Removing the incomplete program environment")
            shutil.rmtree(target / ".venv", ignore_errors=True)
        # the program itself is always built again: uv keeps a built package of the same version number
        run(args.uv, "sync", "--project", str(SOURCE), "--no-dev", "--frozen", "--no-editable", "--python", "3.12",
            "--reinstall-package", "fast-hippos", env={**env, "UV_PROJECT_ENVIRONMENT": str(target / ".venv")})
        # only now that the new version is installed does its folder replace the old one (the window installs
        # Cellpose with the install.py in it; the manual, tests and references are not needed there)
        if SOURCE != target / "program":
            shutil.rmtree(target / "program", ignore_errors=True)
            shutil.copytree(SOURCE, target / "program", ignore=shutil.ignore_patterns(
                ".git", ".github", ".venv", "__pycache__", "manual", "docs", "reference", "tests", "tools", "build"))
    index = [] if MAC else ["--index-url", "https://download.pytorch.org/whl/" + ("cu124" if gpu else "cpu"),
                            "--extra-index-url", "https://pypi.org/simple", "--index-strategy", "unsafe-best-match"]
    for v in versions:
        where = ("the Apple graphics chip (MPS) where it can" if MAC else
                 "the NVIDIA graphics card" if gpu else "the processor (no NVIDIA graphics card found)")
        next_step(f"Cellpose {v}, running on {where}; this takes a while", f"Cellpose {v} with PyTorch")
        cenv = target / f"cellpose{v}-env"
        venv(args.uv, cenv, "3.12", env)
        run(args.uv, "pip", "install", "--python", str(python_of(cenv)), *TORCH, *CELLPOSE[v], *index, env=env)

    if args.cellpose_only:
        say("\nReady.")
        PROGRESS.done()
        return
    next_step("Shortcuts", "Shortcuts")
    shortcuts(target, args.desktop, menu=args.shortcut)  # on Windows always "FAST-HIPPOS.exe" with the logo
    exe = target / "FAST-HIPPOS.exe" if WINDOWS else python_of(target / ".venv").parent / "fast-hippos"
    if args.update:
        version = program_version(target / "program")
        set_windows_version(version)
        say(f"\nUpdated to FAST-HIPPOS {version}.")
        PROGRESS.done()
        finish_update(target, ok=True)
        return
    say(f"\nReady. Start FAST-HIPPOS {'from the start menu' if args.shortcut and WINDOWS else 'from Applications' if args.shortcut and MAC else 'from the applications menu' if args.shortcut else 'with'}"
        f"{'' if args.shortcut else ' ' + str(exe)}; it opens in the browser.")
    PROGRESS.done()


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if e.code not in (0, None):
            say(str(e.code))
            PROGRESS.status = "The installation did not finish: " + str(e.code).strip().splitlines()[0]
            PROGRESS.write()
            if UPDATE.get("target"):
                finish_update(UPDATE["target"], ok=False)
        raise
