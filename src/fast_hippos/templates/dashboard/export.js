// ---------------------------------------------------------------- downloads
const cellText = (k, i) => { const v = C[k][i]; return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v)) ? "" : v; };
const columnKeys = () => Object.keys(C).filter(k => C[k] && C[k].length === N);
function exportCSV() {
  const keys = columnKeys(), lines = [["value_at_frame_" + S.frame, ...keys].join("\t")];
  for (const i of tableRows) lines.push([val(S.frame, i), ...keys.map(k => cellText(k, i))].join("\t"));
  download(`${D.name}_cells_${S.rows}.tsv`, lines.join("\n"), "text/tab-separated-values");
}
function exportHitsTSV() {
  const keys = columnKeys(), lines = [["rank", ...keys].join("\t")];
  sortedHits().forEach((i, r) => lines.push([r + 1, ...keys.map(k => cellText(k, i))].join("\t")));
  download(`${D.name}_hits.tsv`, lines.join("\n"), "text/tab-separated-values");
}
function exportRGN() {
  const ids = [...S.sel].filter(i => C.abs_x_m[i] !== null); if (!ids.length) { alert("Select cells first (with stage positions)."); return; }
  download(`SELECTED_${D.name}.rgn`, rgnXml(ids.map(i => [C.abs_x_m[i], C.abs_y_m[i], `Cell_${C.cell[i]}`]), "selection"), "application/xml");
}
async function exportHitsRGN() {
  if (!nHits()) { alert("No hits."); return; }
  const route = SCR.route && !SCR.route.stale ? SCR.route : await computeRoute();
  let a = 1;
  route.chunks.forEach((chunk, k) => {
    const items = chunk.filter(i => C.abs_x_m[i] !== null).map(i => [C.abs_x_m[i], C.abs_y_m[i], `Cell_${C.cell[i]}`]);
    const name = `HITS_${D.name}_${a}-${a + items.length - 1}.rgn`; a += items.length;
    setTimeout(() => download(name, rgnXml(items, "hits"), "application/xml"), 350 * k);
  });
}
function tomlValue(v) { return v === null || v === undefined ? '""' : typeof v === "string" ? JSON.stringify(v) : Array.isArray(v) ? `[${v.map(tomlValue).join(", ")}]` : typeof v === "boolean" ? String(v) : String(+(+v).toPrecision(10)); }
// the screening settings as a TOML override for 'fast-hippos-cli reapply' (+ the hand-picked hits in selection mode)
function screeningToml() {
  const p = SCR.params, e = SCR.events, L = [], manualFile = `${D.name}_manual_hits.tsv`;
  L.push(`# Screening settings from the FAST-HIPPOS dashboard of '${D.name}'.`, "# Use them for all images of the output folder with:", "#   fast-hippos-cli reapply <config.toml> --override <this file>", "");
  if (eventsTouched) L.push("[events]", `stimulation_frame = ${tomlValue(e.stimulation)}`, `calibration_frame = ${tomlValue(e.calibration)}`, `baseline_only = ${e.baseline_only}`, `margin = ${e.margin}`, "");
  else L.push("# [events] unchanged: the automatic or manual frames of each image are kept", "");
  L.push("[display]", `smooth_traces = ${p.smooth_traces}`, "", "[screening]", "enabled = true", `logic = ${tomlValue(p.logic)}`,
    `response_window = ${p.response_window}`, `response_window_anchor = ${tomlValue(p.response_window_anchor)}`, `response_window_margin = ${p.response_window_margin}`,
    `baseline_calibration_diff = ${p.baseline_calibration_diff ? tomlValue(p.baseline_calibration_diff) : "[]"}`,
    `max_baseline_deviation = ${tomlValue(p.max_baseline_deviation)}`, `rise_time_fraction = ${p.rise_time_fraction}`,
    `additional_channel_metric = ${tomlValue(p.additional_channel_metric)}`, `classify_additional_channel = ${p.classify_additional_channel}`,
    `classification_threshold = ${tomlValue(p.classify_additional_channel ? p.classification_threshold : null)}`,
    `sort_by = ${tomlValue(p.sort_by)}`, `sort_descending = ${p.sort_descending}`, `max_hits_per_rgn = ${p.max_hits_per_rgn}`, `optimize_path = ${p.optimize_path}`,
    'random_hits = ""', `manual_hits = ${SCR.mode === "selection" ? tomlValue(manualFile) : '""'}`, "criteria = [");
  p.criteria.forEach(c => L.push(`  { metric = ${tomlValue(c.metric)}, op = ${tomlValue(c.op)}, value = ${tomlValue(c.value)}` + (c.op === "between" ? `, value2 = ${tomlValue(c.value2)}` : "") + `, logic = ${tomlValue(c.logic)} },`));
  L.push("]", "");
  let manual = null;
  if (SCR.mode === "selection") {
    L.splice(3, 0, `# Hits were chosen by hand: put '${manualFile}' (downloaded with this file) next to it.`);
    manual = ["image\tcell", ...[...SCR.manual].sort((a, b) => a - b).map(i => `${D.name}\t${C.cell[i]}`)].join("\n");
  }
  return { toml: L.join("\n"), manual, manualFile };
}
function exportTOML() {
  const { toml, manual, manualFile } = screeningToml();
  if (manual) setTimeout(() => download(manualFile, manual, "text/tab-separated-values"), 400);
  download(`screening_${D.name}.toml`, toml, "application/toml");
}

// ---------------------------------------------------------------- apply to the run (dashboard opened from the GUI)
async function guiApi(name, body = {}) {
  const r = await fetch("/api/" + name, { method: "POST", headers: { "Content-Type": "application/json", "X-FH-Token": window.FH_GUI.token }, body: JSON.stringify(body) });
  const j = await r.json(); if (!r.ok) throw new Error(j.error || r.statusText); return j;
}
// ---------------------------------------------------------------- apply (only when opened from the FAST-HIPPOS window)
// 'Apply to all images': these screening settings for all images of the output folder. 'Apply to this image only': the
// settings that can differ per image (stimulation settings, response window) become this image's own. Either way all
// images are re-applied, because the hit list and the .rgn files cover all of them.
const OWN_KEYS = { events: ["stimulation_frame", "calibration_frame", "baseline_only", "margin"], screening: ["response_window", "response_window_anchor", "response_window_margin"] };
const OWN_NAMES = { stimulation_frame: "stimulation frame", calibration_frame: "calibration frame", baseline_only: "baseline only", margin: "margin", sensitivity: "detection threshold",
  response_window: "response window", response_window_anchor: "response window anchor", response_window_margin: "response window margin" };
const ownValue = (v) => (v === null || v === undefined || v === "" ? "automatic" : v === true ? "yes" : v === false ? "no" : v);
const describeOwn = (own) => Object.values(own || {}).flatMap(sec => Object.entries(sec).map(([k, v]) => `${OWN_NAMES[k] || k} ${ownValue(v)}`));
// this image's own settings after applying: the ones it had, with the timing set here (if changed) and a response window
// that differs from the one this dashboard started with
function ownSettings() {
  const own = structuredClone(D.own_settings || {}), p = SCR.params, p0 = D.screen.params, e = SCR.events;
  if (eventsTouched) own.events = { ...(own.events || {}), stimulation_frame: e.baseline_only ? null : e.stimulation, calibration_frame: e.baseline_only ? null : e.calibration, baseline_only: e.baseline_only, margin: e.margin };
  for (const k of OWN_KEYS.screening) if (p[k] !== p0[k]) own.screening = { ...(own.screening || {}), [k]: p[k] };
  return own;
}
function ownToml(own) {
  const L = [`# Own settings of '${D.name}' from its dashboard`];
  for (const [sec, vals] of Object.entries(own)) { L.push("", `[${sec}]`); for (const [k, v] of Object.entries(vals)) L.push(`${k} = ${tomlValue(v)}`); }
  return L.join("\n") + "\n";
}
async function applyTo(scope) {
  const dashboard = decodeURIComponent(location.pathname.replace(/^\/files\//, ""));
  let info = null; try { info = (await guiApi("runinfo", { dashboard })).run; } catch { /* the questions below then name no images */ }
  const imgs = info ? info.images.map(i => i.name) : [], n = imgs.length;
  // the other images (of this run) with own settings: their own timing / response window stays theirs
  const owners = (sec) => Object.entries((info && info.image_settings) || {}).filter(([x, v]) => x !== D.name && v[sec] && (!n || imgs.includes(x))).map(([x]) => x);
  const list = imgs.slice(0, 12).map(x => "  • " + x).join("\n") + (n > 12 ? `\n  … and ${n - 12} more` : "");
  const all = n ? `all ${n} image${n === 1 ? "" : "s"}` : "all images";
  let toml, manual = null;
  if (scope === "image") {
    const own = ownSettings(), lines = describeOwn(own);
    if (!lines.length) { alert("Nothing to apply to this image only: change its stimulation frames (Timing) or its response window first."); return; }
    if (!confirm(`Use these settings for ${D.name} only?\n\n${lines.map(l => "  • " + l).join("\n")}\n\nThe other images keep their settings. `
        + `Criteria, quality gates and the other screening settings are not changed by this (use 'Apply to all images' for those). `
        + `Because the hit list and the .rgn files cover all images, ${all} are re-applied (segmentation and traces are kept); this dashboard reloads when it is done.\n\nContinue?`)) return;
    toml = ownToml(own);
  } else {
    const e = SCR.events, p = SCR.params, p0 = D.screen.params, mine = (D.own_settings && D.own_settings.screening) || {};
    const ownTiming = owners("events"), ownWindow = owners("screening");
    const timing = !eventsTouched ? "The stimulation and calibration frames of each image stay as they are (detected, set, or its own)."
      : `The timing set here (${e.baseline_only ? "baseline only" : `stimulation frame ${ownValue(e.stimulation)}, calibration frame ${ownValue(e.calibration)}`}) is used for all images, this one included`
        + (ownTiming.length ? `, except those with their own timing: ${ownTiming.join(", ")}.` : ".");
    const kept = OWN_KEYS.screening.filter(k => k in mine && p[k] === p0[k]), replaced = OWN_KEYS.screening.filter(k => k in mine && p[k] !== p0[k]);
    const windowNote = (kept.length ? `\n${D.name} keeps its own ${kept.map(k => `${OWN_NAMES[k]} ${mine[k]}`).join(", ")}.` : "")
      + (replaced.length ? `\nThe ${replaced.map(k => `${OWN_NAMES[k]} ${p[k]}`).join(", ")} set here is used for all images, ${D.name} included (instead of its own).` : "")
      + (ownWindow.length ? `\nImages that keep their own response window: ${ownWindow.join(", ")}.` : "");
    if (!confirm(`Use these screening settings for ${all} of this output folder${info ? ` (run of ${info.started})` : ""}?` + (n ? `\n\n${list}` : "")
        + `\n\n${timing}` + windowNote
        + "\n\nFor every image, stimulation detection, screening, hit lists, .rgn files and the dashboard are redone; segmentation and traces are kept. "
        + "This dashboard reloads when it is done.\n\nContinue?")) return;
    ({ toml, manual } = screeningToml());
  }
  const msg = $("applymsg"), btns = [$("scrapply"), $("scrapplyimg")];
  btns.forEach(b => { b.disabled = true; }); msg.textContent = "starting…";
  let run;
  try { run = (await guiApi("apply", { dashboard, toml, manual_tsv: manual, image: D.name, scope })).run_id; }
  catch (err) { msg.textContent = err.message; btns.forEach(b => { b.disabled = false; }); return; }
  const poll = async () => {
    let st; try { st = await guiApi("status", { since: 0 }); } catch { setTimeout(poll, 1500); return; }
    if (st.run_id !== run) { msg.textContent = "another run started"; btns.forEach(b => { b.disabled = false; }); return; }
    const last = st.lines.filter(l => / (INFO|WARNING|ERROR) /.test(l)).pop() || "";
    if (st.state === "running") { msg.textContent = "applying… " + last.replace(/^\S+ +\S+ +/, ""); setTimeout(poll, 800); return; }
    if (st.state === "done") { msg.textContent = "done, reloading…"; location.reload(); return; }
    msg.textContent = `${st.state}: ${st.lines.slice(-1)[0] || ""}`; btns.forEach(b => { b.disabled = false; });
  };
  poll();
}
