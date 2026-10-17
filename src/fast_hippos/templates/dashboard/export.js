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
  L.push(`# Screening settings from the FAST-HIPPOS dashboard of '${D.name}'.`, "# Apply to the whole run with:", "#   fast-hippos-cli reapply <config.toml> --override <this file>", "");
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
async function applyToRun() {
  const dashboard = decodeURIComponent(location.pathname.replace(/^\/files\//, ""));
  let info = null; try { info = (await guiApi("runinfo", { dashboard })).run; } catch { /* the question below then names no images */ }
  const imgs = info ? info.images.map(i => i.name) : [];
  const list = imgs.slice(0, 12).map(n => "  • " + n).join("\n") + (imgs.length > 12 ? `\n  … and ${imgs.length - 12} more` : "");
  if (!confirm(`Apply these screening settings to the whole run${info ? ` of ${info.started}` : ""} in this output folder`
      + (imgs.length ? `, ${imgs.length} image${imgs.length === 1 ? "" : "s"}:\n\n${list}` : "?") + "\n\nFor every image, stimulation detection, "
      + "screening, hit lists, .rgn files and the dashboard are redone with these settings; segmentation and traces are kept. "
      + "This dashboard reloads when it is done.\n\nContinue?")) return;
  const { toml, manual } = screeningToml(), msg = $("applymsg"), btn = $("scrapply");
  btn.disabled = true; msg.textContent = "starting…";
  let run;
  try { run = (await guiApi("apply", { dashboard, toml, manual_tsv: manual })).run_id; }
  catch (e) { msg.textContent = e.message; btn.disabled = false; return; }
  const poll = async () => {
    let st; try { st = await guiApi("status", { since: 0 }); } catch { setTimeout(poll, 1500); return; }
    if (st.run_id !== run) { msg.textContent = "another run started"; btn.disabled = false; return; }
    const last = st.lines.filter(l => / (INFO|WARNING|ERROR) /.test(l)).pop() || "";
    if (st.state === "running") { msg.textContent = "applying… " + last.replace(/^\S+ +\S+ +/, ""); setTimeout(poll, 800); return; }
    if (st.state === "done") { msg.textContent = "done, reloading…"; location.reload(); return; }
    msg.textContent = `${st.state}: ${st.lines.slice(-1)[0] || ""}`; btn.disabled = false;
  };
  poll();
}
