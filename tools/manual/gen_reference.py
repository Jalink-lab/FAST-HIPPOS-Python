"""The reference pages of the manual, generated from the program itself (the labels and hover texts of the FAST-HIPPOS
window, the metrics), so that they always match the version they describe.

    python tools/manual/gen_reference.py
"""

import html
from pathlib import Path

from fast_hippos import gui
from fast_hippos.config import METRICS

REF = Path(__file__).resolve().parents[2] / "manual" / "reference"


def value(v) -> str:
    if v is None or v == "" or v == []:
        return "*empty*"
    if isinstance(v, bool):
        return "on" if v else "off"
    return f"`{v}`"


def field_html(f: dict) -> str:
    choices = f.get("choices")
    extra = ""
    if isinstance(choices, dict):
        extra = "<br><span class=\"fh-choices\">" + " · ".join(f"<code>{html.escape(str(k))}</code> {html.escape(str(v))}"
                                                            for k, v in choices.items()) + "</span>"
    default = value(f.get("default"))
    default = html.escape(default.strip("`")) if default.startswith("`") else default.replace("*", "")
    return (f'<tr data-search="{html.escape((f["label"] + " " + f["key"] + " " + f.get("tip", "")).lower())}">'
            f'<td><b>{html.escape(f["label"])}</b><br><code class="fh-key">{html.escape(f["key"])}</code></td>'
            f'<td>{html.escape(f.get("tip") or f.get("help") or "")}{extra}</td><td>{default}</td></tr>')


def settings_page() -> str:
    s = gui.schema()
    fields = {f["key"]: f for sec in s["sections"] for f in sec["fields"]}
    out = ["---", "title: All settings", "---", "", "# All settings", "",
           ("Every setting of the FAST-HIPPOS window, in the order of the window: first the settings that are always shown, "
           "then those under *Advanced settings*. The second line of each name is how the setting is written in a settings "
           "file (`[section] key = value`, see [Settings files and the command line](command-line.md)). The texts are the "
           "same as the hover texts in the window."), "",
           '<input id="fh-filter" class="fh-filter" type="search" placeholder="Filter the settings, e.g. calibration, rgn, cellpose…">', ""]
    for card in s["layout"]:
        out += [f"## {card['title']}", ""]
        groups = [("Always shown", card["basic"])] + [(f"Advanced: {g['title']}", g["keys"]) for g in card["advanced"]]
        for title, keys in groups:
            keys = [k for k in keys if k in fields]
            if not keys:
                continue
            out += [f'<h3 class="fh-group">{html.escape(title)}</h3>',
                    '<table class="fh-settings"><thead><tr><th>Setting</th><th>What it does</th><th>Default</th></tr></thead><tbody>',
                    *[field_html(fields[k]) for k in keys], "</tbody></table>", ""]
    return "\n".join(out) + "\n"


def metrics_page() -> str:
    out = ["---", "title: Cell values (metrics)", "---", "", "# Cell values (metrics)", "",
           ("FAST-HIPPOS measures these values for every cell. They can be used in hit criteria, for sorting the hits, as "
           "axes of the scatter plots and for colouring the cells in the dashboard. *Lifetime* stands for the measured "
           "quantity: the ratio for ratio imaging, the intensity for intensity-only data."), "",
           "| Name | Meaning |", "|---|---|"]
    out += [f"| `{k}` | {v} |" for k, v in METRICS.items()]
    out += ["", "## Other values in the tables", "",
            "These are in `cells.tsv` and in the Cells table of the dashboard (and can be shown in the scatter plot).", "",
            "| Name | Meaning |", "|---|---|"]
    out += [f"| `{k}` | {v} |" for k, v in OTHER_VALUES.items()]
    return "\n".join(out) + "\n"


OTHER_VALUES = {
    "area_px": "Size of the cell in pixels.",
    "mean_intensity": "Mean pixel value of the cell per frame, over the frames used for the segmentation, in the units "
        "of the image (photon counts or amplitudes). The *Minimum cell intensity* filter uses the same value.",
    "circularity": "4π · area / perimeter²: 1 for a circle, lower for irregular shapes.",
    "centroid_x, centroid_y": "Centre of the cell in the image (pixels).",
    "pos_x_px, pos_y_px": "The position used for the hit: the centre of the cell, or of its nucleus with a nuclei "
        "classifier (pixels).",
    "abs_x_m, abs_y_m": "That position as a stage position (metres), as written to the .rgn files: in the frame of "
        "the LAS X Navigator (see [Back to the microscope](../guide/microscope.md#where-the-stage-positions-come-from)).",
    "class_additional": "1 when the cell is positive for the additional channel (classification on), else 0.",
    "valid": "The cell passes the quality gates.",
    "hit": "The cell is a hit.",
}


if __name__ == "__main__":
    REF.mkdir(parents=True, exist_ok=True)
    (REF / "settings.md").write_text(settings_page(), encoding="utf-8")
    (REF / "metrics.md").write_text(metrics_page(), encoding="utf-8")
    print("written", REF)
