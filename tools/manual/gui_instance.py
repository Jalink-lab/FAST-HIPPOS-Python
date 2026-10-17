"""A FAST-HIPPOS window for the screenshots of the manual: its own home folder (so the settings and preferences of
the user are not touched), the settings of the example analysis, light theme.

    python tools/manual/gui_instance.py <example folder with example.toml> [port]
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from fast_hippos import gui
from fast_hippos.config import Settings


def start(example: Path, port: int = 8766) -> tuple[subprocess.Popen, str]:
    home = Path(tempfile.mkdtemp(prefix="fh_manual_home_"))
    state = home / ".fast_hippos"
    state.mkdir()
    settings = Settings.from_toml(example / "example.toml")  # paths made absolute
    (state / "last_settings.toml").write_text(gui.to_toml(settings.to_dict()), encoding="utf-8")
    (state / "gui_prefs.json").write_text('{"theme": "light"}', encoding="utf-8")
    env = os.environ | {"USERPROFILE": str(home), "HOME": str(home), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen([sys.executable, "-m", "fast_hippos.cli", "gui", "--port", str(port), "--no-browser"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc, f"http://127.0.0.1:{port}/"


if __name__ == "__main__":
    p, url = start(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 8766)
    print(url, flush=True)
    for line in p.stdout:
        print(line, end="", flush=True)
