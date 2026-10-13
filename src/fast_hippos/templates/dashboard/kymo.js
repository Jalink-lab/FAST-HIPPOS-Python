// ---------------------------------------------------------------- kymograph (cells sorted on mean response, time down)
const KP = new Plot([$("kyb"), $("kyo")], { l: 50, r: 12, t: 14, b: 26 });
const kymoCanvas = document.createElement("canvas");
function kymoColumns() { return (S.sorted ? ORDER : Array.from({ length: N }, (_, i) => i)).filter(visible); }
// zoom: S.kzoom >= 1 shows n / kzoom columns from S.kstart (at least 20)
function kymoView(nAll) {
  const shown = Math.min(nAll, Math.max(Math.min(20, nAll), Math.round(nAll / S.kzoom)));
  const start = Math.max(0, Math.min(nAll - shown, Math.round(S.kstart)));
  return { start, shown };
}
function drawKymo() {
  KP.resize();
  const all = kymoColumns(), view = kymoView(all.length), cols = all.slice(view.start, view.start + view.shown);
  const n = cols.length, k = K(), rgb = [0, 0, 0];
  KP.nAll = all.length; KP.start = view.start;
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
  KP.range(view.start, view.start + n, (T - 1) * FI, 0);
  KP.axes(ctx, S.sorted ? "cells (sorted on response)" : "cells", "time (s)", { nogrid: true });
  ctx.fillStyle = css("--hit"); const w = KP.pw / Math.max(1, n);
  cols.forEach((ci, c) => { if (HIT[ci]) ctx.fillRect(KP.m.l + c * w, KP.m.t - 6, Math.max(1, w), 4); });
  KP.cols = cols; KP.pos = new Map(cols.map((ci, c) => [ci, c]));
  $("kinfo").textContent = n < all.length ? `cells ${view.start + 1}–${view.start + n} of ${all.length}` : `all ${all.length} cells`;
}
function syncKymoZoom() {
  const maxZoom = Math.max(1, (KP.nAll || N) / 20);
  $("kzoom").value = maxZoom > 1 ? Math.round(Math.log(S.kzoom) / Math.log(maxZoom) * 100) : 0;
}
function setKymoZoom(z, centre) {  // centre: column (in the full order) to keep in the middle
  const nAll = KP.nAll || N, maxZoom = Math.max(1, nAll / 20), old = kymoView(nAll);
  const c = centre ?? old.start + old.shown / 2;
  S.kzoom = Math.max(1, Math.min(maxZoom, z));
  const shown = kymoView(nAll).shown; S.kstart = Math.max(0, Math.min(nAll - shown, c - shown / 2));
  syncKymoZoom(); invalidate("kymo", "kymoOvl");
}
function drawKymoOvl() {
  const ctx = KP.clear(1); if (!KP.cols) return; const n = KP.cols.length, w = KP.pw / Math.max(1, n);
  const y = KP.m.t + (S.frame + 0.5) / T * KP.ph; ctx.strokeStyle = "rgba(255,255,255,.85)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(KP.m.l, y); ctx.lineTo(KP.m.l + KP.pw, y); ctx.stroke();
  // selected columns: semi-transparent wash plus a tick below the axis
  ctx.fillStyle = withAlpha(css("--accent"), S.sel.size > 50 ? 0.35 : 0.85); ctx.strokeStyle = css("--sel");
  // mark per screen pixel and fill runs, so that overlapping narrow columns do not stack up their alpha
  const pw = Math.ceil(KP.pw), mark = new Uint8Array(pw + 1);
  for (const i of S.sel) { const c = KP.pos.get(i); if (c === undefined) continue; const mid = (c + 0.5) * w, half = Math.max(0.75, w / 2); mark.fill(1, Math.max(0, Math.floor(mid - half)), Math.min(pw, Math.ceil(mid + half))); }
  for (let x = 0; x < pw;) { if (!mark[x]) { x++; continue; } let e = x; while (e < pw && mark[e]) e++; ctx.fillRect(KP.m.l + x, KP.m.t, e - x, KP.ph); ctx.fillRect(KP.m.l + x, KP.m.t + KP.ph + 1, e - x, 6); x = e; }
  const hc = KP.pos.get(S.hover); if (hc !== undefined) { ctx.strokeStyle = css("--hover"); ctx.lineWidth = 1; ctx.strokeRect(KP.m.l + hc * w - 0.5, KP.m.t, Math.max(1, w) + 1, KP.ph); }
}
layer("kymo", drawKymo); layer("kymoOvl", drawKymoOvl);
function initKymo() {
  const c = $("kyo");
  const colAt = (px) => { const n = KP.cols.length; const k = Math.floor((px - KP.m.l) / KP.pw * n); return k >= 0 && k < n ? k : -1; };
  c.addEventListener("pointermove", (e) => { const [px, py] = localXY(e, c); const k = colAt(px); setHover(k >= 0 && KP.inside(px, py) ? KP.cols[k] : -1, e); });
  c.addEventListener("click", (e) => { if (c.dataset.dragged) { delete c.dataset.dragged; return; } if (e.shiftKey) return; const [px, py] = localXY(e, c); if (!KP.inside(px, py)) return; setFrame((py - KP.m.t) / KP.ph * T - 0.5); const k = colAt(px); select(k >= 0 ? KP.cols[k] : -1, e); });
  c.addEventListener("pointerleave", () => setHover(-1));
  attachSelector(c, $("ksvg"), (poly, add) => {
    const xs = poly.map(p => p[0]); const a = colAt(Math.max(KP.m.l, Math.min(...xs))), b = colAt(Math.min(KP.m.l + KP.pw - 1, Math.max(...xs)));
    if (a < 0 || b < 0) return; selectMany(KP.cols.slice(a, b + 1), add);
  }, { rangeOnly: true });
  $("ksort").onchange = () => { S.sorted = $("ksort").checked; invalidate("kymo", "kymoOvl"); };
  // zoom slider (logarithmic): zooms around the selected cells if they are in view, else around the middle
  $("kzoom").oninput = () => {
    const maxZoom = Math.max(1, (KP.nAll || N) / 20), z = Math.pow(maxZoom, +$("kzoom").value / 100);
    const sel = [...S.sel].map(i => KP.pos.get(i)).filter(c => c !== undefined);
    setKymoZoom(z, sel.length ? KP.start + sel.reduce((a, b) => a + b, 0) / sel.length : undefined);
  };
  c.addEventListener("wheel", (e) => {
    if (!(e.ctrlKey || e.metaKey)) return; e.preventDefault();
    const [px] = localXY(e, c), col = KP.start + (px - KP.m.l) / KP.pw * KP.cols.length;
    setKymoZoom(S.kzoom * Math.exp(-e.deltaY * 0.002), col);
  }, { passive: false });
  // drag (without shift) to move along when zoomed in
  let drag = null;
  c.addEventListener("pointerdown", (e) => { if (e.shiftKey || S.kzoom <= 1) return; drag = { x: e.clientX, start: S.kstart, moved: false }; });
  addEventListener("pointermove", (e) => {
    if (!drag) return; const dx = e.clientX - drag.x; if (Math.abs(dx) > 3) drag.moved = true;
    if (drag.moved) { const shown = KP.cols.length; S.kstart = Math.max(0, Math.min(KP.nAll - shown, drag.start - dx / KP.pw * shown)); invalidate("kymo", "kymoOvl"); }
  });
  addEventListener("pointerup", () => { if (drag && drag.moved) c.dataset.dragged = "1"; drag = null; });
}
