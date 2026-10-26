# A screen of several samples

A screen usually goes like this: **one (stitched) image per sample**, every sample analyzed as soon as it has been
imaged, its hits photoactivated on the microscope, and then the next sample. Afterwards, or while the screen goes
on, you want to compare all samples.

That is how every analysis in FAST-HIPPOS works. Everything you analyze belongs to an **experiment**: a folder (the
*experiment folder*) with one folder per **sample**, and an overview that compares the samples. Every image is a
sample, analyzed in a run of its own, with its own hit list and `.rgn` files. There is no separate mode for a single
image: with one image you have an experiment of one sample, and its overview is just short.

## Setting it up

1. In the *Images* card, choose an **Experiment folder** (e.g. `D:\screens\ADRB2 screen`). It may be empty, and you
   use the same folder for the whole screen. If you add images without choosing one, FAST-HIPPOS proposes a folder
   *FAST-HIPPOS* next to the images.
2. Add the image of the first sample (or several images: each is a sample). Each sample gets a row with its name,
   its folder `<experiment folder>\<name>` (the image name; type another to change it), and a **label** if you like:
   its condition, plate or library part. The label shows in the experiment overview.
3. **▶ Run analysis**. When the run is done, the `.rgn` files of the sample are in its folder; see
   [Back to the microscope](microscope.md).
4. For the next sample, click **＋ New sample** (top right of the window, or in the sample menu of the top bar).
   This keeps all settings, but empties the image list, the [settings of single images](own-settings.md) and a
   file of hand-picked hits. Add the image of the next sample, and run.

With several images in the list, **▶ Run analysis** analyzes the samples one after the other, each as a run of its
own, and updates the experiment overview once at the end. A sample that already has results in the experiment folder
is replaced; its old results wait in `_previous_run` until the new run is complete.

The bar at the top of the window shows where you are: **Experiment** (the overview of all samples), **Sample** (the
overview of one sample, with a menu of all samples with their label and hits) and **Image** (the dashboard of one
image). Choosing another sample in the menu, or clicking a sample in the experiment overview, loads it into the
window: its images, folder, label and the settings of its single images; the analysis settings stay those of the
window. When the images in the window were not analyzed yet, FAST-HIPPOS asks first.

<figure markdown>
![The Images card with an experiment folder](../images/gui_experiment.png){ .shot width="560" }
</figure>

Every run (and every re-apply) of a sample updates the overview of the experiment: `index.html` in the experiment
folder. **Experiment** in the bar at the top shows it.

```text
ADRB2 screen\                  ← the experiment folder
    index.html                 ← the overview of all samples
    experiment_summary.tsv     ← its images table
    plate 1\                   ← the folder of one sample (its run)
        index.html, HITS_plate 1.rgn, ...
        plate 1\dashboard.html
    plate 2\
        ...
```

A sample is a folder directly inside the experiment folder that holds a complete run; the samples are listed by
name, with numbers in order (*plate 2* before *plate 10*). Other folders, and folders whose
name starts with `_`, are left out. To leave out a sample, move its folder out of the experiment folder; the overview
changes at the next run, or at once with `fast-hippos-cli experiment <folder>` (see
[the command line](../reference/command-line.md)).

!!! warning "Give every sample its own folder"
    A sample is always a folder *inside* the experiment folder. FAST-HIPPOS refuses to run into the experiment
    folder itself, and warns when results are written somewhere else: such a run is not part of the experiment.

!!! note "Hits are per sample"
    Hit criteria, random hits, sorting and the `.rgn` files belong to a sample: there is no combined hit list over
    samples, because they are different specimens. To compare samples, use the experiment overview.

## The experiment overview

<figure markdown>
![The overview of an experiment](../images/experiment.png){ .shot }
</figure>

It works like [the overview of a sample](overview.md), with the images of all samples together:

- the top bar counts the samples, images, cells and hits, and shows when the first and the last sample were analyzed
  (or last re-applied);
- the images table has a **Sample** column (click it for the overview of that sample) and a **Label** column; the
  hits table and the exported tables have them too;
- the quality flags compare every image with all images of the experiment (e.g. *few cells* means fewer than in the
  other samples);
- *Samples* (top right) opens the overview of every sample, and the summary table of the experiment;
- *Export* saves `.rgn` files and tables per image, as in the overview of a sample. It has no route through the hits of
  several images together: the samples are different specimens.

Clicking an image opens its dashboard, as in the overview of its sample. Loading a sample into the window takes over
its label; the Run card warns when the label in the window differs. Changing the screening in a dashboard and
applying it re-applies that sample, and so updates the experiment overview too.

## Are the samples comparable?

The results of two samples can only be compared when both were analyzed with the same settings. FAST-HIPPOS checks
this in two places:

- **The experiment overview** shows a warning at the top when the samples were not all analyzed with the same
  settings, and lists which settings differ in which samples.
- **The window** warns in the Run card when samples of the experiment were analyzed with other settings than those
  in the window:

<figure markdown>
![The warning in the Run card](../images/gui_experiment_differs.png){ .shot width="560" }
</figure>

Not compared are the settings that do not change the results: the images and folders, the sample label, the
display settings (except *Time smoothing*), the `.rgn` settings (file size, route, axes), the Cellpose environments,
hand-picked hits, and the [settings of single images](own-settings.md), which are deliberate differences. When the
hit criteria differ, the *Cells* panel draws no threshold lines.

**↻ Re-apply all samples** (in the Run card, next to *Re-apply this sample*) makes them the same: it re-applies the stimulation, screening and
display settings of the window to every sample, one after the other, and then updates the experiment overview once.
Each sample keeps its own segmentation and traces, its sample label, its hand-picked hits and the settings of its
single images; a sample of another image type (e.g. ratio data among lifetime samples) also keeps its quality
gates, hit criteria and colour range, which are in the units of its values. It takes seconds per sample. A sample that cannot be re-applied keeps its earlier results and settings; the
experiment overview names it, and `experiment_log.txt` says why. Settings that only a new run changes (segmentation, traces, image type, …) can only be
made the same by running the sample again.

<figure markdown>
![The Run card with an experiment](../images/gui_run_experiment.png){ .shot width="560" }
</figure>

!!! tip "Changing the hit criteria during a screen"
    Re-applying all samples also rewrites their `.rgn` files. Samples that were already photoactivated keep their
    cells, of course: the new hit lists then no longer match what happened on the microscope. Keep the hit criteria of
    a screen fixed once the first sample has been photoactivated, or note which samples were done with which criteria.

## The example

The [example data](../start/first-analysis.md) are an experiment of three samples: each of the three images is a
sample of its own (*library part 1–3*), analyzed with the settings of the example. The screenshots on this page show it.
