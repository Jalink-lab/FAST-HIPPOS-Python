// ---------------------------------------------------------------- header, theme, remembered state, start
function drawChips() {
  const cells = IM.reduce((s, im) => s + im.n_cells, 0), valid = IM.reduce((s, im) => s + im.n_valid, 0), hits = IM.reduce((s, im) => s + im.n_hits, 0);
  const chip = (html, tip) => `<span class="chip" title="${esc(tip)}">${html}</span>`;
  const ch = [
    ...(EXP ? [chip(`<b>${RUNS.length}</b> sample${RUNS.length === 1 ? "" : "s"}`, "Samples (runs) in this experiment folder: the output folders inside it")] : []),
    chip(`<b>${NI}</b> image${NI === 1 ? "" : "s"}`, EXP ? "Images of all samples" : "Images in this run"),
    chip(`<b>${cells.toLocaleString("en")}</b> cells · ${valid ? Math.round(100 * valid / cells) : 0} % valid`, "All cells of all images, and the percentage that passes the quality gates"),
  ];
  if (SCREEN) ch.push(`<span class="chip hit" title="Hits of all images, as a percentage of the valid cells"><b>${hits}</b> hits · ${valid ? (100 * hits / valid).toFixed(2) : 0} %</span>`);
  else ch.push(chip("no screening", "This run did not screen for hits: the page compares the samples"));
  if (D.unit) ch.push(chip(esc(D.unit), "What the values are"));
  if (EXP) { const t = RUNS.map(r => r.reapplied || r.started).filter(Boolean).sort(); if (t.length) ch.push(chip(`runs ${esc(t[0])} – ${esc(t[t.length - 1])}`, "When the samples were analyzed (or last re-applied): the first and the last")); }
  else if (D.started) ch.push(chip(`run ${esc(D.started)}${D.reapplied ? ` · re-applied ${esc(D.reapplied)}` : ""}`, "When the analysis ran, and when its screening was last re-applied"));
  if (S.sel.size && S.sel.size < NI) { const ks = selected(); ch.push(chip(`<b>${ks.length}</b> selected · ${ks.reduce((s, k) => s + IM[k].n_cells, 0).toLocaleString("en")} cells` + (SCREEN ? ` · ${ks.reduce((s, k) => s + IM[k].n_hits, 0)} hits` : ""), "The selected images")); }
  $("chips").innerHTML = ch.join("");
}
layer("chips", drawChips);

// display choices per page (localStorage) and the view across a reload, e.g. after a re-apply (sessionStorage)
const STORE = "fast-hippos-overview:" + location.pathname;
const readStore = (st) => { try { return JSON.parse(st.getItem(STORE) || "null"); } catch { return null; } };
const writeStore = (st, v) => { try { st.setItem(STORE, JSON.stringify(v)); } catch { /* storage unavailable */ } };
const PREF_KEYS = ["metric", "metricY", "cmode", "logx", "logy", "align", "hitsOnly", "sameScale", "hitsOpen", "sortCol", "sortDir"];
function restore() {
  const p = readStore(localStorage) || {};
  for (const k of PREF_KEYS) if (k in p && typeof p[k] === typeof S[k]) S[k] = p[k];
  if (!METRIC_KEYS.includes(S.metric)) S.metric = METRIC_KEYS[0] || ""; if (!METRIC_KEYS.includes(S.metricY)) S.metricY = METRIC_KEYS[0] || "";
  if (!COLS.some(c => c.key === S.sortCol)) { S.sortCol = "index"; S.sortDir = 1; }
  if (!hasStim) S.align = false;
  if (p.theme) document.documentElement.dataset.theme = p.theme;
  const s = readStore(sessionStorage);
  if (s && Array.isArray(s.sel)) { const byName = new Map(IM.map(im => [im.name, im.k])); S.sel = new Set(s.sel.map(n => byName.get(n)).filter(k => k !== undefined));
    S.hidden = new Set((s.hidden || []).map(n => byName.get(n)).filter(k => k !== undefined)); }
}
function save() {
  const p = { theme: document.documentElement.dataset.theme || "" }; for (const k of PREF_KEYS) p[k] = S[k];
  writeStore(localStorage, p);
  writeStore(sessionStorage, { sel: [...S.sel].map(k => IM[k].name), hidden: [...S.hidden].map(k => IM[k].name) });
}
addEventListener("pagehide", save); document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") save(); });

$("theme").onclick = () => {
  const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  document.documentElement.dataset.theme = cur === "light" ? "dark" : "light"; save(); invalidate(...ALL());
};
matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => invalidate(...ALL()));
addEventListener("resize", () => invalidate("resp", "metric", "maps"));
addEventListener("keydown", (e) => { if (e.key === "Escape" && !e.target.closest("input, select")) { S.sel = new Set(); selectionChanged(); } });

restore();
$("title").textContent = D.title; document.title = `${D.title} · FAST-HIPPOS ${EXP ? "experiment" : "overview"}`;
if (EXP) $("title").title = "The experiment folder: one sample (run) per folder inside it, the images of all samples together";
$("notes").innerHTML = (D.notes || []).map(n => `<div class="note-warn">⚠ ${esc(n)}</div>`).join("");
$("ver").textContent = `FAST-HIPPOS ${D.version}`;
$("logx").checked = S.logx; $("logy").checked = S.logy; $("hitsOnly").checked = S.hitsOnly; $("sameScale").checked = S.sameScale;
initTable(); initPanels(); initMaps(); initHits(); initExports();
invalidate(...ALL());
