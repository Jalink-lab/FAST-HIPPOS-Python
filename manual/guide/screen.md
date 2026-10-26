# A screen of many images

A screen usually goes like this: **one (stitched) image at a time**, analyzed as soon as it has been imaged, its hits
photoactivated on the microscope, and then the next image. Afterwards, or while the screen goes on, you want to
compare all images.

That is how every analysis in FAST-HIPPOS works. Everything you analyze belongs to an **experiment**: a folder (the
*experiment folder*) with one folder per **image**, and an overview that compares the images. Every image is analyzed
in a run of its own, with its own hit list and `.rgn` files. There is no separate mode for a single image: with one
image you have an experiment of one image, and its overview is just short.

## Setting it up

1. In the *Images* card, choose an **Experiment folder** (e.g. `D:\screens\ADRB2 screen`). It may be empty, and you
   use the same folder for the whole screen. If you add images without choosing one, FAST-HIPPOS proposes a folder
   *FAST-HIPPOS* next to the images.
2. Add the first image (or several: all are analyzed one after the other). Each image gets a row with a tick box,
   its name (its folder `<experiment folder>\<name>`; by default the file name, type another to change it) and a
   **label** if you like: its condition, plate or library part. The label shows in the experiment overview.
3. **▶ Run analysis**. When the run is done, the `.rgn` files of the image are in its folder; see
   [Back to the microscope](microscope.md).
4. For the next image, click **＋ New image** (top right of the window). This keeps all settings, but empties the
   Images list, so that **▶ Run analysis** analyzes only the new image. Add it and run. The images that were already
   analyzed stay in the experiment and in its overview.

Images do not have to come from one folder: the experiment overview compares images from different input folders, and
its *Source* column says where each was read from.

The Images list holds the images **to analyze**. An image that already has results in the experiment folder is
**unticked** and says *✓ has results*; tick it to analyze it again, which replaces its results (its old results wait
in `_previous_run` until the new run is complete). Names, labels and ticks survive a reload of the browser tab.

<figure markdown>
![The Images card with an experiment folder](../images/gui_experiment.png){ .shot width="560" }
</figure>

The bar at the top of the window shows where you are: **Setup**, **Overview** (the overview of the whole experiment)
and **Image** (the dashboard of one image). The menu of **Image** lists every analyzed image of the experiment with its
label and hits. Choosing one makes it the **current image**: it is shown under *Image*, and *Re-apply this image*
redoes its screening. The dashboards of the last two images stay open, so you can switch back at once. Choosing an
image in the top bar does not change the Images list.

Every run (and every re-apply) of an image updates the overview of the experiment: `index.html` in the experiment
folder. **Overview** in the bar at the top shows it.

```text
ADRB2 screen\                  ← the experiment folder
    index.html                 ← the overview of all images
    experiment_summary.tsv     ← its images table
    plate 1\                   ← the folder of one image (its run)
        index.html, HITS_plate 1.rgn, ...
        plate 1\dashboard.html
    plate 2\
        ...
```

An image is a folder directly inside the experiment folder that holds a complete run; the images are listed by
name, with numbers in order (*plate 2* before *plate 10*). Other folders, and folders whose
name starts with `_`, are left out. To leave out an image, move its folder out of the experiment folder; the overview
changes at the next run, or at once with `fast-hippos-cli experiment <folder>` (see
[the command line](../reference/command-line.md)).

!!! warning "Give every image its own folder"
    An image is always a folder *inside* the experiment folder. FAST-HIPPOS refuses to run into the experiment
    folder itself, and warns when results are written somewhere else: such a run is not part of the experiment.

!!! note "Hits are per image"
    Hit criteria, random hits, sorting and the `.rgn` files belong to an image: there is no combined hit list over
    images, because they are different specimens. To compare images, use the experiment overview.

## The experiment overview { #the-experiment-overview }

<figure markdown>
![The overview of an experiment](../images/experiment.png){ .shot }
</figure>

It is described on [the overviews page](overview.md). What is specific to an experiment:

- the top bar counts the images, cells and hits, and shows when the first and the last image were analyzed
  (or last re-applied);
- the images table has an **Image** column (named as in the window; click it for the dashboard), a **Label** column
  and a **Source** column (the folder the image was read from); the hits table and the exported tables have them too;
- the quality flags compare every image with all images of the experiment (e.g. *few cells* means fewer than in the
  other images);
- *Files ▾* (top right) holds the files of the experiment, such as the summary table;
- *Export* saves `.rgn` files and tables per image. It has no route through the hits of several images together:
  the images are different specimens.

Clicking an image opens its dashboard. Changing the screening in a dashboard and applying it re-applies that image,
and so updates the experiment overview too. Images that were not screened show '–' for the hits.

## Are the images comparable? { #are-the-samples-comparable }

The results of two images can only be compared when both were analyzed with the same settings. FAST-HIPPOS checks
this in two places:

- **The experiment overview** shows a warning at the top when the images were not all analyzed with the same
  settings, and lists which settings differ in which images.
- **The window** warns in the Run card when images of the experiment were analyzed with other settings than those
  in the window:

<figure markdown>
![The warning in the Run card](../images/gui_experiment_differs.png){ .shot width="560" }
</figure>

Not compared are the settings that do not change the results: the images and folders, the labels, the
display settings (except *Time smoothing*), the `.rgn` settings (file size, route, axes), the Cellpose environments,
hand-picked hits, and the [settings of single images](own-settings.md), which are deliberate differences. When the
hit criteria differ, the *Cells* panel draws no threshold lines.

**↻ Re-apply all images** (in the Run card, next to *Re-apply this image*) makes them the same: it re-applies the
stimulation, screening and display settings of the window to every image, one after the other, and then updates the
experiment overview once. Each image keeps its own segmentation and traces, its label, its hand-picked hits and its
own settings; an image of another type (e.g. ratio data among lifetime images) also keeps its quality gates, hit
criteria and colour range, which are in the units of its values. It takes seconds per image. An image that cannot be
re-applied keeps its earlier results and settings; the experiment overview names it, and `experiment_log.txt` says
why. Settings that only a new run changes (segmentation, traces, image type, …) can only be made the same by
analyzing the image again.

<figure markdown>
![The Run card with an experiment](../images/gui_run_experiment.png){ .shot width="560" }
</figure>

!!! tip "Changing the hit criteria during a screen"
    Re-applying all images also rewrites their `.rgn` files. Images that were already photoactivated keep their
    cells, of course: the new hit lists then no longer match what happened on the microscope. Keep the hit criteria of
    a screen fixed once the first image has been photoactivated, or note which images were done with which criteria.

## The example

The [example data](../start/first-analysis.md) are an experiment of three images (*library part 1–3*), analyzed with
the settings of the example. The screenshots on this page show it.
