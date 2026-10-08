// ---------------------------------------------------------------- cell card: crop movie, trace vs population, pass/fail per criterion
const CP = new Plot([$("cctr")], { l: 44, r: 8, t: 8, b: 26 });
let popBand = null, popBandKey = "";
function focusCell() { return S.hover >= 0 ? S.hover : (S.sel.has(S.lastClicked) ? S.lastClicked : (S.sel.size ? [...S.sel][0] : -1)); }
function drawCell() {
  const i = focusCell(), box = $("ccbody");
  if (i < 0) { box.classList.add("empty"); $("cctitle").textContent = "Cell"; return; }
  box.classList.remove("empty");
  $("cctitle").innerHTML = `Cell ${C.cell[i]}` + (HIT[i] ? ` <span class="badge hit">hit</span>` : "") +
    (C.valid ? (C.valid[i] ? ` <span class="badge ok">valid</span>` : ` <span class="badge bad">fails gates</span>`) : "") +
    (C.class_additional ? (C.class_additional[i] ? ` <span class="badge">ch+</span>` : ` <span class="badge muted">ch−</span>`) : "");
  // crop: square around the cell, at the best available resolution
  const cv = $("cccrop"), dpr = window.devicePixelRatio || 1, cw = cv.clientWidth || 200, ch = cv.clientHeight || 200;
  cv.width = cw * dpr; cv.height = ch * dpr; const x = cv.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0);
  x.fillStyle = "#000"; x.fillRect(0, 0, cw, ch);
  const b = cellBox(i), size = Math.max(b[2] - b[0], b[3] - b[1]) * 1.8 + 8, cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
  const vw = { s: Math.min(cw, ch) / size }; vw.tx = cw / 2 - cx * vw.s; vw.ty = ch / 2 - cy * vw.s;
  renderImage(x, cw, ch, vw, ["cell"]);
  const L = chooseLevel(vw.s);
  (L === OVERVIEW ? [{ L: null }] : tilesInView(L, cw, ch, vw)).forEach(t => request(labKey(t), ["cell"]));
  x.fillStyle = css("--hover"); for (const [px, py, sz] of cellBoundary(i, cw, ch, vw)) x.fillRect(px, py, Math.max(1, sz), Math.max(1, sz));
  x.fillStyle = "rgba(0,0,0,.55)"; x.fillRect(0, ch - 18, cw, 18); x.fillStyle = "#fff"; x.font = "11px system-ui";
  x.fillText(`t = ${(S.frame * FI).toFixed(0)} s · ${fmt(val(S.frame, i))} ${D.is_lifetime ? "ns" : ""}`, 6, ch - 5);
  // trace vs population
  CP.resize(); CP.range(0, Math.max(1, T - 1) * FI, ...yRange());
  const c = CP.clear(0); CP.axes(c, null, null); c.save(); CP.clip(c);
  const key = `${S.tsrc}|${SCR.version}|${S.show}|${S.show === "sel" ? S.sel.size : 0}`;
  if (key !== popBandKey) { const ids = []; for (let j = 0; j < N; j++) if (visible(j)) ids.push(j); popBand = bandStats(ids, K()); popBandKey = key; }
  const ev = EV, shade = (a, bb, col) => { if (bb > a) { c.fillStyle = col; c.fillRect(CP.X(a * FI), CP.m.t, CP.X(Math.max(a, bb - 1) * FI) - CP.X(a * FI) || 2, CP.ph); } };
  if (!ev.baseline_only) { shade(ev.baseline[0], ev.baseline[1], css("--base-win")); shade(ev.timed_window[0], ev.timed_window[1], css("--resp-win")); shade(ev.calibration_window[0], ev.calibration_window[1], css("--cal-win")); }
  const xs = new Float32Array(T); for (let t = 0; t < T; t++) xs[t] = CP.X(t * FI);
  const area = (lo, hi) => { c.fillStyle = withAlpha(css("--muted"), 0.18); c.beginPath(); for (let t = 0; t < T; t++) c.lineTo(xs[t], CP.Y(hi[t])); for (let t = T - 1; t >= 0; t--) c.lineTo(xs[t], CP.Y(lo[t])); c.fill(); };
  area(popBand[1], popBand[3]);
  const line = (arr, col, w) => { c.strokeStyle = col; c.lineWidth = w; c.beginPath(); let pen = false; for (let t = 0; t < T; t++) { const v = arr(t); if (!Number.isFinite(v)) { pen = false; continue; } pen ? c.lineTo(xs[t], CP.Y(v)) : c.moveTo(xs[t], CP.Y(v)); pen = true; } c.stroke(); };
  line(t => popBand[2][t], css("--muted"), 1.5);
  if (S.tsrc === "smoothed") line(t => KR[t * N + i], withAlpha(css("--text"), 0.35), 1);
  line(t => K()[t * N + i], HIT[i] ? css("--hit") : css("--accent"), 2.2);
  if (Number.isFinite(C.baseline_mean[i])) { c.setLineDash([3, 3]); c.strokeStyle = css("--text"); c.lineWidth = 1; c.beginPath(); c.moveTo(CP.m.l, CP.Y(C.baseline_mean[i])); c.lineTo(CP.m.l + CP.pw, CP.Y(C.baseline_mean[i])); c.stroke(); c.setLineDash([]); }
  const fx = CP.X(S.frame * FI); c.strokeStyle = css("--accent"); c.lineWidth = 1; c.beginPath(); c.moveTo(fx, CP.m.t); c.lineTo(fx, CP.m.t + CP.ph); c.stroke();
  c.restore();
  // checklist
  const p = SCR.params, rows = [];
  const mark = (ok) => ok ? `<span class="ok">✓</span>` : `<span class="bad">✗</span>`;
  if (p.baseline_calibration_diff) { const v = C.calibration_diff[i]; rows.push([mark(v >= p.baseline_calibration_diff[0] && v <= p.baseline_calibration_diff[1]), "gate: calibration − baseline", fmt(v)]); }
  if (p.max_baseline_deviation !== null && p.max_baseline_deviation !== undefined) { const v = C.baseline_dev_pop[i]; rows.push([mark(Math.abs(v) <= p.max_baseline_deviation), "gate: |baseline − population|", fmt(Math.abs(v))]); }
  p.criteria.forEach((cr, k) => { const v = C[cr.metric] ? C[cr.metric][i] : NaN; rows.push([SCR.pass[k] ? mark(SCR.pass[k][i]) : "", `<span class="pill ${cr.logic.toLowerCase()}">${cr.logic}</span> ${critText(cr)}`, fmt(v)]); });
  for (const m of ["baseline_mean", "response_max_diff", "rise_time_frames", "additional_intensity"]) if (C[m] && !p.criteria.some(cr => cr.metric === m)) rows.push(["", m, fmt(C[m][i])]);
  $("cclist").innerHTML = rows.map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td></tr>`).join("");
}
let cellTimer = null;
layer("cell", () => { clearTimeout(cellTimer); cellTimer = setTimeout(drawCell, 40); });  // coalesce while hovering
