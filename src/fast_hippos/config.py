"""Run settings, loaded from a TOML file (replaces the Fiji script-parameter and screening dialogs).

Conventions (differences from the Fiji macro are deliberate, see docs/SPEC.md):
- Channels are 1-based, as in Fiji.
- Frames are 0-based indices. ``stimulation_frame`` is the first frame *with* stimulus,
  ``calibration_frame`` the first frame with the calibration stimulus.
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints


class Modality(StrEnum):
    TCSPC = "tcspc"  # fitted 2-component TCSPC amplitudes / TauSeparation
    FAST_FLIM = "fast_flim"
    TAU_CONTRAST = "tau_contrast"
    FD_FLIM = "fd_flim"
    RATIO = "ratio"
    INTENSITY = "intensity"


@dataclass
class InputSettings:
    files: list[Path] = field(default_factory=list)
    output: Path = Path("output")
    modality: Modality = Modality.TCSPC
    intensity_channel: int = 1  # first (amplitude) channel; lifetime/second channel is the next one
    tau1: float = 0.6  # ns, TCSPC component 1
    tau2: float = 3.4  # ns, TCSPC component 2
    default_frame_interval: float = 5.0  # s, used when not in metadata
    pixel_size: float | None = None  # µm, overrides metadata
    remove_last_frame: bool = False
    additional_channel: int | None = None  # measure mean intensity of this channel per cell
    series: list[int] | None = None  # .lif series to analyze (0-based); None = all


@dataclass
class FDFLIMSettings:
    reference: Path | None = None  # phase stack of a reference dye (TIFF / .npy)
    phases: int = 12
    frequency_mhz: float = 40.0
    tau_ref: float = 3.93  # ns
    lifetime_from: str = "phase"  # "phase" or "modulation"
    background: Path | None = None  # optional background phase stack


@dataclass
class PreprocessSettings:
    correct_bidirectional: bool = False
    correct_drift: bool = False
    drift_reference: str = "first"  # "first", "last" or "previous"
    drift_edge_detect: bool = False
    drift_blur_sigma: float = 4.0


@dataclass
class SegmentationSettings:
    method: str = "cellpose"  # "cellpose", "labelmap" (from file) or "threshold" (classical, no GPU)
    channel: int | None = None  # dedicated segmentation channel (1-based); None = intensity
    labelmap: Path | None = None  # for method = "labelmap"
    cellpose_model: str = "cyto3"  # cyto3, cyto2_cp3, nuclei, cpsam, or a path to a custom model
    cellpose_version: int | None = None  # 3 or 4; None = 4 for 'cpsam', else 3
    # Python executables of environments with Cellpose 3 / 4, used when the requested version is not
    # installed in the current environment (e.g. C:/PythonProjects/Cellpose4/.venv/Scripts/python.exe)
    cellpose3_python: Path | None = None
    cellpose4_python: Path | None = None
    diameter: float = 0.0  # 0 = automatic
    flow_threshold: float = 1.0
    cellprob_threshold: float = 0.0
    use_gpu: bool = True
    gamma: float | None = None  # e.g. 0.5 for contrast enhancement before segmentation
    start_frame: int | None = None  # projection range (0-based, inclusive); None = all
    end_frame: int | None = None
    min_cell_size: int = 50  # pixels
    max_circularity: float = 1.0  # 4*pi*A/P^2; 1.0 = no filtering
    min_cell_intensity: float = 0.0
    # Hit position refinement (replaces the Labkit step): a pixel classifier trained with
    # `fast-hippos train-classifier` predicts a nuclei probability map; the hit position becomes the
    # probability-weighted centre of the (eroded) cell instead of its centroid.
    classifier: Path | None = None
    classifier_class: int = 1  # class index of the nuclei in the classifier
    position_erosion: int = 2  # pixels


@dataclass
class DisplaySettings:
    lut: str = "turbo"
    min_lifetime: float = 2.0
    max_lifetime: float = 3.4
    smooth_traces: float = 0.0  # temporal box radius (frames) for traces and hit detection
    overlay_smooth_xy: float = 1.0  # radius (pixels) for the lifetime overlay
    overlay_smooth_t: float = 1.0  # radius (frames) for the lifetime overlay
    histogram_bins: int = 50
    dashboard: bool = True
    dashboard_max_size: int = 1024  # longest image side in the dashboard (downsampled if larger)
    dashboard_max_megapixels: float = 200.0  # total pixels x frames budget; frames are skipped beyond this
    save_png_plots: bool = True
    save_tables: bool = True  # per-frame trace tables (TSV)


@dataclass
class EventSettings:
    stimulation_frame: int | None = None  # manual; None = automatic detection
    calibration_frame: int | None = None
    baseline_only: bool = False
    sensitivity: float = 5.0  # min. peak prominence, in robust noise sigmas of the 2nd derivative
    margin: int = 1  # frames excluded before each transition (end of baseline, end of response)


@dataclass
class Criterion:
    metric: str
    op: str  # "<", ">" or "between"
    value: float
    value2: float | None = None
    # "AND": must pass; "OR": at least one of the OR criteria must pass. None = screening.logic
    logic: str | None = None


@dataclass
class ScreeningSettings:
    enabled: bool = False
    logic: str = "OR"  # "OR" or "AND"
    criteria: list[Criterion] = field(default_factory=list)
    # timed response window (for response_mean_abs / response_mean_diff / response_fraction)
    response_window: int = -1  # frames; -1 = full response
    response_window_anchor: str = "before_calibration"  # or "after_stimulation"
    response_window_margin: int = 0
    # validity gates (None = off)
    baseline_calibration_diff: tuple[float, float] | None = (0.5, 1.0)
    max_baseline_deviation: float | None = 0.2  # |cell baseline - population baseline|, ns
    rise_time_fraction: float = 0.75
    additional_channel_metric: str = "mean"  # "mean" or "first"
    classify_additional_channel: bool = False  # Otsu on log10 intensity -> 'class_additional'
    classification_threshold: float | None = None  # manual linear threshold, overrides Otsu
    random_hits: int | None = None  # testing: pick N random cells instead of screening
    random_seed: int | None = None
    # hits chosen by hand (e.g. exported from a dashboard selection): TSV with a 'cell' column and
    # optionally an 'image' column; replaces the criteria
    manual_hits: Path | None = None
    sort_by: str | None = None
    sort_descending: bool = True
    # stage positions
    stage_positions_file: Path | None = None  # text file: x0, y0, x1, y1, ... (m), or a .lif file
    n_tiles: tuple[int, int] | None = None  # (nx, ny); overruled by stitched metadata
    tile_overlap: float = 0.0  # percent; overruled by stitched metadata
    # output
    max_hits_per_rgn: int = 1000
    optimize_path: bool = True
    max_optimization_time: float = 5.0  # s per chunk


@dataclass
class Settings:
    input: InputSettings = field(default_factory=InputSettings)
    fdflim: FDFLIMSettings = field(default_factory=FDFLIMSettings)
    preprocess: PreprocessSettings = field(default_factory=PreprocessSettings)
    segmentation: SegmentationSettings = field(default_factory=SegmentationSettings)
    display: DisplaySettings = field(default_factory=DisplaySettings)
    events: EventSettings = field(default_factory=EventSettings)
    screening: ScreeningSettings = field(default_factory=ScreeningSettings)

    @classmethod
    def from_toml(cls, path: str | Path, overrides: list[str | Path] = ()) -> Settings:
        """Load settings; each override file is merged on top (tables merged, other values replaced)."""
        path = Path(path)
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        for override in overrides:
            with Path(override).open("rb") as fh:
                data = _merge(data, tomllib.load(fh))
        settings = _from_dict(cls, data)
        # relative paths in the config are relative to the config file
        base = path.parent
        settings.input.files = [_resolve(base, f) for f in settings.input.files]
        settings.input.output = _resolve(base, settings.input.output)
        for section, name in [
            (settings.fdflim, "reference"),
            (settings.fdflim, "background"),
            (settings.segmentation, "labelmap"),
            (settings.segmentation, "cellpose3_python"),
            (settings.segmentation, "cellpose4_python"),
            (settings.segmentation, "classifier"),
            (settings.screening, "stage_positions_file"),
            (settings.screening, "manual_hits"),
        ]:
            value = getattr(section, name)
            if value is not None:
                setattr(section, name, _resolve(base, value))
        return settings

    def to_dict(self) -> dict[str, Any]:
        return _to_plain(asdict(self))


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        out[key] = _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def _resolve(base: Path, p: Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else (base / p).resolve()


def _from_dict(cls, data: dict[str, Any]):
    hints = get_type_hints(cls)
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"Unknown setting(s) in [{cls.__name__}]: {', '.join(sorted(unknown))}")
    kwargs = {name: _convert(hints[name], value) for name, value in data.items()}
    return cls(**kwargs)


def _convert(tp, value):
    if value is None:
        return None
    origin = get_origin(tp)
    args = get_args(tp)
    if is_dataclass(tp):
        return _from_dict(tp, value)
    if origin is list:
        return [_convert(args[0], v) for v in value]
    if origin is tuple:
        return tuple(_convert(a, v) for a, v in zip(args, value, strict=True))
    if args and type(None) in args:  # Optional[X]; TOML has no null, so "" or [] mean None
        if value == "" or value == []:
            return None
        inner = next(a for a in args if a is not type(None))
        return _convert(inner, value)
    if tp is Path:
        return Path(value)
    if isinstance(tp, type) and issubclass(tp, StrEnum):
        return tp(value)
    if tp is float and isinstance(value, int):
        return float(value)
    return value


def _to_plain(obj):
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, StrEnum):
        return str(obj)
    return obj


METRICS = {
    "baseline_mean": "mean lifetime over the baseline",
    "response_mean_abs": "mean lifetime in the timed response window",
    "response_mean_diff": "mean (lifetime - own baseline) in the timed response window",
    "response_fraction": "response_mean_diff / response_max_diff",
    "response_max_abs": "maximum lifetime over the full response",
    "response_max_diff": "maximum (lifetime - own baseline) over the full response",
    "response_max_diff_pop": "maximum (lifetime - population baseline) over the full response",
    "rise_time_frames": "frames until the response reaches rise_time_fraction of its maximum",
    "rapid_response_ratio": "mean diff of the 2nd half / 1st half of the response",
    "calibration_mean": "mean lifetime over the calibration",
    "calibration_diff": "calibration_mean - baseline_mean",
    "baseline_dev_pop": "baseline_mean - population baseline",
    "additional_intensity": "intensity in the additional channel (mean over time or first frame)",
}
