// ---------------------------------------------------------------- image viewer: embedded overview + lazily loaded tile pyramid
const V = D.viewer, W0 = D.image_size[0], H0 = D.image_size[1], F0 = V.factor, NVF = V.frames.length;
const VW = V.size[0], VH = V.size[1];
const TLEVELS = (V.tiles && V.tiles.levels) || [];   // finer levels (factor 1, 2, ...), loaded on demand
const TSIZE = (V.tiles && V.tiles.tile) || 512;
const vwrap = $("vwrap"), vimg = $("vimg"), vsel = $("vsel"), vhov = $("vhov"), vsvg = $("vsvg");
const view = { s: 1, tx: 0, ty: 0, fitted: false, auto: true };  // s = screen px per full-resolution px; auto = keep fitting
let renderVersion = 0, outlineVersion = 0;

// ---- caches (Map keeps insertion order -> simple LRU)
function lru(max) {
  const m = new Map();
  return { get(k) { const v = m.get(k); if (v !== undefined) { m.delete(k); m.set(k, v); } return v; },
    set(k, v) { m.set(k, v); while (m.size > max) m.delete(m.keys().next().value); }, has: (k) => m.has(k), clear: () => m.clear() };
}
const rawCache = lru(150), labCache = lru(120), compCache = lru(100), outCache = lru(100), fillCache = lru(60), lastComp = new Map();  // ~1 MB per 512² tile
let fillVersion = 0, fillRange = [0, 1];
const inflight = new Set(); let active = 0; const queue = [];

function decodeURL(url) {
  return new Promise((res, rej) => { const im = new Image(); im.onload = () => {
    const c = document.createElement("canvas"); c.width = im.width; c.height = im.height;
    const x = c.getContext("2d", { willReadFrequently: true }); x.drawImage(im, 0, 0);
    res({ data: x.getImageData(0, 0, im.width, im.height).data, w: im.width, h: im.height }); }; im.onerror = rej; im.src = url; });
}
// tiles are .js files calling FHTile(key, dataURL): works from file:// where fetch() is blocked
const tileWaiters = new Map();
window.FHTile = (key, url) => { const r = tileWaiters.get(key); if (r) { tileWaiters.delete(key); r(url); } };
function loadTileURL(key) {
  return new Promise((resolve) => {
    tileWaiters.set(key, resolve);
    const s = document.createElement("script"); s.src = `${V.tiles.path}/${key}.js`;
    s.onload = () => s.remove(); s.onerror = () => { s.remove(); tileWaiters.delete(key); resolve(null); };
    document.head.appendChild(s);
  });
}
function sourceURL(key) {
  if (key === "O/lab") return Promise.resolve(V.labels);
  if (key === "O/p") return Promise.resolve(V.projection);
  if (key.startsWith("O/t")) return Promise.resolve(V.images[+key.slice(3)]);
  return loadTileURL(key);
}
// request(key): cached entry or null (and starts loading); `then` layers are redrawn when it arrives
function request(key, then = ["viewer", "viewerSel", "cell"]) {
  const isLab = key.endsWith("lab") || key.includes("/lab_");
  const hit = (isLab ? labCache : rawCache).get(key);
  if (hit) return hit;
  if (!inflight.has(key)) { inflight.add(key); queue.push([key, isLab, then]); pump(); }
  return null;
}
function pump() {
  while (active < 6 && queue.length) {
    const [key, isLab, then] = queue.pop();  // newest first: what is on screen now
    active++;
    sourceURL(key).then(url => url ? decodeURL(url) : null).then(img => {
      if (img) (isLab ? labCache : rawCache).set(key, isLab ? labelEntry(img) : img);
    }).catch(() => {}).finally(() => { active--; inflight.delete(key); invalidate(...then); pump(); });
  }
  const n = queue.length + active; $("loading").textContent = n ? `loading ${n} tile${n > 1 ? "s" : ""}…` : "";
}
function labelEntry(img) {
  const { data, w, h } = img, lab = new Int32Array(w * h), bnd = [];
  for (let p = 0; p < w * h; p++) lab[p] = data[4 * p] + 256 * data[4 * p + 1] + 65536 * data[4 * p + 2];
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const p = y * w + x, l = lab[p]; if (!l) continue;
    if ((x > 0 && lab[p - 1] !== l) || (x < w - 1 && lab[p + 1] !== l) || (y > 0 && lab[p - w] !== l) || (y < h - 1 && lab[p + w] !== l)) bnd.push(p);
  }
  // per-label index into bnd (sorted by label) for fast single-cell outlines
  const b = Int32Array.from(bnd).sort((p, q) => lab[p] - lab[q]), first = new Map();
  for (let k = b.length - 1; k >= 0; k--) first.set(lab[b[k]], k);
  return { lab, bnd: b, first, w, h };
}

// ---- levels and tiles
function vfIndex(t) { let lo = 0; for (let i = 0; i < NVF; i++) if (V.frames[i] <= t) lo = i; return lo; }
const OVERVIEW = { f: F0, overview: true };
function chooseLevel(s) {
  // coarsest level that still has at least ~1 level pixel per screen pixel
  const want = 1 / s; let best = OVERVIEW;
  if (F0 <= Math.max(1, want) || !TLEVELS.length) return OVERVIEW;
  for (const L of TLEVELS) if (L.factor <= Math.max(1, want)) best = L;
  return best === OVERVIEW ? TLEVELS[0] : best;
}
function tilesInView(L, cw, ch, vw) {
  const f = L.factor, x0 = Math.max(0, -vw.tx / vw.s / f), y0 = Math.max(0, -vw.ty / vw.s / f);
  const x1 = Math.min(L.width, (cw - vw.tx) / vw.s / f), y1 = Math.min(L.height, (ch - vw.ty) / vw.s / f);
  const out = [];
  for (let ty = Math.floor(y0 / TSIZE); ty <= Math.min(L.ny - 1, Math.floor((y1 - 1) / TSIZE)); ty++)
    for (let tx = Math.floor(x0 / TSIZE); tx <= Math.min(L.nx - 1, Math.floor((x1 - 1) / TSIZE)); tx++)
      out.push({ L, tx, ty, x: tx * TSIZE, y: ty * TSIZE, f, pos: `L${L.level}/${ty}_${tx}` });
  return out;
}
const frameKey = (t, vf) => t.L ? `L${t.L.level}/t${vf}_${t.ty}_${t.tx}` : `O/t${vf}`;
const projKey = (t) => t.L ? `L${t.L.level}/p_${t.ty}_${t.tx}` : "O/p";
const labKey = (t) => t.L ? `L${t.L.level}/lab_${t.ty}_${t.tx}` : "O/lab";

// ---- compositing: lifetime code (R) through the LUT, times intensity (G or projection)
function luts() {
  const tauIdx = new Int16Array(256); tauIdx[0] = -1;
  for (let r = 1; r < 256; r++) { const v = V.lo + (r - 1) / 254 * (V.hi - V.lo); let x = (v - S.dmin) / (S.dmax - S.dmin); x = x < 0 ? 0 : x > 1 ? 1 : x; tauIdx[r] = Math.round(x * 255) * 3; }
  const gain = new Float32Array(256); for (let g = 0; g < 256; g++) gain[g] = Math.min(1, g / 255 * S.bright);
  return { tauIdx, gain, L: LUTS[S.lut] };
}
let LT = null;
function composite(fr, pr) {
  const c = document.createElement("canvas"); c.width = fr.w; c.height = fr.h;
  const x = c.getContext("2d"), img = x.createImageData(fr.w, fr.h), out = img.data, f = fr.data, { tauIdx, gain, L } = LT;
  const useProj = !!pr;
  for (let q = 0; q < out.length; q += 4) {
    const k = tauIdx[f[q]], g = gain[useProj ? pr.data[q] : f[q + 1]];
    if (k < 0) { const v = g * 140; out[q] = out[q + 1] = out[q + 2] = v; }
    else { out[q] = L[k] * g; out[q + 1] = L[k + 1] * g; out[q + 2] = L[k + 2] * g; }
    out[q + 3] = 255;
  }
  x.putImageData(img, 0, 0); return c;
}
function tileImage(t, vf, then) {
  const fk = frameKey(t, vf), key = `${fk}|${S.isrc}|${renderVersion}`;
  let c = compCache.get(key); if (c) return c;
  const fr = request(fk, then), pr = S.isrc === "projection" ? request(projKey(t), then) : null;
  if (!fr || (S.isrc === "projection" && !pr)) return null;
  c = composite(fr, pr); compCache.set(key, c); return c;
}
let hitRGB = [255, 79, 176], selRGB = [255, 255, 255];
function outlineImage(t) {
  const lk = labKey(t), key = `${lk}|${outlineVersion}`;
  let c = outCache.get(key); if (c) return c;
  const le = request(lk); if (!le) return null;
  c = document.createElement("canvas"); c.width = le.w; c.height = le.h;
  const x = c.getContext("2d"), img = x.createImageData(le.w, le.h), d = img.data, mode = S.outl;
  for (const p of le.bnd) {
    const i = le.lab[p] - 1; if (i < 0 || i >= N) continue;
    let rgb = null, a = 255;
    if (S.sel.has(i)) rgb = selRGB;
    else if ((mode === "hits" || mode === "all") && HIT[i]) rgb = hitRGB;
    else if (mode === "all") { rgb = [200, 200, 200]; a = 110; }
    if (!rgb) continue;
    const q = p * 4; d[q] = rgb[0]; d[q + 1] = rgb[1]; d[q + 2] = rgb[2]; d[q + 3] = a;
  }
  x.putImageData(img, 0, 0); outCache.set(key, c); return c;
}

// cells filled with the colour of a per-cell metric (spatial pattern of responses / hits)
function fillImage(t) {
  const lk = labKey(t), key = `${lk}|${fillVersion}`;
  let c = fillCache.get(key); if (c) return c;
  const le = request(lk); if (!le) return null;
  c = document.createElement("canvas"); c.width = le.w; c.height = le.h;
  const x = c.getContext("2d"), img = x.createImageData(le.w, le.h), d = img.data, vals = C[S.fillMetric], Lv = LUTS.viridis;
  const [lo, hi] = fillRange, cache = new Map();
  for (let p = 0; p < le.lab.length; p++) {
    const l = le.lab[p]; if (!l || l > N) continue;
    let k = cache.get(l);
    if (k === undefined) { const v = vals[l - 1]; k = v === null || !Number.isFinite(v) ? -1 : Math.round(Math.max(0, Math.min(1, (v - lo) / (hi - lo || 1))) * 255) * 3; cache.set(l, k); }
    if (k < 0) continue;
    const q = p * 4; d[q] = Lv[k]; d[q + 1] = Lv[k + 1]; d[q + 2] = Lv[k + 2]; d[q + 3] = 200;
  }
  x.putImageData(img, 0, 0); fillCache.set(key, c); return c;
}
function fillsChanged() {
  if (S.fillMetric) { const q = quantiles(Array.from(C[S.fillMetric], v => v ?? NaN), [0.02, 0.98]); fillRange = Number.isFinite(q[0]) ? q : [0, 1]; }
  fillVersion++; invalidate("viewerSel"); drawColorbar();
}

// generic renderer (used for the main view and for the cell card crop)
function renderImage(ctx, cw, ch, vw, then) {
  const vf = vfIndex(S.frame), L = chooseLevel(vw.s);
  ctx.imageSmoothingEnabled = vw.s * F0 < 1;
  const ov = tileImage({ L: null }, vf, then);
  if (ov) ctx.drawImage(ov, vw.tx, vw.ty, VW * F0 * vw.s, VH * F0 * vw.s);
  if (L === OVERVIEW) return;
  ctx.imageSmoothingEnabled = vw.s * L.factor < 1;
  for (const t of tilesInView(L, cw, ch, vw)) {
    let c = tileImage(t, vf, then);
    if (c) lastComp.set(t.pos, c); else c = lastComp.get(t.pos);  // previous frame while loading
    if (c) ctx.drawImage(c, vw.tx + t.x * t.f * vw.s, vw.ty + t.y * t.f * vw.s, c.width * t.f * vw.s, c.height * t.f * vw.s);
  }
}
function renderOutlines(ctx, cw, ch, vw, make = outlineImage) {
  const L = chooseLevel(vw.s); ctx.imageSmoothingEnabled = false;
  const tiles = L === OVERVIEW ? [{ L: null, x: 0, y: 0, f: F0 }] : tilesInView(L, cw, ch, vw);
  let fallback = false;
  for (const t of tiles) {
    const c = make(t);
    if (!c && t.L && !fallback) { const ov = make({ L: null }); if (ov) ctx.drawImage(ov, vw.tx, vw.ty, VW * F0 * vw.s, VH * F0 * vw.s); fallback = true; continue; }
    if (c) ctx.drawImage(c, vw.tx + t.x * t.f * vw.s, vw.ty + t.y * t.f * vw.s, c.width * t.f * vw.s, c.height * t.f * vw.s);
  }
}
// boundary pixels of one cell in screen coordinates (for the hover outline)
function cellBoundary(i, cw, ch, vw) {
  const L = chooseLevel(vw.s), out = [];
  const tiles = L === OVERVIEW ? [{ L: null, x: 0, y: 0, f: F0 }] : tilesInView(L, cw, ch, vw);
  for (const t of tiles) {
    const le = labCache.get(labKey(t)); if (!le) continue;
    const k0 = le.first.get(i + 1); if (k0 === undefined) continue;
    for (let k = k0; k < le.bnd.length && le.lab[le.bnd[k]] === i + 1; k++) { const p = le.bnd[k]; out.push([vw.tx + (t.x + p % le.w) * t.f * vw.s, vw.ty + (t.y + Math.floor(p / le.w)) * t.f * vw.s, t.f * vw.s]); }
  }
  return out;
}

// ---- layers
function canvasSize(c) { const r = vwrap.getBoundingClientRect(), dpr = window.devicePixelRatio || 1; const W = Math.round(r.width * dpr), H = Math.round(r.height * dpr); if (c.width !== W || c.height !== H) { c.width = W; c.height = H; } const x = c.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, r.width, r.height); return [x, r.width, r.height]; }
function drawViewer() {
  if (!view.fitted) fitView(false);
  LT = luts();
  const [x, w, h] = canvasSize(vimg); renderImage(x, w, h, view);
  if (S.playing) prefetch();
  const L = chooseLevel(view.s);
  $("vinfo").textContent = `${W0}×${H0} px · ${L === OVERVIEW ? (F0 > 1 ? `overview 1:${F0}` : "full resolution") : (L.factor > 1 ? `tiles 1:${L.factor}` : "full resolution")}` + (NVF < T ? ` · ${NVF} of ${T} frames` : "");
  invalidate("viewerSel", "viewerHov");
}
function prefetch() {
  const next = vfIndex(Math.min(T - 1, S.frame + 1)), L = chooseLevel(view.s);
  const r = vwrap.getBoundingClientRect();
  if (L === OVERVIEW) request(frameKey({ L: null }, next), []);
  else for (const t of tilesInView(L, r.width, r.height, view)) request(frameKey(t, next), []);
}
function drawViewerSel() { const [x, w, h] = canvasSize(vsel); if (S.fillMetric && C[S.fillMetric]) renderOutlines(x, w, h, view, fillImage); renderOutlines(x, w, h, view); }
function drawViewerHov() {
  const [x, w, h] = canvasSize(vhov);
  if (S.hover >= 0) { x.fillStyle = css("--hover"); for (const [px, py, sz] of cellBoundary(S.hover, w, h, view)) x.fillRect(px, py, Math.max(1, sz), Math.max(1, sz)); }
  if (S.showRoute && SCR.route) drawRoute(x);
  if (S.scalebar && D.pixel_size) drawScaleBar(x, w, h);
}
function drawRoute(x) {
  const colors = ["#4da3ff", "#ffb347", "#7bd389", "#c792ea", "#ff6b6b", "#5ad1d1"];
  const sx = (i) => view.tx + POSX[i] * view.s, sy = (i) => view.ty + POSY[i] * view.s;
  SCR.route.chunks.forEach((chunk, k) => {
    if (chunk.length < 2) return;
    x.strokeStyle = colors[k % colors.length]; x.lineWidth = 1.5; x.globalAlpha = SCR.route.stale ? 0.35 : 0.9;
    x.beginPath(); chunk.forEach((i, j) => j ? x.lineTo(sx(i), sy(i)) : x.moveTo(sx(i), sy(i))); x.stroke();
    x.fillStyle = x.strokeStyle; x.beginPath(); x.arc(sx(chunk[0]), sy(chunk[0]), 5, 0, 7); x.fill();
    if (view.s > 0.6 * F0 && chunk.length < 400) { x.font = "10px system-ui"; x.fillStyle = "#fff"; chunk.forEach((i, j) => x.fillText(j + 1, sx(i) + 4, sy(i) - 4)); }
  });
  x.globalAlpha = 1;
}
function drawScaleBar(x, w, h) {
  const pxPerUm = view.s / D.pixel_size, target = 110 / pxPerUm, e = Math.pow(10, Math.floor(Math.log10(target)));
  const um = [1, 2, 5, 10].map(m => m * e).filter(v => v <= target * 1.4).pop() || e, len = um * pxPerUm;
  const x0 = 14, y0 = h - 16;
  x.fillStyle = "rgba(0,0,0,.5)"; x.fillRect(x0 - 6, y0 - 22, len + 12, 30);
  x.fillStyle = "#fff"; x.fillRect(x0, y0, len, 4);
  x.font = "12px system-ui"; x.textAlign = "center"; x.fillText(um >= 1000 ? `${um / 1000} mm` : `${um} µm`, x0 + len / 2, y0 - 6); x.textAlign = "start";
}
layer("viewer", drawViewer); layer("viewerSel", drawViewerSel); layer("viewerHov", drawViewerHov);
function outlinesChanged() { outlineVersion++; invalidate("viewerSel", "viewerHov", "cell"); }
function imageChanged() { renderVersion++; lastComp.clear(); invalidate("viewer", "cell"); }

// ---- navigation
function fitView(redraw = true) {
  const r = vwrap.getBoundingClientRect(); if (!r.width) return;
  view.s = Math.min(r.width / W0, r.height / H0); view.tx = (r.width - W0 * view.s) / 2; view.ty = (r.height - H0 * view.s) / 2; view.fitted = true; view.auto = true;
  if (redraw) invalidate("viewer");
}
function zoomAt(mx, my, f) { view.auto = false; const s = Math.max(0.01, Math.min(32, view.s * f)); view.tx = mx - (mx - view.tx) * s / view.s; view.ty = my - (my - view.ty) * s / view.s; view.s = s; invalidate("viewer"); }
function cellBox(i) {
  if (C.bbox_x0 && C.bbox_x0[i] !== null) return [C.bbox_x0[i], C.bbox_y0[i], C.bbox_x1[i], C.bbox_y1[i]];
  const r = Math.sqrt((C.area_px[i] || 100) / Math.PI) * 1.2; return [POSX[i] - r, POSY[i] - r, POSX[i] + r, POSY[i] + r];
}
function zoomTo(ids) {
  if (!ids.length) return;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const i of ids) { const b = cellBox(i); x0 = Math.min(x0, b[0]); y0 = Math.min(y0, b[1]); x1 = Math.max(x1, b[2]); y1 = Math.max(y1, b[3]); }
  const pad = Math.max(20, 0.15 * Math.max(x1 - x0, y1 - y0)); x0 -= pad; y0 -= pad; x1 += pad; y1 += pad;
  const r = vwrap.getBoundingClientRect(); view.auto = false;
  view.s = Math.min(32, Math.min(r.width / (x1 - x0), r.height / (y1 - y0)));
  view.tx = r.width / 2 - (x0 + x1) / 2 * view.s; view.ty = r.height / 2 - (y0 + y1) / 2 * view.s; invalidate("viewer");
}
function imgCoords(ev) { const r = vwrap.getBoundingClientRect(); return [(ev.clientX - r.left - view.tx) / view.s, (ev.clientY - r.top - view.ty) / view.s]; }
function labelAt(x, y) {
  if (x < 0 || y < 0 || x >= W0 || y >= H0) return -1;
  const L = chooseLevel(view.s);
  for (const lv of (L === OVERVIEW ? [] : [L, ...TLEVELS.filter(l => l.factor > L.factor)]).concat([OVERVIEW])) {
    const f = lv.factor ?? F0, lx = Math.floor(x / f), ly = Math.floor(y / f);
    const t = lv === OVERVIEW ? { L: null, x: 0, y: 0 } : { L: lv, tx: Math.floor(lx / TSIZE), ty: Math.floor(ly / TSIZE), x: Math.floor(lx / TSIZE) * TSIZE, y: Math.floor(ly / TSIZE) * TSIZE };
    const le = labCache.get(labKey(t)); if (!le) continue;
    const px = lx - t.x, py = ly - t.y; if (px < 0 || py < 0 || px >= le.w || py >= le.h) continue;
    const l = le.lab[py * le.w + px]; return l > 0 && l <= N ? l - 1 : -1;
  }
  return -1;
}
function initViewer() {
  let drag = null;
  vwrap.addEventListener("wheel", (e) => { if (!(e.ctrlKey || e.metaKey)) return; e.preventDefault(); const r = vwrap.getBoundingClientRect(); zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * 0.004)); }, { passive: false });
  vwrap.addEventListener("pointerdown", (e) => { if (e.shiftKey) return; vwrap.setPointerCapture(e.pointerId); drag = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty, moved: false }; });
  vwrap.addEventListener("pointermove", (e) => {
    if (drag) { const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true; if (drag.moved) { view.auto = false; view.tx = drag.tx + dx; view.ty = drag.ty + dy; invalidate("viewer"); } return; }
    const [x, y] = imgCoords(e); setHover(labelAt(x, y), e);
  });
  vwrap.addEventListener("pointerup", (e) => { const d = drag; drag = null; if (d && !d.moved) { const [x, y] = imgCoords(e); select(labelAt(x, y), e); } });
  vwrap.addEventListener("dblclick", (e) => { const [x, y] = imgCoords(e); const i = labelAt(x, y); if (i >= 0) zoomTo([i]); });
  vwrap.addEventListener("pointerleave", () => setHover(-1));
  attachSelector(vwrap, vsvg, (poly, add) => {
    const r = vwrap.getBoundingClientRect(), list = [];
    const img = poly.map(([px, py]) => [(px - view.tx) / view.s, (py - view.ty) / view.s]);
    for (let i = 0; i < N; i++) if (inPolygon(POSX[i], POSY[i], img)) list.push(i);
    selectMany(list, add);
  });
  const zc = (f) => { const r = vwrap.getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, f); };
  $("vzin").onclick = () => zc(1.6); $("vzout").onclick = () => zc(1 / 1.6); $("vfit").onclick = () => fitView();
  $("vzsel").onclick = () => zoomTo(S.sel.size ? [...S.sel] : HIT.map((h, i) => h ? i : -1).filter(i => i >= 0));
  $("outl").value = S.outl; $("outl").onchange = () => { S.outl = $("outl").value; outlinesChanged(); };
  $("isrc").onchange = () => { S.isrc = $("isrc").value; imageChanged(); };
  $("bright").oninput = () => { S.bright = Math.pow(10, +$("bright").value); imageChanged(); };
  $("vroute").checked = S.showRoute; $("vroute").onchange = () => { S.showRoute = $("vroute").checked; invalidate("viewerHov"); };
  const fm = $("vfill"); fm.add(new Option("lifetime image", "")); METRIC_KEYS.forEach(k => fm.add(new Option(k, k)));
  fm.onchange = () => { S.fillMetric = fm.value; fillsChanged(); };
  $("vscale").checked = S.scalebar; $("vscale").onchange = () => { S.scalebar = $("vscale").checked; invalidate("viewerHov"); };
  hitRGB = hexToRgb(css("--hit"));
  new ResizeObserver(() => { if (!view.fitted || view.auto) fitView(false); invalidate("viewer"); }).observe(vwrap);
}
