# Settings files and the command line

Everything the window does can also be done from the command line, with the settings in a text file. This is handy
for running the same analysis on many data sets, or on a computer without a screen.

## Settings files

Settings files are [TOML](https://toml.io) files: sections in square brackets, with `key = value` lines. Every run
saves its settings as `fast_hippos_settings.toml` in the output folder, and *Save settings…* in the window writes one;
these can be used on the command line as they are, and opened again in the window. Only settings that differ from the
defaults are needed. A minimal file for a TCSPC screen:

```toml
[input]
files = ["C:/Data/screen/plate1.lif"]
output = "C:/Data/screen/plate1_results"
modality = "tcspc"
tau1 = 0.6                     # ns
tau2 = 3.4                     # ns
additional_channel = 3         # optional

[segmentation]
method = "cellpose"
cellpose_model = "cyto3"       # or "cpsam" (Cellpose 4)

[screening]
enabled = true
criteria = [
  { metric = "response_mean_diff", op = "<", value = 0.6, logic = "AND" },
  { metric = "baseline_mean",      op = "<", value = 2.6, logic = "AND" },
]
```

- Paths may be relative to the settings file. Use `/` or double `\\` in Windows paths.
- Frames count from 0 and are the *first* frame with the stimulus. Channels count from 1, as in Fiji.
- An empty value (`""`) means *automatic* or *not set*, e.g. `stimulation_frame = ""`.
- The key of every setting is shown in [All settings](settings.md), and `fast-hippos-cli init-config` writes an
  annotated example file.

[Settings for single images](../guide/own-settings.md) are written as tables per image. The name is the image name
as the overview and the dashboard show it: the file name without extension (`<file> - <series>` for a `.lif` file,
`<prefix>_STITCHED` for a tile folder). The log warns about a name that matches no image of the run.

```toml
[image."plate1 - Position 7".events]
stimulation_frame = 8
calibration_frame = 27
```

## Commands

Run the commands in PowerShell, in the FAST-HIPPOS folder, as `uv run fast-hippos-cli …`, or directly with
`.venv\Scripts\fast-hippos-cli.exe …`.

| Command | |
|---|---|
| `fast-hippos-cli run settings.toml` | the full analysis |
| `fast-hippos-cli reapply settings.toml` | redo stimulation detection, screening and dashboards for the run in the output folder, with the `[events]`, `[screening]` and `[display]` settings of the file |
| `fast-hippos-cli reapply settings.toml --override screening.toml` | the same, with the settings of a second file on top, e.g. one saved with *Settings → TOML* in a dashboard (`run` takes `--override` too) |
| `fast-hippos-cli experiment folder` | rebuild the overview of all samples in an experiment folder (see [A screen of several samples](../guide/screen.md)); every run of a sample in it does this too, when its settings file has `experiment = "<folder>"` under `[input]` |
| `fast-hippos-cli experiment folder --reapply settings.toml` | re-apply the `[events]`, `[screening]` and `[display]` settings of the file to every sample of the experiment (each keeps the own settings of its single images), then rebuild its overview |
| `fast-hippos-cli init-config example.toml` | write an annotated example settings file |
| `fast-hippos-cli stitch tiles_folder [--lif scan.lif] [--bidirectional y]` | only stitch a folder of exported tiles; writes `<prefix>_STITCHED.tif` next to the folder (or `--output`), replacing an existing one |
| `fast-hippos-cli train-classifier projection.tif scribbles.tif nuclei.joblib` | train a nuclei classifier for the hit positions |
| `fast-hippos-cli demo` | analyze a small synthetic experiment and open its dashboard |
| `fast-hippos-cli gui` | open the window (with a console that shows its messages) |
| `fast-hippos-cli shortcut` | put a shortcut on the desktop (Windows) |

`fast-hippos-cli <command> --help` lists the options of a command. Like the window, every `run` and `reapply` writes
its settings as `fast_hippos_settings.toml` into the output folder. A mistake in a settings file (an unknown
setting, a TOML syntax error) gives a short error message naming the section.

!!! note "Re-apply and settings for single images"
    A `reapply` keeps the own settings of single images of the run, unless the settings file has an `[image…]`
    part (or `image = {}`, for none).
