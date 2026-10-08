// ---------------------------------------------------------------- kymograph (cells sorted on mean response, time down)
const KP = new Plot([$("kyb"), $("kyo")], { l: 50, r: 12, t: 14, b: 26 });
const kymoCanvas = document.createElement("canvas");
function kymoColumns() { return (S.sorted ? ORDER : Array.from({ length: N }, (_, i) => i)).filter(visible); }
function drawKymo() {
  KP.resize();
  const cols = kymoColumns(), n = cols.length, k = K(), rgb = [0, 0, 0];
  kymoCanvas.width = Math.max(1, n); kymoCanvas.height = T;
  const x = kymoCanvas.getContext("2d"), img = x.createImageData(Math.max(1, n), T);
  for (let t = 0; t < T; t++) for (let c = 0; c < n; c++) {
    const v = k[t * N + cols[c]], q = (t * n + c) * 4;
    if (Number.isNaN(v)) continue;
    lutRGB(v, rgb); img.data[q] = rgb[0]; img.data[q + 1] = rgb[1]; img.data[q + 2] = rgb[2]; img.data[q + 3] = 255;
  }
  x.putImageData(img, 0, 0);
  const ctx = KP.clear(0);
  ctx.imageSmoothingEnabled = n > KP.pw * 2; ctx.drawImage(kymoCanvas, KP.m.l, KP.m.t, KP.pw, KP.ph);
  KP.range(0, n, (T - 1) * FI, 0);
  KP.axes(ctx, S.sorted ? "cells (sorted on response)" : "cells", "time (s)", { nogrid: true });
  ctx.fillStyle = css("--hit"); const w = KP.pw / Math.max(1, n);
  cols.forEach((ci, c) => { if (HIT[ci]) ctx.fillRect(KP.m.l + c * w, KP.m.t - 6, Math.max(1, w), 4); });
  KP.cols = cols; KP.pos = new Map(cols.map((ci, c) => [ci, c]));
}
function drawKymoOvl() {
  const ctx = KP.clear(1); if (!KP.cols) return; const n = KP.cols.length, w = KP.pw / Math.max(1, n);
  const y = KP.m.t + (S.frame + 0.5) / T * KP.ph; ctx.strokeStyle = "rgba(255,255,255,.85)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(KP.m.l, y); ctx.lineTo(KP.m.l + KP.pw, y); ctx.stroke();
  // selected columns: semi-transparent wash plus a tick below the axis
  ctx.fillStyle = withAlpha(css("--sel"), 0.35); ctx.strokeStyle = css("--sel");
  for (const i of S.sel) { const c = KP.pos.get(i); if (c === undefined) continue; const x = KP.m.l + c * w; ctx.fillRect(x, KP.m.t, Math.max(1, w), KP.ph); ctx.fillRect(x, KP.m.t + KP.ph + 1, Math.max(1, w), 4); }
  const hc = KP.pos.get(S.hover); if (hc !== undefined) { ctx.strokeStyle = css("--hover"); ctx.lineWidth = 2; ctx.strokeRect(KP.m.l + hc * w, KP.m.t, Math.max(2, w), KP.ph); }
}
layer("kymo", drawKymo); layer("kymoOvl", drawKymoOvl);
function initKymo() {
  const c = $("kyo");
  const colAt = (px) => { const n = KP.cols.length; const k = Math.floor((px - KP.m.l) / KP.pw * n); return k >= 0 && k < n ? k : -1; };
  c.addEventListener("pointermove", (e) => { const [px, py] = localXY(e, c); const k = colAt(px); setHover(k >= 0 && KP.inside(px, py) ? KP.cols[k] : -1, e); });
  c.addEventListener("click", (e) => { if (e.shiftKey) return; const [px, py] = localXY(e, c); if (!KP.inside(px, py)) return; setFrame((py - KP.m.t) / KP.ph * T - 0.5); const k = colAt(px); select(k >= 0 ? KP.cols[k] : -1, e); });
  c.addEventListener("pointerleave", () => setHover(-1));
  attachSelector(c, $("ksvg"), (poly, add) => {
    const xs = poly.map(p => p[0]); const a = colAt(Math.max(KP.m.l, Math.min(...xs))), b = colAt(Math.min(KP.m.l + KP.pw - 1, Math.max(...xs)));
    if (a < 0 || b < 0) return; selectMany(KP.cols.slice(a, b + 1), add);
  }, { rangeOnly: true });
  $("ksort").onchange = () => { S.sorted = $("ksort").checked; invalidate("kymo", "kymoOvl"); };
}
