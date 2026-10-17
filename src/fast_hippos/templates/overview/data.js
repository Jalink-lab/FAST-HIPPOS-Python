// ---------------------------------------------------------------- data of the run and the state of the page
const D = JSON.parse($("fh-data").textContent);
const SCREEN = D.screening;
// images: per-cell columns (a sample of up to max_cells per image, all hits kept) and the response bands (5 x frames)
const IM = D.images.map((im, k) => {
  const cols = {}; for (const [n, v] of Object.entries(im.cells)) cols[n] = b64f32(v);
  const nShown = im.n_shown, rowOfCell = new Map();
  if (cols.cell) for (let i = 0; i < nShown; i++) rowOfCell.set(cols.cell[i], i);
  return { ...im, k, C: cols, B: b64f32(im.bands), BH: b64f32(im.bands_hits), rowOfCell };
});
const NI = IM.length;
const imgColor = (k) => css(`--img-${k % 8}`);
const UNIT = D.is_lifetime ? "ns" : "";
const hasStim = IM.some(im => im.events.stimulation !== null), hasCal = IM.some(im => im.events.calibration !== null);
const hasPositions = SCREEN && IM.some(im => im.has_positions || im.hits.length);
const EXTRA_TIPS = { area_px: "Cell area in pixels", mean_intensity: "Mean intensity of the cell", circularity: "Circularity 4πA/P² (1 = a perfect circle)" };
const METRIC_KEYS = [...Object.keys(D.metrics), "area_px", "mean_intensity", "circularity"]
  .filter(m => IM.some(im => im.C[m] && im.C[m].some(Number.isFinite)));
const metricTip = (m) => D.metrics[m] || EXTRA_TIPS[m] || "";
const FLAG_LABEL = { few_cells: "few cells", low_valid: "low fraction valid", no_stimulation: "no stimulation", no_calibration: "no calibration",
  event_offset: "stimulation at another frame", no_cal_response: "no calibration response", no_positions: "no stage positions", no_hits: "no hits" };

const S = {
  sel: new Set(IM.slice(0, 6).map(im => im.k)), hidden: new Set(), hover: -1, last: -1, sortCol: "index", sortDir: 1,
  metric: METRIC_KEYS.includes(D.response_metric) ? D.response_metric : (METRIC_KEYS[0] || ""), metricY: METRIC_KEYS.includes("baseline_mean") ? "baseline_mean" : (METRIC_KEYS[0] || ""),
  cmode: "dist", logx: false, logy: false, align: hasStim, hitsOnly: false, sameScale: false, hitsOpen: false,
};
// the selected images, in the order of the table; 'shown' leaves out the curves switched off in the legend
function selected() { return tableOrder().filter(k => S.sel.has(k)); }
function shown() { return selected().filter(k => !S.hidden.has(k)); }
const safeName = (s) => String(s).replace(/[<>:"/\\|?*]/g, "_").trim();
const tsvCell = (v) => v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v)) ? "" : String(v).replace(/[\t\n]/g, " ");

// ---------------------------------------------------------------- hover tip
const tipEl = $("tip");
function showTip(html, ev) {
  if (!html || !ev) { tipEl.style.display = "none"; return; }
  tipEl.innerHTML = html; tipEl.style.display = "block";
  tipEl.style.left = Math.min(ev.clientX + 14, innerWidth - tipEl.offsetWidth - 8) + "px";
  tipEl.style.top = Math.min(ev.clientY + 14, innerHeight - tipEl.offsetHeight - 8) + "px";
}
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function openCell(im, cell) { if (im.href) window.open(`${im.href}#cell=${cell}`, "_blank"); }
function setHover(k) { if (k === S.hover) return; S.hover = k; invalidate("tableHov", "resp", "metric", "maps"); }
