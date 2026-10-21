"""The context help of the pages (window, dashboard, overviews) from the user manual: the guide, reference and help
pages of manual/ converted to HTML, one section per heading, into src/fast_hippos/templates/help.json.

    python tools/manual/make_help.py

The pages show it in a side panel (templates/common/help.js); their ? buttons point at '<page>#<heading anchor>'.
tests/test_help.py fails when help.json no longer matches the manual, or a ? button points at a heading that is gone.
Screenshots are left out (the help is read next to the real thing); links to pages that are not in the help open
the online manual.
"""

import json
import posixpath
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[2]
MANUAL = ROOT / "manual"
OUT = ROOT / "src" / "fast_hippos" / "templates" / "help.json"
SITE = "https://jalink-lab.github.io/FAST-HIPPOS-Python/"

# the pages in the help, in the order of the manual's contents (mkdocs.yml)
PAGES = {
    "User guide": ["guide/window", "guide/dashboard", "guide/choosing-hits", "guide/own-settings", "guide/overview",
                   "guide/microscope", "guide/screen", "guide/output-folder"],
    "Reference": ["reference/settings", "reference/metrics", "reference/analysis"],
    "Help": ["help/faq", "help/glossary"],
}
IN_HELP = {p for pages in PAGES.values() for p in pages}

EXTENSIONS = ["abbr", "admonition", "attr_list", "def_list", "footnotes", "md_in_html", "tables", "toc",
              "pymdownx.details", "pymdownx.keys", "pymdownx.superfences"]


def _source(page: str) -> str:
    text = (MANUAL / f"{page}.md").read_text(encoding="utf-8")
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.DOTALL)  # front matter
    text = re.sub(r"^<input id=\"fh-filter\"[^>]*>\s*$", "", text, flags=re.MULTILINE)  # the settings filter of the site
    text = re.sub(r"<figure markdown>.*?</figure>\s*", "", text, flags=re.DOTALL)  # screenshots
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)(\{[^}]*\})?", "", text)  # other images
    text = re.sub(r"^\[[^\]]*\]\([^)]*\)\{ ?\.md-button[^}]*\}\s*$", "", text, flags=re.MULTILINE)  # 'Try it' buttons
    text = re.sub(r"\s*:(material|octicons|fontawesome)-[a-z0-9-]+:", "", text)  # icons
    return text + "\n\n" + (MANUAL / "includes" / "abbreviations.md").read_text(encoding="utf-8")


def _link(page: str, href: str) -> str:
    """An attribute for a link of the page: data-h for a page in the help, else the online manual."""
    if re.match(r"[a-z]+:", href):
        return f'href="{href}" target="_blank" rel="noopener"'
    path, _, anchor = href.partition("#")
    if not path:
        target = page
    else:
        target = posixpath.normpath(posixpath.join(posixpath.dirname(page), path))
        target = re.sub(r"(/index)?\.md$", "", target)
    if target in IN_HELP:
        return f'data-h="{target}#{anchor}"' if anchor else f'data-h="{target}"'
    url = SITE + ("" if target in ("index", ".") else target + "/") + (f"#{anchor}" if anchor else "")
    return f'href="{url}" target="_blank" rel="noopener"'


def page_html(page: str) -> tuple[str, str]:
    """(title, HTML) of a manual page; every h2/h3 with what follows it is a <section data-a="anchor">."""
    md = markdown.Markdown(extensions=EXTENSIONS, extension_configs={"toc": {"permalink": False}})
    html = md.convert(_source(page))
    m = re.match(r'\s*<h1 id="[^"]*">(.*?)</h1>\s*', html, re.DOTALL)
    title, html = (re.sub(r"<[^>]+>", "", m.group(1)), html[m.end():]) if m else (page, html)
    html = re.sub(r'<a href="([^"]*)"', lambda a: f"<a {_link(page, a.group(1))}", html)
    html = re.sub(r' data-search="[^"]*"', "", html)  # for the filter of the site's settings page
    parts = re.split(r'(?=<h[23] id=")', html)
    out = [f'<section data-a="">{parts[0].strip()}</section>'] if parts[0].strip() else []
    for p in parts[1:]:
        anchor = re.match(r'<h[23] id="([^"]*)"', p).group(1)
        out.append(f'<section data-a="{anchor}">{p.strip()}</section>')
    return title, "\n".join(out)


def build() -> dict:
    pages = []
    for group, names in PAGES.items():
        for name in names:
            title, html = page_html(name)
            pages.append({"path": name, "group": group, "title": title, "html": html})
    return {"site": SITE, "pages": pages}


def text() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=0) + "\n"


def main() -> None:
    OUT.write_text(text(), encoding="utf-8", newline="\n")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size // 1024} kB, "
          f"{sum(len(p) for p in PAGES.values())} pages")


if __name__ == "__main__":
    main()
