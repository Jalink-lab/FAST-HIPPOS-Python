"""Checks of the settings against the input images, before a run starts (metadata only, so it takes seconds).

A run that would fail halfway, e.g. on a channel that an image does not have, stops at once with a list of all
problems and where to fix them, instead of after minutes of work with a traceback.
"""

from __future__ import annotations

from pathlib import Path

from .config import Modality, Settings
from .io import image_info, safe_name


class SettingsError(ValueError):
    """The settings do not fit the input; the message lists all problems, one per line."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


# image types that read a second channel (the one after input.intensity_channel)
TWO_CHANNELS = {Modality.TCSPC: "the second lifetime component", Modality.FAST_FLIM: "the lifetime",
                Modality.TAU_CONTRAST: "the lifetime", Modality.RATIO: "the denominator"}


def check_inputs(settings: Settings) -> list[str]:
    """All problems found, as readable sentences; empty if the run can start."""
    s_in, seg, ev = settings.input, settings.segmentation, settings.events
    problems: list[str] = []
    if not s_in.files:
        problems.append("No images selected (Images).")
    positions_file = settings.screening.stage_positions_file
    lif = Path(positions_file) if positions_file and Path(positions_file).suffix.lower() == ".lif" else None
    folders: dict[str, str] = {}  # result folder (lower case) -> the image that gets it
    n_images = 0
    for f in s_in.files:
        path = Path(f)
        if not path.exists():
            problems.append(f"Image not found: {path}")
            continue
        try:
            infos = image_info(path, lif)
        except Exception as e:  # noqa: BLE001 - reported to the user
            problems.append(f"{path.name} cannot be read: {e}")
            continue
        if path.suffix.lower() == ".lif" and s_in.series:
            infos = [infos[i] for i in s_in.series if 0 <= i < len(infos)]
        for info in infos:
            # the image name as the analysis gives it (see io.read_lif), and so the name of its result folder
            name = f"{path.stem} - {info['name'].replace('/', '-')}" if path.suffix.lower() == ".lif" else info["name"]
            label = path.name if len(infos) == 1 else f"{path.name} ({info['name']})"
            key = safe_name(name).lower()
            if key in folders:
                problems.append(f"{label} and {folders[key]} would share the result folder '{safe_name(name)}': rename one "
                                "of them (Images).")
            folders.setdefault(key, label)
            n_images += 1
            problems += _check_image(label, info, settings.for_image(name), own="events" in settings.image.get(name, {}))
    if seg.method == "labelmap" and (seg.labelmap is None or not Path(seg.labelmap).exists()):
        problems.append(f"Label image not found: {seg.labelmap} (Cell segmentation)." if seg.labelmap
                        else "No label image chosen (Cell segmentation).")
    if seg.classifier is not None and not Path(seg.classifier).exists():
        problems.append(f"Nuclei classifier not found: {seg.classifier} (Cell segmentation, advanced).")
    sc = settings.screening
    if sc.enabled and sc.stage_positions_file is not None and not Path(sc.stage_positions_file).exists():
        problems.append(f"Stage positions file not found: {sc.stage_positions_file} (Screening).")
    if (sc.enabled and sc.stage_positions_file is not None and Path(sc.stage_positions_file).exists()
            and Path(sc.stage_positions_file).suffix.lower() != ".lif"):
        from .stage import read_positions_file

        try:
            n_pos = len(read_positions_file(Path(sc.stage_positions_file)))
            if n_images and n_pos < n_images:
                problems.append(f"The stage positions file has {n_pos} position{'s' if n_pos != 1 else ''} for "
                                f"{n_images} images: give X and Y for every image (Screening, advanced).")
        except ValueError as e:
            problems.append(f"Stage positions file: {e} (Screening, advanced).")
    if sc.enabled and sc.manual_hits is not None and not Path(sc.manual_hits).exists():
        problems.append(f"Hand-picked hits file not found: {sc.manual_hits} (Screening, advanced).")
    if s_in.modality == Modality.FD_FLIM and (settings.fdflim.reference is None or not Path(settings.fdflim.reference).exists()):
        problems.append("Frequency-domain FLIM needs a reference phase stack (Images, advanced).")
    for image, where in [(None, "Stimulation and calibration")] + [(n, f"own settings of {n}") for n in settings.image]:
        e = settings.for_image(image).events if image else ev
        if (not e.baseline_only and e.stimulation_frame is not None and e.calibration_frame is not None
                and e.calibration_frame <= e.stimulation_frame):
            problems.append(f"The calibration frame ({e.calibration_frame}) must come after the stimulation frame "
                            f"({e.stimulation_frame}) ({where}).")
    return problems


def _check_image(name: str, info: dict, settings: Settings, own: bool = False) -> list[str]:
    """Problems of one image; settings: those of this image (Settings.for_image), own: it has its own stimulation settings."""
    s_in, seg, ev = settings.input, settings.segmentation, settings.events
    n_ch, n_fr, out = info["channels"], info["frames"], []
    have = f"{name} has {n_ch} channel{'s' if n_ch != 1 else ''}"
    c = s_in.intensity_channel
    if not 1 <= c <= n_ch:
        out.append(f"{have}, but the first FLIM / ratio channel is set to {c} (Images, advanced).")
    elif s_in.modality in TWO_CHANNELS and c + 1 > n_ch:
        out.append(f"{have}, but '{s_in.modality}' needs channel {c + 1} for {TWO_CHANNELS[s_in.modality]} "
                   f"(the channel after the first FLIM channel {c}) (Images: image type).")
    if s_in.additional_channel is not None and not 1 <= s_in.additional_channel <= n_ch:
        out.append(f"{have}, but the additional channel is set to {s_in.additional_channel} (Images: additional channel).")
    if seg.channel is not None and not 1 <= seg.channel <= n_ch:
        out.append(f"{have}, but the segmentation channel is set to {seg.channel} (Cell segmentation, advanced).")
    frames = n_fr - (1 if s_in.remove_last_frame and n_fr > 1 else 0)
    if not ev.baseline_only:
        for label, f in (("stimulation", ev.stimulation_frame), ("calibration", ev.calibration_frame)):
            if f is not None and not 0 <= f < frames:
                out.append(f"{name} has {frames} frames (0–{frames - 1}), but the {label} frame is set to {f} "
                           + ("(its own settings, under Stimulation and calibration)." if own else "(Stimulation and calibration)."))
    for label, f in (("first", seg.start_frame), ("last", seg.end_frame)):
        if f is not None and not 0 <= f < frames:
            out.append(f"{name} has {frames} frames, but the {label} projection frame is set to {f} (Cell segmentation, advanced).")
    return out
