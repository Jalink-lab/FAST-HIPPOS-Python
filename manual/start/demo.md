---
hide: [navigation, toc]
---

# Try it in your browser

These are the real results of the [example analysis](first-analysis.md): the overview of the run and the dashboards
of its three images, exactly as FAST-HIPPOS writes them. They run completely in your browser; nothing is installed or
uploaded. Each dashboard holds the full images (about 25 MB), so it may take a few seconds to load.

The experiment: Cos7 cells with the cAMP sensor EpacH250, with about 5 % ADRB2 knock-out cells among them, are
stimulated with isoproterenol; the hits are the cells that hardly respond, i.e. most likely the knock-out cells.
Go to frame 15 in a dashboard and look at the scatter plot: most hits carry the marker of the knock-out cells.
See [what the experiment is about](first-analysis.md#what-the-experiment-is-about).

=== "Overview of the experiment"

    <div class="fh-demo-bar" markdown>
    [Open in a new tab :material-open-in-new:](../demo/experiment/index.html){ .md-button target="_blank" }
    </div>
    <iframe class="fh-demo" src="../../demo/experiment/index.html" loading="lazy" title="Overview of the example experiment"></iframe>

    Select images in the table to compare them, switch between *distribution* and *scatter*, hover over a hit in
    the maps. The image names link to the dashboards. See [the run overview](../guide/overview.md).

=== "Dashboard of one image"

    <div class="fh-demo-bar" markdown>
    [Open in a new tab :material-open-in-new:](../demo/experiment/example_screen_1/example_screen_1/dashboard.html){ .md-button target="_blank" }
    </div>
    <iframe class="fh-demo" src="../../demo/experiment/example_screen_1/example_screen_1/dashboard.html" loading="lazy" title="Dashboard of example_screen_1"></iframe>

    Try this:

    - Hover over the cells; ++ctrl++ + scroll zooms, dragging pans, ++space++ plays the time-lapse.
    - Drag the black marker of the hit criterion (*Hits from*, at the bottom of the Screening pane) and watch the hits
      change.
    - Click a cell, a trace, a kymograph column or a point in the scatter plot: the same cell is selected everywhere.

    See [the dashboard](../guide/dashboard.md) for all it can do. The buttons that re-apply the screening to all images
    only appear in dashboards opened from the FAST-HIPPOS window.

!!! note "Larger screens"
    The dashboard and the overview are made for a computer screen; on a phone, use *Open in a new tab* and turn the
    phone sideways.
