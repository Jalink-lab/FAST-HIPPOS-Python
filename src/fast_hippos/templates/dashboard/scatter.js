// ---------------------------------------------------------------- scatter plot of any two per-cell quantities
const SP = new Plot([$("scb"), $("scs"), $("sch")], { l: 56, r: 12, t: 10, b: 32 });
const SKIP = ["image", "cell", "tile", "hit", "valid", "response_rank", "bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1"];
const NUMERIC = Object.keys(C).filter(k => !SKIP.includes(k) && C[k].some(v => typeof v === "number"));
const VALUE_LABEL = D.is_lifetime ? "lifetime @ frame" : "value @ frame";
function scatterValues(key) {
  const o = new Float64Array(N);
  if (key === "@value") { const k = K(); for (let i = 0; i < N; i++) o[i] = k[S.frame * N + i]; return o; }
  if (key === "@additional") { for (let i = 0; i < N; i++) o[i] = KA[S.frame * N + i]; return o; }
  const a = C[key]; for (let i = 0; i < N; i++) o[i] = a[i] === null || a[i] === undefined ? NaN : a[i]; return o;
}
const scatterLabel = (k) => k === "@value" ? VALUE_LABEL : k === "@additional" ? "additional channel @ frame" : k;
function drawScatter() {
  SP.resize(); SP.logx = S.slogx; SP.logy = S.slogy;
  const xs = scatterValues(S.sx), ys = scatterValues(S.sy), ids = [];
  for (let i = 0; i < N; i++) if (visible(i)) ids.push(i);
  const [x0, x1] = finiteRange(xs, ids, S.slogx), [y0, y1] = S.sy === "@value" && !S.slogy ? yRange() : finiteRange(ys, ids, S.slogy);
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
  ctx.restore(); ctx.globalAlpha = 1;
  SP.map = new Map(SP.pts.map(p => [p[0], p]));
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
  NUMERIC.forEach(k => opts.push([k, k]));
  for (const id of ["sx", "sy"]) { const el = $(id); opts.forEach(([v, l]) => el.add(new Option(l, v))); }
  $("sx").value = S.sx; $("sy").value = S.sy;
  $("sx").onchange = () => { S.sx = $("sx").value; invalidate("scatter", "scatterSel", "scatterHov"); };
  $("sy").onchange = () => { S.sy = $("sy").value; invalidate("scatter", "scatterSel", "scatterHov"); };
  $("slogx").onchange = () => { S.slogx = $("slogx").checked; invalidate("scatter", "scatterSel", "scatterHov"); };
  $("slogy").onchange = () => { S.slogy = $("slogy").checked; invalidate("scatter", "scatterSel", "scatterHov"); };
  const c = $("sch");
  c.addEventListener("pointermove", (e) => {
    if (e.shiftKey && e.buttons) return;
    const [px, py] = localXY(e, c); if (!SP.pts) return;
    let best = -1, bd = 64; for (const [i, x, y] of SP.pts) { const d = (x - px) ** 2 + (y - py) ** 2; if (d < bd) { bd = d; best = i; } }
    setHover(best, e);
  });
  c.addEventListener("click", (e) => { if (!e.shiftKey) select(S.hover, e); });
  c.addEventListener("pointerleave", () => setHover(-1));
  attachSelector(c, $("ssvg"), (poly, add) => selectMany(SP.pts.filter(([, x, y]) => inPolygon(x, y, poly)).map(p => p[0]), add));
}
