// ---------------------------------------------------------------- downloads
function download(name, text, type) { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); }
function uuid() { return crypto.randomUUID ? crypto.randomUUID() : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === "x" ? r : (r & 3 | 8)).toString(16); }); }
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
function rgnXml(items, name) {
  let body = "", stack = "";
  items.forEach(([x, y, tag], n) => { const id = uuid();
    body += `<Item${n}>\n<Number>${n + 1}</Number>\n<Tag>${tag}</Tag>\n<Identifier>${id}</Identifier>\n<Type>Point</Type>\n<Fill>R:1,G:0,B:0,A:0</Fill>\n<Font />\n<Verticies>\n<Items>\n<Item0>\n<X>${x.toFixed(10)}</X>\n<Y>${y.toFixed(10)}</Y>\n</Item0>\n</Items>\n</Verticies>\n<DecoratorColors>\n<Items />\n</DecoratorColors>\n<ExtendedProperties>\n<Items />\n</ExtendedProperties>\n</Item${n}>\n`;
    stack += `<Entry Identifier="${id}" Begin="0.0000000000" End="0.0000000000" SectionCount="0" ReferenceX="0.0000000000" ReferenceY="0.0000000000" FocusStabilizerOffset="0.0000000000" FocusStabilizerOffsetFixed="false" StackValid="false" Marked="false" />\n`; });
  return `<StageOverviewRegions>\n<Regions>\n<ShapeList>\n<Items>\n<Item0>\n<Name>${name}</Name>\n<Identifier>${uuid()}</Identifier>\n<Type>CompoundShape</Type>\n<Font />\n<Verticies>\n<Items />\n</Verticies>\n<DecoratorColors>\n<Items />\n</DecoratorColors>\n<ExtendedProperties>\n<Items />\n</ExtendedProperties>\n<Children>\n<Items>\n${body}</Items>\n</Children>\n</Item0>\n</Items>\n<FillMaskMode>None</FillMaskMode>\n<VertexUnitMode>Pixels</VertexUnitMode>\n</ShapeList>\n</Regions>\n<StackList>\n${stack}</StackList>\n</StageOverviewRegions>\n`;
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
function exportTOML() {
  const p = SCR.params, e = SCR.events, L = [], manualFile = `${D.name}_manual_hits.tsv`;
  L.push(`# Screening settings from the FAST-HIPPOS dashboard of '${D.name}'.`, "# Apply to the whole run with:", "#   fast-hippos reapply <config.toml> --override <this file>", "");
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
  if (SCR.mode === "selection") {
    L.splice(3, 0, `# Hits were chosen by hand: put '${manualFile}' (downloaded with this file) next to it.`);
    const rows = ["image\tcell", ...[...SCR.manual].sort((a, b) => a - b).map(i => `${D.name}\t${C.cell[i]}`)];
    setTimeout(() => download(manualFile, rows.join("\n"), "text/tab-separated-values"), 400);
  }
  download(`screening_${D.name}.toml`, L.join("\n"), "application/toml");
}
