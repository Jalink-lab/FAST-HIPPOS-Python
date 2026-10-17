"""Run settings, loaded from a TOML file (replaces the Fiji script-parameter and screening dialogs).

Conventions (differences from the Fiji macro are deliberate, see docs/SPEC.md):
- Channels are 1-based, as in Fiji.
- Frames are 0-based indices. ``stimulation_frame`` is the first frame *with* stimulus,
  ``calibration_frame`` the first frame with the calibration stimulus.
"""

from __future__ import annotations

import copy
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


# image types whose value per cell is a lifetime (ns); ratio and intensity are in their own units
LIFETIME_MODALITIES = (Modality.TCSPC, Modality.FAST_FLIM, Modality.TAU_CONTRAST, Modality.FD_FLIM)
GATES = ("baseline_calibration_diff", "max_baseline_deviation")


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
    # direction of the offset between the two scan directions: "y" when the fast scan axis is vertical (the scan
    # lines are columns), "x" when it is horizontal. Fixed for a given microscope.
    bidirectional_axis: str = "y"
    correct_drift: bool = False
    drift_reference: str = "first"  # "first", "last" or "previous"
    drift_edge_detect: bool = False
    drift_blur_sigma: float = 2.0  # px; blur of the cross-correlation image, to find its peak robustly


@dataclass
class SegmentationSettings:
    method: str = "cellpose"  # "cellpose", "labelmap" (from file) or "threshold" (classical, no GPU)
    channel: int | None = None  # dedicated segmentation channel (1-based); None = intensity
    labelmap: Path | None = None  # for method = "labelmap"
    cellpose_model: str = "cyto3"  # cyto3, cyto2_cp3, nuclei, cpsam, or a path to a custom model
    cellpose_version: int | None = None  # 3 or 4; None = 4 for 'cpsam', else 3
    # Python executables of environments with Cellpose 3 / 4, used when the requested version is not
    # installed in the current environment (e.g. <path to env>/.venv/Scripts/python.exe)
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
    # `fast-hippos-cli train-classifier` predicts a nuclei probability map; the hit position becomes the
    # probability-weighted centre of the (eroded) cell instead of its centroid.
    classifier: Path | None = None
    classifier_class: int = 1  # class index of the nuclei in the classifier
    position_erosion: int = 2  # pixels


@dataclass
class DisplaySettings:
    lut: str = "turbo"
    # initial lifetime / ratio range of colour scales and axes; None = from the data (1st-99th percentile).
    # Can also be changed in the dashboard.
    min_lifetime: float | None = None
    max_lifetime: float | None = None
    smooth_traces: float = 0.0  # temporal box radius (frames) for traces and hit detection
    overlay_smooth_xy: float = 1.0  # radius (pixels) for the lifetime overlay
    overlay_smooth_t: float = 1.0  # radius (frames) for the lifetime overlay
    histogram_bins: int = 50
    dashboard: bool = True
    dashboard_max_size: int = 1024  # longest image side in the dashboard (downsampled if larger)
    dashboard_max_megapixels: float = 200.0  # overview pixels x frames budget; frames are skipped beyond this
    dashboard_tiles: bool = True  # larger images: full-resolution tiles loaded on zoom (folder 'tiles')
    save_png_plots: bool = True
    save_tables: bool = True  # per-frame trace tables (TSV)
    # how the dashboards start (each dashboard remembers what is changed in it)
    traces_view: str = "auto"  # auto (lines up to 300 cells, else bands), lines, bands, density
    scatter_x: str = "mean_intensity"  # a cell value, or value_at_frame / additional_at_frame
    scatter_log_x: bool = False
    scatter_y: str = "value_at_frame"
    scatter_log_y: bool = False


@dataclass
class EventSettings:
    stimulation_frame: int | None = None  # manual; None = automatic detection (also when the other frame is set)
    calibration_frame: int | None = None
    baseline_only: bool = False
    no_calibration: bool = False  # the experiment has no calibration: only the stimulation is looked for
    sensitivity: float = 5.0  # detection threshold: min. peak prominence in noise sigmas of the 2nd derivative; lower = more sensitive
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
    response_window: int | None = None  # frames; None (empty) = the whole response (-1 in older settings files)
    response_window_anchor: str = "before_calibration"  # or "after_stimulation"
    response_window_margin: int = 0
    # validity gates (None = off)
    # quality gates, in the unit of the measured value; these defaults are lifetimes (ns): for ratio and intensity
    # data they are off unless set (see _gates_for_image_type)
    baseline_calibration_diff: tuple[float, float] | None = (0.5, 1.0)
    max_baseline_deviation: float | None = 0.2  # |cell baseline - population baseline|
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
    # stage position (X, Y) -> .rgn frame (LAS X Navigator): by default X_rgn = -Y_stage, Y_rgn = -X_stage (Stellaris)
    rgn_swap_xy: bool = True
    rgn_invert_x: bool = True
    rgn_invert_y: bool = True
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
    # settings of single images that differ from those above, by image name: {name: {"events": {...}, "screening":
    # {...}}}; only IMAGE_SETTINGS can differ (in TOML: [image."name".events]). Set from a dashboard with 'Apply to
    # this image only'.
    image: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)

    def for_image(self, name: str) -> Settings:
        """The settings for one image: these, with that image's own settings (if any) filled in."""
        own = self.image.get(name)
        if not own:
            return self
        s = copy.deepcopy(self)
        for section, values in own.items():
            for key, value in values.items():
                setattr(getattr(s, section), key, value)
        return s

    @classmethod
    def from_toml(cls, path: str | Path, overrides: list[str | Path] = ()) -> Settings:
        """Load settings; each override file is merged on top (tables merged, other values replaced)."""
        path = Path(path)
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        for override in overrides:
            with Path(override).open("rb") as fh:
                extra = tomllib.load(fh)
            # a hit list named in an override file lives next to that file
            manual = extra.get("screening", {}).get("manual_hits")
            if manual and not Path(manual).is_absolute():
                extra["screening"]["manual_hits"] = str((Path(override).parent / manual).resolve())
            data = _merge(data, extra)
        settings = _gates_for_image_type(_from_dict(cls, data), data)
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

    @classmethod
    def from_dict(cls, data: dict) -> Settings:
        return _gates_for_image_type(_from_dict(cls, data), data)

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


def _gates_for_image_type(settings: Settings, data: dict) -> Settings:
    """The default quality gates are lifetimes in ns: for ratio and intensity data they are off unless the settings
    give them."""
    if settings.input.modality not in LIFETIME_MODALITIES:
        given = data.get("screening", {}) if isinstance(data.get("screening"), dict) else {}
        for k in GATES:
            if k not in given:
                setattr(settings.screening, k, None)
    # the whole response window was -1 in older settings files; it is empty now
    if settings.screening.response_window is not None and settings.screening.response_window <= 0:
        settings.screening.response_window = None
    for own in settings.image.values():
        w = own.get("screening", {}).get("response_window")
        if w is not None and w <= 0:
            own["screening"]["response_window"] = None
    return settings


def _from_dict(cls, data: dict[str, Any]):
    hints = get_type_hints(cls)
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        section = {get_type_hints(Settings).get(f.name): f.name for f in fields(Settings)}.get(cls, cls.__name__)
        raise ValueError(f"Unknown setting(s) in [{section}]: {', '.join(sorted(unknown))}")
    kwargs = {name: _convert(hints[name], value) for name, value in data.items()}
    return cls(**kwargs)


# the settings that may differ per image (Settings.image), by section
IMAGE_SETTINGS = {
    "events": ("stimulation_frame", "calibration_frame", "baseline_only", "no_calibration", "sensitivity", "margin"),
    "screening": ("response_window", "response_window_anchor", "response_window_margin"),
}


def _image_settings(value: dict) -> dict:
    """Validate and convert per-image settings ({name: {section: {key: value}}}); empty entries are dropped."""
    classes = {"events": EventSettings, "screening": ScreeningSettings}
    out: dict[str, dict] = {}
    for name, sections in value.items():
        if not isinstance(sections, dict):
            raise ValueError(f'[image."{name}"]: expected sections {" / ".join(IMAGE_SETTINGS)}')  # noqa: TRY004 - shown to the user like other setting errors
        own = {}
        for section, values in sections.items():
            if section not in IMAGE_SETTINGS:
                raise ValueError(f'[image."{name}".{section}]: only {" and ".join(IMAGE_SETTINGS)} settings can differ per image')
            bad = set(values) - set(IMAGE_SETTINGS[section])
            if bad:
                raise ValueError(f'[image."{name}".{section}]: {", ".join(sorted(bad))} cannot differ per image (possible: '
                                 f'{", ".join(IMAGE_SETTINGS[section])})')
            hints = get_type_hints(classes[section])
            if values:
                own[section] = {k: _convert(hints[k], v) for k, v in values.items()}
        if own:
            out[str(name)] = own
    return out


def _convert(tp, value):
    if value is None:
        return None
    origin = get_origin(tp)
    args = get_args(tp)
    if is_dataclass(tp):
        return _from_dict(tp, value)
    if origin is dict:  # Settings.image
        return _image_settings(value)
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
    "baseline_mean": "Average lifetime of the cell before the stimulation (its baseline).",
    "response_mean_abs": "Average lifetime of the cell in the response window (the value itself, not the change).",
    "response_mean_diff": "Average change of the lifetime in the response window, compared with the cell's own "
        "baseline (lifetime − baseline).",
    "response_fraction": "How much of its maximal response the cell keeps in the response window: "
        "response_mean_diff ÷ response_max_diff (1 = sustained, near 0 = transient).",
    "response_max_abs": "Highest lifetime of the cell between the stimulation and the calibration.",
    "response_max_diff": "Largest change of the lifetime after the stimulation, compared with the cell's own baseline. "
        "The usual measure of how strongly a cell responds.",
    "response_max_diff_pop": "Largest lifetime after the stimulation minus the average baseline of all cells (instead "
        "of the cell's own baseline).",
    "rise_time_frames": "Number of frames of the response up to and including the first frame in which the cell "
        "reaches the rise fraction (e.g. 75 %) of its maximal response (1 = already in the first frame after the "
        "stimulation). Small = fast responder. Only meaningful for cells that respond: combine it with an AND "
        "criterion on the response.",
    "rapid_response_ratio": "Average response in the second half of the response period divided by that in the first "
        "half. Above 1 = still rising, below 1 = fading.",
    "calibration_mean": "Average lifetime of the cell during the calibration (maximal stimulation).",
    "calibration_diff": "Response to the calibration: calibration_mean − baseline_mean. Shows whether the sensor works "
        "in this cell.",
    "baseline_dev_pop": "How much the baseline of the cell differs from the average baseline of all cells.",
    "additional_intensity": "Intensity of the additional channel in the cell (mean over time, or the first frame).",
}
