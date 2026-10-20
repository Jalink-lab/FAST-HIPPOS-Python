// The filter of the settings reference: shows the settings whose name, key or text contain all typed words
// (Material loads pages without a full reload, so this hooks into its document$ stream)
function fhFilter() {
  const box = document.getElementById("fh-filter");
  if (!box) return;
  const run = () => {
    const words = box.value.toLowerCase().split(/\s+/).filter(Boolean);
    document.querySelectorAll("table.fh-settings").forEach(t => {
      let shown = 0;
      t.querySelectorAll("tbody tr").forEach(tr => {
        const ok = words.every(w => tr.dataset.search.includes(w));
        tr.classList.toggle("fh-hidden", !ok); shown += ok;
      });
      t.classList.toggle("fh-hidden", !shown);
      const h = t.previousElementSibling; if (h && h.classList.contains("fh-group")) h.classList.toggle("fh-hidden", !shown);
    });
    document.querySelectorAll(".md-typeset h2").forEach(h2 => {  // a card heading without visible settings
      let el = h2.nextElementSibling, any = false;
      while (el && el.tagName !== "H2") { if (el.matches("table.fh-settings:not(.fh-hidden)")) any = true; el = el.nextElementSibling; }
      h2.classList.toggle("fh-hidden", !any && words.length > 0);
    });
  };
  box.addEventListener("input", run);
}
if (window.document$) document$.subscribe(fhFilter); else document.addEventListener("DOMContentLoaded", fhFilter);

// The movie of the home page: one image per frame (tools/manual/make_landing_images.py), with the label, the colour
// scale and a timeline as page text over it, so that they stay sharp. It starts by itself (also when the system asks
// for reduced motion, as many work PCs do: it is short and has a pause button), and pauses while the mouse is on it
// or with the button.
let fhMovieTimer = null;
function fhMovie() {
  clearTimeout(fhMovieTimer);
  const box = document.querySelector(".fh-movie[data-movie]");
  if (!box) return;
  const base = box.dataset.movie, img = box.querySelector("img"), label = box.querySelector(".fh-movie-label");
  const btn = box.querySelector(".fh-movie-play"), tl = box.querySelector(".fh-timeline");
  fetch(base + "movie.json").then(r => r.json()).then(m => {
    const pct = (k) => (100 * k) / m.n, segs = tl.querySelectorAll(".fh-tl-seg"), cursor = tl.querySelector(".fh-tl-cursor");
    const stim = m.stimulation ?? 0, cal = m.calibration ?? m.n;
    [stim, cal - stim, m.n - cal].forEach((w, i) => { segs[i].style.width = pct(w) + "%"; });
    const ends = box.querySelectorAll(".fh-cb-ends span"); ends[0].textContent = m.min.toFixed(1); ends[1].textContent = m.max.toFixed(1);
    const frames = Array.from({ length: m.n }, (_, k) => { const im = new Image(); im.src = `${base}f${String(k).padStart(2, "0")}.webp`; return im; });
    let k = m.still, playing = true, hover = false;
    const show = () => {
      img.src = frames[k].src;
      const phase = m.labels[k];
      label.innerHTML = `frame ${m.frames[k] + 1} · ` + (phase === "hits found" ? "<b>hits found</b>" : phase);
      cursor.style.left = pct(k + 0.5) + "%";
    };
    const step = () => {
      if (!document.body.contains(box)) return;  // another page was loaded
      if (playing && !hover) { k = (k + 1) % m.n; show(); }
      fhMovieTimer = setTimeout(step, playing && !hover ? m.durations[k] : 250);
    };
    const setButton = () => { btn.textContent = playing ? "⏸" : "⏵"; btn.setAttribute("aria-label", playing ? "Pause" : "Play"); };
    btn.onclick = () => { playing = !playing; setButton(); };
    box.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") hover = true; });  // not a tap on a phone
    box.addEventListener("pointerleave", () => { hover = false; });
    btn.hidden = false; tl.hidden = false; setButton();
    if (playing) k = 0;
    show(); fhMovieTimer = setTimeout(step, m.durations[k]);
  }).catch(() => { /* without the timing: the still frame stays */ });
}
if (window.document$) document$.subscribe(fhMovie); else document.addEventListener("DOMContentLoaded", fhMovie);
