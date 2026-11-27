// ---------------------------------------------------------------- scatter plot of any two per-cell quantities
const SP = new Plot([$("scb"), $("scs"), $("sch")], { l: 56, r: 12, t: 10, b: 32 });
// not useful as an axis; class_additional is shown as an outline instead
const SKIP = ["image", "cell", "tile", "hit", "valid", "response_rank", "bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1", "class_additional"];
const NUMERIC = Object.keys(C).filter(k => !SKIP.includes(k) && C[k].some(v => typeof v === "number"));
const VALUE_LABEL = D.is_lifetime ? "lifetime @ frame" : "value @ frame";
function scatterValues(key) {
  const o = new Float64Array(N);
  if (key === "@value") { const k = K(); for (let i = 0; i < N; i++) o[i] = k[S.frame * N + i]; return o; }
  if (key === "@additional") { for (let i = 0; i < N; i++) o[i] = KA[S.frame * N + i]; return o; }
  if (key === "@partner") { for (let i = 0; i < N; i++) o[i] = KOTHER[S.frame * N + i]; return o; }
  const a = C[key]; for (let i = 0; i < N; i++) o[i] = a[i] === null || a[i] === undefined ? NaN : a[i]; return o;
}
// per-cell quantities in the same unit as the traces (lifetime or ratio)
const VALUE_METRICS = ["baseline", "mean_during_response", "peak_during_response", "mean_during_calibration"];
const isValueAxis = (k) => k === "@value" || VALUE_METRICS.includes(k);
const scatterLabel = (k) => k === "@value" ? VALUE_LABEL : k === "@additional" ? "additional channel @ frame" : k === "@partner" ? `${D.partner.name} @ frame` : nameOf(k);
function drawScatter() {
  SP.resize(); SP.logx = S.slogx; SP.logy = S.slogy;
  const xs = scatterValues(S.sx), ys = scatterValues(S.sy), ids = [];
  for (let i = 0; i < N; i++) if (visible(i)) ids.push(i);
  // lifetime (or ratio) axes share the range of the colour scale, as in Traces and Distribution
  const [x0, x1] = isValueAxis(S.sx) && !S.slogx ? yRange() : finiteRange(xs, ids, S.slogx);
  const [y0, y1] = isValueAxis(S.sy) && !S.slogy ? yRange() : finiteRange(ys, ids, S.slogy);
  SP.range(x0, x1, y0, y1);
  const ctx = SP.clear(0); SP.axes(ctx, scatterLabel(S.sx), scatterLabel(S.sy)); ctx.save(); SP.clip(ctx);
  SP.pts = []; const base = css("--accent"), hit = css("--hit"), r = ids.length > 2000 ? 1.6 : 2.6;
  for (const pass of [0, 1]) for (const i of ids) {
    if ((pass === 0) === HIT[i]) continue;
    const xv = xs[i], yv = ys[i];
    if (!Number.isFinite(xv) || !Number.isFinite(yv) || (S.slogx && xv <= 0) || (S.slogy && yv <= 0)) continue;
    const x = SP.X(xv), y = SP.Y(yv); SP.pts.push([i, x, y]);
    ctx.fillStyle = HIT[i] ? hit : base; ctx.globalAlpha = HIT[i] ? 0.9 : 0.5; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
  }
  if (S.sclass && C.class_additional) {  // outline the additional-channel positive cells
    ctx.globalAlpha = 0.95; ctx.strokeStyle = css("--class-pos"); ctx.lineWidth = r > 2 ? 1.3 : 1;
    for (const [i, x, y] of SP.pts) if (C.class_additional[i] === 1) { ctx.beginPath(); ctx.arc(x, y, r + 1.6, 0, 7); ctx.stroke(); }
  }
  drawGates(ctx);
  ctx.restore(); ctx.globalAlpha = 1;
  SP.map = new Map(SP.pts.map(p => [p[0], p]));
}
// ---- gates: hit criteria drawn as a region of this plot (fast_hippos.screening.in_polygon / FHScreen.gatePass)
// A gate keeps its two metrics and whether each axis was logarithmic: its edges are straight in that space, so on
// other axis settings they are drawn curved (each edge in 24 steps).
let GATE_DRAW = false;
const gateMetric = (k) => CRIT_KEYS.includes(k);  // only values of the cell can be criteria (not the values at a frame)
function drawGates(ctx) {
  SCR.params.criteria.forEach((c, k) => {
    if (!FHScreen.isGate(c) || c.metric !== S.sx || c.metric2 !== S.sy) return;
    const { px, py } = FHScreen.gatePoints(c), back = (u, log) => (log ? Math.pow(10, u) : u), pts = [];
    for (let i = 0; i < px.length; i++) {
      const j = (i + 1) % px.length;
      for (let s = 0; s < 24; s++) { const f = s / 24; pts.push([SP.X(back(px[i] + f * (px[j] - px[i]), c.log_x)), SP.Y(back(py[i] + f * (py[j] - py[i]), c.log_y))]); }
    }
    ctx.globalAlpha = 1; ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath();
    ctx.fillStyle = withAlpha(css("--hit"), c.op === "inside" ? 0.08 : 0.03); ctx.fill();
    ctx.setLineDash(c.op === "inside" ? [] : [5, 4]); ctx.strokeStyle = css("--hit"); ctx.lineWidth = 1.6; ctx.stroke(); ctx.setLineDash([]);
    const top = pts.reduce((a, q) => (q[1] < a[1] ? q : a), pts[0]);
    ctx.font = "11px system-ui, sans-serif"; ctx.fillStyle = css("--hit"); ctx.textAlign = "left"; ctx.textBaseline = "bottom";
    ctx.fillText(`gate ${k + 1}${c.op === "outside" ? " (outside)" : ""}`, top[0] + 4, top[1] - 2);
  });
}
function gateState() {  // the Gate button: only for two per-cell metrics
  const ok = gateMetric(S.sx) && gateMetric(S.sy);
  $("sgate").disabled = !ok && !GATE_DRAW;
  $("sgate").title = ok ? "Draw a gate: a region of this plot that becomes a hit criterion (cells inside it pass). Works for any image when the screening is applied."
    : `A gate needs two values that criteria can use on the axes (not a value at a frame, nor a position): ${CRIT_KEYS.map(nameOf).join(", ")}`;
  $("sgate").classList.toggle("drawing", GATE_DRAW); $("sgate").textContent = GATE_DRAW ? "Cancel gate" : "✎ Gate";
  $("gatehint").textContent = GATE_DRAW ? `drag a ${S.tool === "lasso" ? "lasso" : "box"} around the cells (L: box/lasso, Esc: cancel)` : "";
  $("sch").closest(".stack").classList.toggle("drawgate", GATE_DRAW);
}
function setGateDraw(on) { GATE_DRAW = on; gateState(); }
function addGate(poly) {  // poly: in pixels of the plot
  setGateDraw(false); addGate.t = Date.now();
  const r = (v) => +v.toPrecision(6), polygon = poly.map(([x, y]) => [r(SP.iX(x)), r(SP.iY(y))]);
  if (polygon.some(q => !q.every(Number.isFinite))) return;
  SCR.params.criteria.push({ metric: S.sx, metric2: S.sy, op: "inside", value: null, value2: null, logic: "AND", polygon, log_x: !!S.slogx, log_y: !!S.slogy });
  if (SCR.mode === "selection") { SCR.mode = "criteria"; setSrc("criteria"); }  // a gate is a criterion: hits from the criteria again
  if (!SCR.on) { SCR.on = true; setScreenOn(); }
  renderCriteria(); recompute(); invalidate("scatter");
}
function showGate(c) {  // the axes of a gate, as it was drawn
  S.sx = c.metric; S.sy = c.metric2; S.slogx = !!c.log_x; S.slogy = !!c.log_y;
  $("sx").value = S.sx; $("sy").value = S.sy; $("slogx").checked = S.slogx; $("slogy").checked = S.slogy;
  gateState(); invalidate("scatter", "scatterSel", "scatterHov");
  $("sch").closest(".panel").scrollIntoView({ behavior: "smooth", block: "center" });
}
function drawScatterSel() {
  const ctx = SP.clear(1); if (!SP.map) return; const many = S.sel.size > 150;
  ctx.strokeStyle = css("--sel"); ctx.fillStyle = css("--sel"); ctx.lineWidth = 1.5;
  for (const i of S.sel) { const p = SP.map.get(i); if (!p) continue; ctx.beginPath(); ctx.arc(p[1], p[2], many ? 2.2 : 5, 0, 7); many ? ctx.fill() : ctx.stroke(); }
}
function drawScatterHov() {
  const ctx = SP.clear(2); const p = SP.map && SP.map.get(S.hover);
  if (p) { ctx.strokeStyle = css("--hover"); ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(p[1], p[2], 7, 0, 7); ctx.stroke(); }
}
layer("scatter", drawScatter); layer("scatterSel", drawScatterSel); layer("scatterHov", drawScatterHov);
function initScatter() {
  const opts = [["@value", VALUE_LABEL]]; if (KA) opts.push(["@additional", "additional channel @ frame"]);
  if (KOTHER) opts.push(["@partner", `${D.partner.name} @ frame`]);
  for (const id of ["sx", "sy"]) { const el = $(id); opts.forEach(([v, l]) => el.add(new Option(l, v))); NUMERIC.forEach(k => el.add(nameOpt(k))); }
  $("sx").value = S.sx; $("sy").value = S.sy;
  $("sx").onchange = () => { S.sx = $("sx").value; gateState(); invalidate("scatter", "scatterSel", "scatterHov"); };
  $("sy").onchange = () => { S.sy = $("sy").value; gateState(); invalidate("scatter", "scatterSel", "scatterHov"); };
  $("sgate").onclick = () => setGateDraw(!GATE_DRAW);
  addEventListener("keydown", (e) => { if (GATE_DRAW && e.key === "Escape") { e.stopImmediatePropagation(); setGateDraw(false); } }, true);
  addEventListener("keydown", (e) => { if (GATE_DRAW && e.key === "l") setTimeout(gateState, 0); });
  gateState();
  $("slogx").onchange = () => { S.slogx = $("slogx").checked; invalidate("scatter", "scatterSel", "scatterHov"); };
  if (C.class_additional) {
    $("sclassl").hidden = false;
    $("sclass").onchange = () => { S.sclass = $("sclass").checked; invalidate("scatter"); };
  }
  $("slogy").onchange = () => { S.slogy = $("slogy").checked; invalidate("scatter", "scatterSel", "scatterHov"); };
  const c = $("sch");
  c.addEventListener("pointermove", (e) => {
    if (e.shiftKey && e.buttons) return;
    const [px, py] = localXY(e, c); if (!SP.pts) return;
    let best = -1, bd = 64; for (const [i, x, y] of SP.pts) { const d = (x - px) ** 2 + (y - py) ** 2; if (d < bd) { bd = d; best = i; } }
    setHover(best, e);
  });
  c.addEventListener("click", (e) => { if (!e.shiftKey && !GATE_DRAW && !(Date.now() - (addGate.t || 0) < 400)) select(S.hover, e); });  // (not the end of drawing a gate)
  c.addEventListener("pointerleave", () => setHover(-1));
  attachSelector(c, $("ssvg"), (poly, add) => {
    if (GATE_DRAW) { addGate(poly); return; }
    selectMany(SP.pts.filter(([, x, y]) => inPolygon(x, y, poly)).map(p => p[0]), add);
  }, { draw: () => GATE_DRAW });
}
