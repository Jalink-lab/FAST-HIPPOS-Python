"""Screenshots of the user manual (manual/images), from the example analysis (make_example_data.py, example.toml),
with the installed Microsoft Edge driven by Playwright. A FAST-HIPPOS window of its own is started for this
(gui_instance.py), so the settings of the user are not touched.

    python tools/manual/screenshots.py <example folder> [only these shots, e.g. gui_images dash_cell]
"""

import sys
import time
from pathlib import Path
from urllib.parse import quote

from PIL import Image
from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from gui_instance import start

OUT = Path(__file__).resolve().parents[2] / "manual" / "images"
VIEW = {"width": 1440, "height": 900}
SCALE = 1.5  # device pixels per CSS pixel: sharp text, also on high-resolution screens


def save(locator_or_page, name: str, **kw) -> None:
    path = OUT / f"{name}.png"
    locator_or_page.screenshot(path=path, animations="disabled", **kw)
    im = Image.open(path)
    im.save(path, optimize=True)
    print(f"{name}.png {im.size[0]}×{im.size[1]}")


def card(page: Page, title: str):
    return page.locator(".card", has=page.locator(f"text='{title}'")).first


def panel(page: Page, title: str):
    return page.locator(".panel", has=page.locator("h2", has_text=title)).first


def gui_shots(page: Page, url: str, want) -> Path:
    page.goto(url)
    page.wait_for_selector("#bRun")
    page.wait_for_timeout(2500)  # image information, Cellpose check, output folder
    page.once("dialog", lambda d: d.accept())
    page.click("#bReapply")
    page.wait_for_function("document.getElementById('state').textContent.includes('Done')", timeout=120_000)
    page.wait_for_timeout(800)
    page.evaluate("window.scrollTo(0, 0)")
    if want("gui"):
        save(page, "gui")
    for name, title in (("gui_images", "Images"), ("gui_segmentation", "Cell segmentation"),
                        ("gui_stimulation", "Stimulation and calibration"), ("gui_screening", "Screening"),
                        ("gui_display", "Display and output"), ("gui_run", "Run")):
        if want(name):
            save(card(page, title), name)
    if want("gui_advanced"):  # the advanced settings of the segmentation, opened
        c = card(page, "Cell segmentation")
        c.locator("text=Advanced settings").first.click()
        page.wait_for_timeout(400)
        save(c, "gui_advanced")
        c.locator("text=Advanced settings").first.click()
    if want("gui_rgn"):  # Screening, advanced: from 'Stage positions and .rgn files' to the tiles
        c = card(page, "Screening")
        c.locator("text=Advanced settings").first.click()
        page.wait_for_timeout(400)
        box = page.evaluate("""() => {
          const hs = [...document.querySelectorAll('h3')];
          const a = hs.find(h => h.textContent.startsWith('Stage positions')), b = hs.find(h => h.textContent.startsWith('Tiles'));
          a.scrollIntoView(); const r0 = a.getBoundingClientRect(), r1 = b.nextElementSibling.getBoundingClientRect();
          const card = a.closest('.card').getBoundingClientRect();
          return {x: card.left, y: r0.top - 4, width: card.width, height: r1.bottom - r0.top + 8};
        }""")
        save(page, "gui_rgn", clip=box)
        c.locator("text=Advanced settings").first.click()
    return Path(page.evaluate("document.querySelector('#results [data-open]').dataset.open")).parent


def dashboard_shots(page: Page, base: str, out: Path, want) -> None:
    page.goto(f"{base}files/{quote((out / 'example_screen_1' / 'dashboard.html').as_posix())}")
    page.wait_for_selector("#scrapply", state="attached")
    page.wait_for_timeout(2500)
    if want("dashboard"):
        save(page, "dashboard")
    scr = panel(page, "Screening")
    if want("dash_screening"):
        save(scr, "dash_screening")
    for name, title in (("dash_timing", "Timing"), ("dash_gates", "Quality gates"), ("dash_output", "Output"),
                        ("dash_criteria", "Hits from")):
        if want(name):
            box = scr.locator("fieldset, .box, .blk, section, div", has=page.locator(f"text=/^{title}/i")).last
            save(box, name)
    for name, title in (("dash_image", "Image"), ("dash_traces", "Traces"), ("dash_kymograph", "Kymograph"),
                        ("dash_distribution", "Distribution"), ("dash_scatter", "Scatter"), ("dash_cells", "Cells")):
        if want(name):
            # the distribution and the scatter plot during the response, where the low responders stand apart
            page.evaluate(f"setFrame({15 if name in ('dash_distribution', 'dash_scatter') else 0})")
            p = panel(page, title)
            p.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            save(p, name)
    page.evaluate("setFrame(0)")
    if want("dash_cell"):  # the cell card of a hit, as when the mouse is over it
        page.mouse.move(0, 0)
        page.evaluate("$('selhits').click(); const i = [...S.sel][0]; $('clearsel').click(); setHover(i)")
        p = page.locator(".panel.cellp")
        p.scroll_into_view_if_needed()
        page.wait_for_timeout(800)
        save(p, "dash_cell")
    if want("dashboard_views"):  # the views, with the screening pane folded
        page.evaluate("window.scrollTo(0, 0); setHover(-1)")
        page.click("#scrtoggle")
        page.wait_for_timeout(800)
        save(page, "dashboard_views")
        page.click("#scrtoggle")


def overview_shots(page: Page, base: str, out: Path, want) -> None:
    page.goto(f"{base}files/{quote((out / 'index.html').as_posix())}")
    page.wait_for_selector(".panel.images")
    page.wait_for_timeout(2000)
    if want("overview"):
        save(page, "overview")
    page.click("#hitsToggle")  # the list of hits, unfolded
    page.wait_for_timeout(400)
    for name, cls in (("ov_images", "images"), ("ov_response", "resp"), ("ov_cells", "metric"), ("ov_maps", "maps"),
                      ("ov_hits", "hitsp")):
        if want(name):
            p = page.locator(f".panel.{cls}").first
            p.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            save(p, name)


def experiment_shots(page: Page, url: str, example: Path, want) -> None:
    """The example experiment (make_example_experiment.py): the window with the settings of its third sample, and the
    overview of all samples."""
    page.goto(url)
    page.wait_for_selector("#bRun")
    page.wait_for_function("!document.getElementById('bReapplyAll').hidden", timeout=30_000)
    page.wait_for_timeout(2500)
    page.evaluate("window.scrollTo(0, 0)")
    if want("gui_experiment"):
        save(card(page, "Images"), "gui_experiment")
    if want("gui_run_experiment"):
        save(card(page, "Run"), "gui_run_experiment")
    if want("gui_experiment_differs"):  # another criterion in the window than the samples were analyzed with
        page.evaluate("S.screening.criteria[0].value = 3.0; render()")
        page.wait_for_function("document.getElementById('checks').textContent.includes('other settings')", timeout=30_000)
        page.wait_for_timeout(500)
        save(page.locator("#checks"), "gui_experiment_differs")
    page.goto(f"{url}files/{quote((example / 'experiment' / 'index.html').as_posix())}")
    page.wait_for_selector(".panel.images")
    page.wait_for_timeout(2000)
    if want("experiment"):
        save(page, "experiment")


def main(example: Path, only: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    want = (lambda n: any(n.startswith(o) for o in only)) if only else (lambda n: True)
    proc, url = start(example, 8767)
    try:
        time.sleep(2)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge")
            page = browser.new_page(viewport=VIEW, device_scale_factor=SCALE, color_scheme="light")
            out = gui_shots(page, url, want)
            dashboard_shots(page, url, out, want)
            overview_shots(page, url, out, want)
            if any(want(n) for n in ("gui_experiment", "gui_run_experiment", "experiment")):
                if not (example / "experiment" / "index.html").exists():
                    sys.exit("No example experiment: run tools/manual/make_example_experiment.py first")
                proc2, url2 = start(example, 8768, "sample_3.toml")
                try:
                    time.sleep(2)
                    experiment_shots(page, url2, example, want)
                finally:
                    proc2.terminate()
            browser.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:])
