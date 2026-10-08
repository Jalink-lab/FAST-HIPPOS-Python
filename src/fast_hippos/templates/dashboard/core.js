// ---------------------------------------------------------------- data and shared state
const D = JSON.parse(document.getElementById("fh-data").textContent);
const $ = (id) => document.getElementById(id);
const N = D.n_cells, T = D.n_frames, FI = D.frame_interval;
const C = D.cells;

function b64bytes(s) { const b = atob(s); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }
function b64f32(s) { return s ? new Float32Array(b64bytes(s).buffer) : null; }
const KR = b64f32(D.kymo), KA = b64f32(D.additional);
const LUTS = {}; for (const [k, v] of Object.entries(D.luts)) LUTS[k] = b64bytes(v);
Object.keys(C).filter(k => k.startsWith("pass_")).forEach(k => delete C[k]);  // recomputed live
const HAS_ABS = (C.abs_x_m || []).some(v => v !== null);
const POSX = Float64Array.from(C.pos_x_px ?? C.centroid_x, v => v ?? NaN), POSY = Float64Array.from(C.pos_y_px ?? C.centroid_y, v => v ?? NaN);

// screening state (recomputed in the browser by FHScreen = templates/screening.js, identical to Python)
const SCR = {
  events: structuredClone(D.screen.events), params: structuredClone(D.screen.params),
  mode: "criteria", manual: new Set(), pass: {}, route: null, routeBusy: false,
};
SCR.params.criteria.forEach(c => { c.logic = (c.logic || SCR.params.logic || "OR").toUpperCase(); });
const SCR0 = JSON.stringify({ events: SCR.events, params: SCR.params, mode: SCR.mode });
let KS = KR, HIT = C.hit.map(Boolean), ORDER = D.order, EV = D.events;

const S = {
  frame: 0, hover: -1, sel: new Set(), lastClicked: -1, playing: false,
  lut: D.display.lut, dmin: D.display.min, dmax: D.display.max, bright: Math.pow(10, 0.2),
  isrc: "movie", outl: D.screening.enabled ? "hits" : "selection", tsrc: SCR.params.smooth_traces > 0 ? "smoothed" : "raw",
  show: "all", tcol: D.screening.enabled && D.screening.n_hits ? "hit" : "cell", tmode: N > 300 ? "bands" : "lines",
  sorted: true, rows: "all", sortCol: null, sortDir: 1, sx: "mean_intensity", sy: "@value", slogx: false, slogy: false,
  tool: "rect", showRoute: true, scalebar: true, fillMetric: "",
};
const K = () => (S.tsrc === "smoothed" ? KS : KR);
const val = (t, i) => K()[t * N + i];
function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
function cellColor(i, alpha = 1) { const h = (i * 137.508) % 360; return `hsla(${h.toFixed(1)},72%,58%,${alpha})`; }
function visible(i) { return S.show === "all" || (S.show === "hits" ? HIT[i] : S.sel.has(i)); }
const fmt = (v, d = 3) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  if (!Number.isFinite(v)) return v > 0 ? "∞" : "−∞";
  if (a >= 1e7 || (a < 1e-4 && v !== 0)) return v.toExponential(2);
  return a >= 1000 ? v.toFixed(Math.min(d, 1)) : (+v).toFixed(d);
};
const nHits = () => HIT.reduce((s, h) => s + (h ? 1 : 0), 0);

// ---------------------------------------------------------------- redraw scheduling
// Each panel registers named layers; invalidate() marks them, one animation frame redraws them in order.
const LAYERS = [];  // [name, fn]
function layer(name, fn) { LAYERS.push([name, fn]); }
const dirty = new Set();
let rafPending = false;
function invalidate(...names) { names.forEach(n => dirty.add(n)); if (!rafPending) { rafPending = true; requestAnimationFrame(flush); } }
function flush() {
  rafPending = false;
  const d = new Set(dirty); dirty.clear();
  for (const [name, fn] of LAYERS) if (d.has(name)) { try { fn(); } catch (e) { console.error(name, e); } }
}
const ALL = () => LAYERS.map(l => l[0]);
// groups of layers per kind of change
const ON = {
  frame: ["viewer", "tracesHov", "kymoOvl", "hist", "tableRows", "cell"],
  hover: ["viewerHov", "tracesHov", "kymoOvl", "scatterHov", "tableHov", "cell"],
  selection: ["viewerSel", "viewerHov", "tracesSel", "kymoOvl", "scatterSel", "hist", "tableRows", "cell", "screenSel"],
  hits: ["viewerSel", "viewerHov", "traces", "tracesSel", "kymo", "kymoOvl", "hist", "scatter", "scatterSel", "table", "cell"],
  display: ["viewer", "traces", "tracesSel", "tracesHov", "kymo", "kymoOvl", "hist", "scatter", "scatterSel", "scatterHov", "cell"],
};

// ---------------------------------------------------------------- frame, hover, selection
function setFrame(t) {
  t = Math.max(0, Math.min(T - 1, Math.round(t)));
  if (t === S.frame) return;
  S.frame = t; $("frame").value = t; updateTimeLabel();
  invalidate(...ON.frame);
  if (S.sy === "@value" || S.sx === "@value" || S.sx === "@additional" || S.sy === "@additional") invalidate("scatter", "scatterSel", "scatterHov");
}
function setHover(i, ev) {
  if (i !== S.hover) { S.hover = i; invalidate(...ON.hover); }
  showTip(i, ev);
}
function select(i, ev) {
  if (i < 0) { if (!(ev && (ev.ctrlKey || ev.metaKey))) S.sel.clear(); }
  else if (ev && (ev.ctrlKey || ev.metaKey)) { S.sel.has(i) ? S.sel.delete(i) : S.sel.add(i); }
  else S.sel = new Set([i]);
  S.lastClicked = i;
  selectionChanged();
}
function selectMany(list, add) { if (!add) S.sel.clear(); list.forEach(i => S.sel.add(i)); selectionChanged(); }
function selectionChanged() {
  invalidate(...ON.selection);
  if (S.show === "sel") invalidate("traces", "hist", "scatter", "kymo");
  if (S.rows === "sel") invalidate("table");
  updateChips();
}

const tip = $("tip");
function showTip(i, ev) {
  if (i < 0 || !ev) { tip.style.display = "none"; return; }
  const v = val(S.frame, i);
  tip.innerHTML = `<b>Cell ${C.cell[i]}</b> · ${fmt(v)} ${D.is_lifetime ? "ns" : ""}` + (HIT[i] ? ` · <span class="h">hit</span>` : "") +
    (C.response_max_diff ? `<br><span class="muted">max Δ ${fmt(C.response_max_diff[i])} · baseline ${fmt(C.baseline_mean[i])}</span>` : "");
  tip.style.display = "block";
  tip.style.left = Math.min(ev.clientX + 14, innerWidth - tip.offsetWidth - 8) + "px";
  tip.style.top = Math.min(ev.clientY + 14, innerHeight - tip.offsetHeight - 8) + "px";
}

// ---------------------------------------------------------------- LUT helpers
function lutRGB(v, out = [0, 0, 0]) {
  const L = LUTS[S.lut]; let x = (v - S.dmin) / (S.dmax - S.dmin); x = x < 0 ? 0 : x > 1 ? 1 : x;
  const j = Math.round(x * 255) * 3; out[0] = L[j]; out[1] = L[j + 1]; out[2] = L[j + 2]; return out;
}
function hexToRgb(h) { const c = document.createElement("canvas").getContext("2d"); c.fillStyle = h; const s = c.fillStyle; return s.startsWith("#") ? [parseInt(s.slice(1, 3), 16), parseInt(s.slice(3, 5), 16), parseInt(s.slice(5, 7), 16)] : [255, 255, 255]; }
function withAlpha(color, a) { const [r, g, b] = hexToRgb(color); return `rgba(${r},${g},${b},${a})`; }

// ---------------------------------------------------------------- shift-drag selection shapes (rectangle or lasso)
// attachSelector(element, onDone(polygon in element px, additive)); draws the shape in an SVG overlay
function attachSelector(el, svg, onDone, opts = {}) {
  let drag = null;
  const pt = (e) => { const r = el.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  el.addEventListener("pointerdown", (e) => {
    if (!e.shiftKey || e.button !== 0) return;
    e.preventDefault(); e.stopPropagation(); el.setPointerCapture(e.pointerId);
    const p = pt(e); drag = { pts: [p], tool: opts.rangeOnly ? "range" : S.tool };
  }, true);
  el.addEventListener("pointermove", (e) => {
    if (!drag) return; e.stopPropagation();
    const p = pt(e); drag.tool === "lasso" ? drag.pts.push(p) : (drag.pts[1] = p);
    drawShape(svg, drag, el);
  }, true);
  el.addEventListener("pointerup", (e) => {
    if (!drag) return; e.stopPropagation();
    const d = drag; drag = null; svg.innerHTML = "";
    let poly = d.pts;
    if (d.tool !== "lasso" && d.pts.length > 1) {
      const [a, b] = d.pts, h = el.getBoundingClientRect().height;
      poly = d.tool === "range" ? [[a[0], 0], [b[0], 0], [b[0], h], [a[0], h]] : [a, [b[0], a[1]], b, [a[0], b[1]]];
    }
    if (poly.length > 2) onDone(poly, e.ctrlKey || e.metaKey);
  }, true);
}
function drawShape(svg, d, el) {
  const h = el.getBoundingClientRect().height;
  let pts = d.pts;
  if (d.tool !== "lasso" && pts.length > 1) { const [a, b] = pts; pts = d.tool === "range" ? [[a[0], 0], [b[0], 0], [b[0], h], [a[0], h]] : [a, [b[0], a[1]], b, [a[0], b[1]]]; }
  svg.innerHTML = `<polygon points="${pts.map(p => p.join(",")).join(" ")}" class="selshape"/>`;
}
function inPolygon(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
