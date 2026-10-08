// ---------------------------------------------------------------- traces: lines, quantile bands or density
const TP = new Plot([$("trb"), $("trs"), $("trh")], { l: 50, r: 12, t: 12, b: 32 });
const yRange = () => [S.dmin, S.dmax];
function groupsForBands() {
  const vis = []; for (let i = 0; i < N; i++) if (visible(i)) vis.push(i);
  if (S.tcol === "hit" && HIT.some(Boolean)) return [
    { ids: vis.filter(i => !HIT[i]), color: css("--trace-gray-solid"), name: "non-hits" },
    { ids: vis.filter(i => HIT[i]), color: css("--hit"), name: "hits" }];
  return [{ ids: vis, color: css("--accent"), name: "cells" }];
}
function bandStats(ids, k) {
  const q = [0.1, 0.25, 0.5, 0.75, 0.9], out = q.map(() => new Float64Array(T)), col = new Float64Array(ids.length);
  for (let t = 0; t < T; t++) { for (let j = 0; j < ids.length; j++) col[j] = k[t * N + ids[j]]; const v = quantiles(Array.from(col), q); v.forEach((x, m) => out[m][t] = x); }
  return out;
}
function drawBand(ctx, xs, stats, color, alphaOuter = 0.13, alphaInner = 0.28, lw = 2) {
  const area = (lo, hi, a) => { ctx.fillStyle = withAlpha(color, a); ctx.beginPath(); let started = false;
    for (let t = 0; t < T; t++) { if (!Number.isFinite(hi[t])) continue; const y = TP.Y(hi[t]); started ? ctx.lineTo(xs[t], y) : ctx.moveTo(xs[t], y); started = true; }
    for (let t = T - 1; t >= 0; t--) { if (!Number.isFinite(lo[t])) continue; ctx.lineTo(xs[t], TP.Y(lo[t])); } ctx.fill(); };
  area(stats[0], stats[4], alphaOuter); area(stats[1], stats[3], alphaInner);
  ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.beginPath(); let pen = false;
  for (let t = 0; t < T; t++) { const v = stats[2][t]; if (!Number.isFinite(v)) { pen = false; continue; } pen ? ctx.lineTo(xs[t], TP.Y(v)) : ctx.moveTo(xs[t], TP.Y(v)); pen = true; } ctx.stroke();
}
const densCanvas = document.createElement("canvas");
function drawDensity(ctx, ids, k, color) {
  const ny = Math.max(20, Math.round(TP.ph / 2)); densCanvas.width = T; densCanvas.height = ny;
  const x = densCanvas.getContext("2d"), img = x.createImageData(T, ny), [r, g, b] = hexToRgb(color);
  for (let t = 0; t < T; t++) {
    const h = new Float64Array(ny); let mx = 0;
    for (const i of ids) { const v = k[t * N + i]; if (Number.isNaN(v)) continue; const bi = Math.floor((1 - (v - TP.y0) / (TP.y1 - TP.y0)) * ny); if (bi >= 0 && bi < ny) { h[bi]++; if (h[bi] > mx) mx = h[bi]; } }
    for (let bi = 0; bi < ny; bi++) { const q = (bi * T + t) * 4; img.data[q] = r; img.data[q + 1] = g; img.data[q + 2] = b; img.data[q + 3] = mx ? Math.round(Math.sqrt(h[bi] / mx) * 235) : 0; }
  }
  x.putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true;
  const dx = T > 1 ? (TP.X(FI) - TP.X(0)) / 2 : 0;
  ctx.drawImage(densCanvas, TP.m.l - dx, TP.m.t, TP.pw + 2 * dx, TP.ph);
}
function drawTraces() {
  TP.resize(); TP.range(0, Math.max(1, T - 1) * FI, ...yRange());
  const ctx = TP.clear(0); TP.axes(ctx, "time (s)", D.is_lifetime ? "lifetime (ns)" : D.unit);
  ctx.save(); TP.clip(ctx);
  const ev = EV, xs = new Float32Array(T); for (let t = 0; t < T; t++) xs[t] = TP.X(t * FI);
  const shade = (a, b, col) => { if (b > a) { ctx.fillStyle = col; ctx.fillRect(TP.X(a * FI), TP.m.t, TP.X(Math.max(a, b - 1) * FI) - TP.X(a * FI) || 2, TP.ph); } };
  if (!ev.baseline_only) { shade(ev.baseline[0], ev.baseline[1], css("--base-win")); shade(ev.timed_window[0], ev.timed_window[1], css("--resp-win")); shade(ev.calibration_window[0], ev.calibration_window[1], css("--cal-win")); }
  const k = K(); let nvis = 0; for (let i = 0; i < N; i++) if (visible(i)) nvis++;
  if (S.tmode === "lines") {
    const alpha = nvis > 1000 ? 0.18 : nvis > 200 ? 0.35 : 0.7; ctx.lineWidth = nvis > 1000 ? 0.6 : 1;
    const drawOne = (i) => { ctx.beginPath(); let pen = false; for (let t = 0; t < T; t++) { const v = k[t * N + i]; if (Number.isNaN(v)) { pen = false; continue; } const y = TP.Y(v); pen ? ctx.lineTo(xs[t], y) : ctx.moveTo(xs[t], y); pen = true; } ctx.stroke(); };
    const gray = css("--trace-gray"), hit = css("--hit");
    if (S.tcol === "hit") { ctx.strokeStyle = gray; for (let i = 0; i < N; i++) if (visible(i) && !HIT[i]) drawOne(i); ctx.strokeStyle = hit; ctx.globalAlpha = 0.85; for (let i = 0; i < N; i++) if (visible(i) && HIT[i]) drawOne(i); ctx.globalAlpha = 1; }
    else if (S.tcol === "gray") { ctx.strokeStyle = gray; for (let i = 0; i < N; i++) if (visible(i)) drawOne(i); }
    else for (let i = 0; i < N; i++) if (visible(i)) { ctx.strokeStyle = cellColor(i, alpha); drawOne(i); }
    const all = groupsForBands(); const ids = all.flatMap(g => g.ids);
    if (ids.length) drawBand(ctx, xs, bandStats(ids, k), css("--mean"), 0, 0, 2.5);
  } else if (S.tmode === "bands") {
    for (const g of groupsForBands()) if (g.ids.length) drawBand(ctx, xs, bandStats(g.ids, k), g.color);
  } else {
    const groups = groupsForBands(), ids = groups.flatMap(g => g.ids);
    drawDensity(ctx, ids, k, css("--accent"));
    for (const g of groups) if (g.ids.length) drawBand(ctx, xs, bandStats(g.ids, k), g.name === "hits" ? css("--hit") : css("--mean"), 0, 0, 2);
  }
  ctx.setLineDash([4, 4]); ctx.strokeStyle = css("--muted"); ctx.lineWidth = 1; ctx.font = "11px system-ui"; ctx.fillStyle = css("--muted");
  for (const [f, name] of [[ev.stimulation, "stim"], [ev.calibration, "cal"]]) if (f !== null && f !== undefined && !ev.baseline_only) { const x = TP.X(f * FI); ctx.beginPath(); ctx.moveTo(x, TP.m.t); ctx.lineTo(x, TP.m.t + TP.ph); ctx.stroke(); ctx.fillText(name, x + 3, TP.m.t + 10); }
  ctx.restore();
  $("trinfo").textContent = `${nvis} cells` + (S.tsrc === "smoothed" ? ` · smoothed r=${SCR.params.smooth_traces}` : "") + (S.tmode !== "lines" ? " · median, 25–75 %, 10–90 %" : "");
}
function traceLine(ctx, i, col, w) {
  const k = K(); ctx.strokeStyle = col; ctx.lineWidth = w; ctx.beginPath(); let pen = false;
  for (let t = 0; t < T; t++) { const v = k[t * N + i]; if (Number.isNaN(v)) { pen = false; continue; } const x = TP.X(t * FI), y = TP.Y(v); pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y); pen = true; }
  ctx.stroke();
}
function drawTracesSel() {
  const ctx = TP.clear(1); ctx.save(); TP.clip(ctx); const n = S.sel.size;
  if (n > 300) {  // many cells: a band reads better than 300+ lines
    const xs = new Float32Array(T); for (let t = 0; t < T; t++) xs[t] = TP.X(t * FI);
    drawBand(ctx, xs, bandStats([...S.sel], K()), css("--sel"), 0.12, 0.25, 2);
  } else {
    const w = n <= 10 ? 2.5 : n <= 50 ? 1.5 : 1, a = n <= 50 ? 1 : 0.55;
    for (const i of S.sel) { if (n <= 10) traceLine(ctx, i, css("--bg"), w + 2); ctx.globalAlpha = a; traceLine(ctx, i, S.tcol === "cell" ? cellColor(i) : css("--sel"), w); ctx.globalAlpha = 1; }
  }
  ctx.restore();
}
function drawTracesHov() {
  const ctx = TP.clear(2); ctx.save(); TP.clip(ctx);
  const x = TP.X(S.frame * FI); ctx.strokeStyle = css("--accent"); ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(x, TP.m.t); ctx.lineTo(x, TP.m.t + TP.ph); ctx.stroke();
  if (S.hover >= 0) { traceLine(ctx, S.hover, css("--bg"), 5); traceLine(ctx, S.hover, css("--hover"), 2.5); }
  ctx.restore();
}
layer("traces", drawTraces); layer("tracesSel", drawTracesSel); layer("tracesHov", drawTracesHov);
function initTraces() {
  const c = $("trh");
  c.addEventListener("pointermove", (e) => {
    const [px, py] = localXY(e, c); if (!TP.inside(px, py)) { setHover(-1); return; }
    const t = Math.max(0, Math.min(T - 1, Math.round(TP.iX(px) / FI))), y = TP.iY(py), k = K();
    let best = -1, bd = Infinity;
    const cand = S.tmode === "lines" ? null : S.sel;  // in band/density mode only the drawn (selected) lines are pickable
    for (let i = 0; i < N; i++) { if (cand ? !cand.has(i) : !visible(i)) continue; const d = Math.abs(k[t * N + i] - y); if (d < bd) { bd = d; best = i; } }
    setHover(best >= 0 && Math.abs(TP.Y(k[t * N + best]) - py) < 10 ? best : -1, e);
  });
  c.addEventListener("pointerleave", () => setHover(-1));
  c.addEventListener("click", (e) => { const [px] = localXY(e, c); if (S.hover >= 0) select(S.hover, e); else setFrame(TP.iX(px) / FI); });
  $("tmode").value = S.tmode; $("tmode").onchange = () => { S.tmode = $("tmode").value; invalidate("traces"); };
  $("tcol").value = S.tcol; $("tcol").onchange = () => { S.tcol = $("tcol").value; invalidate("traces", "tracesSel"); };
}
