// ---------------------------------------------------------------- response over time (one curve per image)
const RP = new Plot([$("rpb"), $("rph")], { l: 52, r: 12, t: 10, b: 32 });
// time of frame f: with 'align', 0 is the transition into the stimulation frame (as the S marker of the dashboard)
const tOffset = (im) => (S.align && im.events.stimulation !== null ? (im.events.stimulation - 0.5) * im.frame_interval : 0);
const bandsOf = (im) => (S.hitsOnly && im.BH ? im.BH : im.B);
function drawLegend() {
  const ks = selected();
  $("legend").innerHTML = ks.map(k => `<button class="lchip ${S.hidden.has(k) ? "off" : ""}" data-k="${k}" title="${esc(IM[k].name)}: click to ${S.hidden.has(k) ? "show" : "hide"} its curve"><span class="sw" style="background:${imgColor(k)}"></span><span class="n">${esc(IM[k].name)}</span></button>`).join("");
}
function drawResp() {
  RP.resize(); const ctx = RP.clear(0); RP.clear(1);
  const ks = shown();
  if (!ks.length) { ctx.fillStyle = css("--muted"); ctx.font = "13px system-ui"; ctx.fillText(selected().length ? "All curves are hidden: click a name above" : "Select images in the table", RP.m.l + 10, RP.m.t + 24); $("rnote").textContent = ""; return; }
  let x0 = Infinity, x1 = -Infinity;
  for (const k of ks) { const im = IM[k], off = tOffset(im); x0 = Math.min(x0, -off); x1 = Math.max(x1, (im.frames - 1) * im.frame_interval - off); }
  if (!(x1 > x0)) x1 = x0 + 1;
  RP.range(x0, x1, D.y_range[0], D.y_range[1]);
  // the windows (baseline, response, calibration) of the first image shown; a note when the others differ
  const ref = IM[ks.find(k => !IM[k].events.baseline_only && IM[k].events.stimulation !== null) ?? ks[0]], same = ks.every(k => JSON.stringify([IM[k].events.baseline, IM[k].events.response, IM[k].events.calibration_window]) ===
    JSON.stringify([ref.events.baseline, ref.events.response, ref.events.calibration_window]) && IM[k].frame_interval === ref.frame_interval);
  shadeFor(ctx, ref);
  const aligned = S.align && ks.some(k => IM[k].events.stimulation !== null);
  RP.axes(ctx, aligned ? "time from stimulation (s)" : "time (s)", D.is_lifetime ? "lifetime (ns)" : D.unit);
  ctx.save(); RP.clip(ctx);
  const hov = ks.includes(S.hover) ? S.hover : -1;
  for (const k of ks) {
    const im = IM[k], B = bandsOf(im), T = im.frames, off = tOffset(im), col = imgColor(k);
    if (!B) continue;
    const X = (f) => RP.X(f * im.frame_interval - off), Y = (v) => RP.Y(v);
    const fade = hov >= 0 && hov !== k ? 0.3 : 1;
    const band = (lo, hi, alpha) => {
      ctx.beginPath(); let started = false;
      for (let t = 0; t < T; t++) { const v = B[hi * T + t]; if (!Number.isFinite(v)) continue; started ? ctx.lineTo(X(t), Y(v)) : ctx.moveTo(X(t), Y(v)); started = true; }
      for (let t = T - 1; t >= 0; t--) { const v = B[lo * T + t]; if (Number.isFinite(v)) ctx.lineTo(X(t), Y(v)); }
      ctx.closePath(); ctx.fillStyle = withAlpha(col, alpha * fade); ctx.fill();
    };
    if (ks.length === 1) band(0, 4, 0.12);
    band(1, 3, ks.length > 6 ? 0 : 0.2);
    ctx.beginPath(); let started = false;
    for (let t = 0; t < T; t++) { const v = B[2 * T + t]; if (!Number.isFinite(v)) { started = false; continue; } started ? ctx.lineTo(X(t), Y(v)) : ctx.moveTo(X(t), Y(v)); started = true; }
    ctx.strokeStyle = withAlpha(col, fade); ctx.lineWidth = hov === k ? 2.6 : 1.6; ctx.stroke();
  }
  ctx.restore();
  const notes = [];
  if (!same) notes.push(`Shaded windows: those of ${ref.name} (the selected images differ)`);
  if (S.hitsOnly) { const none = ks.filter(k => !IM[k].BH).map(k => IM[k].name); if (none.length) notes.push(`No hits in: ${none.join(", ")}`); }
  $("rnote").textContent = notes.join(" · ");
}
function shadeFor(ctx, im) {
  const ev = im.events, off = tOffset(im), FIm = im.frame_interval;
  const block = (w, col) => { if (!w || !(w[1] > w[0])) return; const a = RP.X((w[0] - 0.5) * FIm - off), b = RP.X((w[1] - 0.5) * FIm - off); ctx.fillStyle = col; ctx.fillRect(a, RP.m.t, b - a, RP.ph); };
  if (ev.baseline_only) return;
  block(ev.baseline, css("--base-win")); block(ev.response, withAlpha(css("--resp-solid"), 0.1)); block(ev.calibration_window, css("--cal-win"));
}
// hover: the value of each curve at that time
function respHover(e) {
  const [px, py] = localXY(e, $("rph")); const ks = shown();
  if (!ks.length || !RP.inside(px, py)) { showTip(null); return; }
  const t = RP.iX(px), rows = ks.map(k => { const im = IM[k], B = bandsOf(im); if (!B) return ""; const f = Math.round((t + tOffset(im)) / im.frame_interval);
    if (f < 0 || f >= im.frames) return ""; return `<span class="sw" style="background:${imgColor(k)}"></span> ${esc(im.name)}: ${fmt(B[2 * im.frames + f])} <span class="muted">(${fmt(B[im.frames + f])}–${fmt(B[3 * im.frames + f])})</span>`; }).filter(Boolean);
  showTip(`<b>t = ${fmt(t, 1)} s</b><br>${rows.join("<br>")}`, e);
}

// ---------------------------------------------------------------- cells: distribution per image, or a scatter plot
const MP = new Plot([$("mpb"), $("mph")], { l: 150, r: 14, t: 10, b: 34 });
const ROW_H = 44;
const finite = (a, log) => Array.from(a || []).filter(v => Number.isFinite(v) && (!log || v > 0));
function sharedRange(ks, m, log) {
  const all = []; for (const k of ks) for (const v of finite(IM[k].C[m], log)) all.push(v);
  if (!all.length) return log ? [0.1, 10] : [0, 1];
  let [a, b] = quantiles(all, [0.01, 0.99]);
  if (!(b > a)) { a = log ? a / 2 : a - 0.5; b = log ? b * 2 : b + 0.5; }
  const pad = log ? 1.15 : (b - a) * 0.05; return log ? [a / pad, b * pad] : [a - pad, b + pad];
}
function drawMetric() {
  const ks = shown(), m = S.metric, dist = S.cmode === "dist";
  $("myl").style.display = dist ? "none" : ""; $("logyl").style.display = dist ? "none" : "";
  $("mxl").textContent = dist ? "value" : "x"; $("logxl").textContent = dist ? "log" : "log x";
  $("mstack").style.height = (dist ? Math.max(220, ks.length * ROW_H + 50) : 340) + "px";
  MP.m.l = dist ? 150 : 56; MP.logx = S.logx; MP.logy = dist ? false : S.logy;
  MP.resize(); const ctx = MP.clear(0); MP.clear(1);
  if (!ks.length || !m) { ctx.fillStyle = css("--muted"); ctx.font = "13px system-ui"; ctx.fillText("Select images in the table", 20, 30); $("mnote").textContent = ""; return; }
  const sampled = ks.filter(k => IM[k].n_shown < IM[k].n_cells);
  $("mnote").textContent = sampled.length ? `Large images are shown with a sample of ${D.max_cells.toLocaleString("en")} cells (all hits included): ${sampled.map(k => IM[k].name).join(", ")}` : "";
  dist ? drawDistributions(ctx, ks, m) : drawScatter(ctx, ks);
}
function drawDistributions(ctx, ks, m) {
  const [a, b] = sharedRange(ks, m, S.logx); MP.range(a, b, 0, ks.length);
  const tx = (v) => (S.logx ? Math.log10(v) : v), nb = 40, bw = (tx(b) - tx(a)) / nb;
  ctx.font = "11px system-ui, sans-serif";
  const hov = ks.includes(S.hover) ? S.hover : -1;
  ks.forEach((k, r) => {
    const im = IM[k], vals = im.C[m], hit = im.C.hit, top = MP.m.t + r * ROW_H, h = ROW_H - 10, col = imgColor(k), fade = hov >= 0 && hov !== k ? 0.35 : 1;
    const cnt = new Float64Array(nb), fin = [];
    for (let i = 0; i < im.n_shown; i++) { const v = vals ? vals[i] : NaN; if (!Number.isFinite(v) || (S.logx && v <= 0)) continue; fin.push(v); const j = Math.floor((tx(v) - tx(a)) / bw); if (j >= 0 && j < nb) cnt[j]++; }
    const mx = Math.max(1, ...cnt);
    if (!fin.length) { ctx.fillStyle = css("--muted"); ctx.textBaseline = "middle"; ctx.textAlign = "left"; ctx.fillText(`no values of ${m} in this image`, MP.m.l + 8, top + h / 2); }
    ctx.fillStyle = withAlpha(col, 0.55 * fade);
    for (let j = 0; j < nb; j++) { if (!cnt[j]) continue; const x0 = MP.X(S.logx ? Math.pow(10, tx(a) + j * bw) : a + j * bw), x1 = MP.X(S.logx ? Math.pow(10, tx(a) + (j + 1) * bw) : a + (j + 1) * bw); const bh = (cnt[j] / mx) * h; ctx.fillRect(x0, top + h - bh, Math.max(1, x1 - x0 - 1), bh); }
    const [q1, q2, q3] = quantiles(fin, [0.25, 0.5, 0.75]);
    if (Number.isFinite(q2)) { ctx.strokeStyle = withAlpha(col, fade); ctx.lineWidth = 1.5; ctx.strokeRect(MP.X(q1), top + h + 2, Math.max(1, MP.X(q3) - MP.X(q1)), 4); ctx.beginPath(); ctx.moveTo(MP.X(q2), top - 1); ctx.lineTo(MP.X(q2), top + h + 6); ctx.stroke(); }
    if (hit) { ctx.strokeStyle = withAlpha(css("--hit"), 0.9 * fade); ctx.lineWidth = 1; ctx.beginPath(); for (let i = 0; i < im.n_shown; i++) { if (!hit[i]) continue; const v = vals[i]; if (!Number.isFinite(v)) continue; const x = MP.X(v); ctx.moveTo(x, top + h - 7); ctx.lineTo(x, top + h); } ctx.stroke(); }
    ctx.fillStyle = col; ctx.fillRect(8, top + h / 2 - 5, 10, 10);
    ctx.fillStyle = hov === k ? css("--text") : css("--muted"); ctx.textBaseline = "middle"; ctx.textAlign = "left";
    let name = im.name; while (name.length > 3 && ctx.measureText(name).width > MP.m.l - 34) name = name.slice(0, -2);
    ctx.fillText(name === im.name ? name : name + "…", 24, top + h / 2);
  });
  // thresholds of the hit criteria on this value
  for (const c of D.criteria.filter(c => c.metric === m)) for (const v of [c.value, c.op === "between" ? c.value2 : null]) {
    if (v === null || !(v > a && v < b)) continue; const x = MP.X(v);
    ctx.save(); ctx.setLineDash([4, 3]); ctx.strokeStyle = css("--text"); ctx.globalAlpha = 0.6; ctx.beginPath(); ctx.moveTo(x, MP.m.t - 4); ctx.lineTo(x, MP.m.t + MP.ph); ctx.stroke(); ctx.restore();
  }
  // x axis
  ctx.fillStyle = css("--muted"); ctx.textAlign = "center"; ctx.textBaseline = "top";
  const ticks = S.logx ? logTicks(a, b) : niceTicks(a, b, Math.max(2, Math.floor(MP.pw / 80)));
  for (const v of ticks) { const x = MP.X(v); if (x < MP.m.l || x > MP.m.l + MP.pw) continue; ctx.fillText(tickFmt(v), x, MP.m.t + MP.ph + 4); }
  ctx.textBaseline = "bottom"; ctx.fillText(m, MP.m.l + MP.pw / 2, MP.h - 1);
}
function drawScatter(ctx, ks) {
  const mx = S.metric, my = S.metricY, [x0, x1] = sharedRange(ks, mx, S.logx), [y0, y1] = sharedRange(ks, my, S.logy);
  MP.range(x0, x1, y0, y1); MP.axes(ctx, mx, my); ctx.save(); MP.clip(ctx);
  const hov = ks.includes(S.hover) ? S.hover : -1;
  // the image under the mouse on top; the others dimmed, their hit rings too
  for (const k of [...ks.filter(k => k !== hov), ...ks.filter(k => k === hov)]) {
    const im = IM[k], X = im.C[mx], Y = im.C[my], hit = im.C.hit; if (!X || !Y) continue;
    const dim = hov >= 0 && hov !== k;
    ctx.fillStyle = withAlpha(imgColor(k), dim ? 0.12 : 0.5);
    for (let i = 0; i < im.n_shown; i++) { if (!Number.isFinite(X[i]) || !Number.isFinite(Y[i])) continue; ctx.fillRect(MP.X(X[i]) - 1.2, MP.Y(Y[i]) - 1.2, 2.4, 2.4); }
    if (hit) { ctx.strokeStyle = withAlpha(css("--hit"), dim ? 0.2 : 1); ctx.lineWidth = 1.2; for (let i = 0; i < im.n_shown; i++) { if (!hit[i] || !Number.isFinite(X[i]) || !Number.isFinite(Y[i])) continue; ctx.beginPath(); ctx.arc(MP.X(X[i]), MP.Y(Y[i]), 3.2, 0, 7); ctx.stroke(); } }
  }
  ctx.restore();
}
function metricPick(e) {  // what is under the mouse: a row of the distributions, or the nearest point of the scatter
  const [px, py] = localXY(e, $("mph")), ks = shown(); if (!ks.length || !MP.inside(px, py)) return null;
  if (S.cmode === "dist") { const r = Math.floor((py - MP.m.t) / ROW_H); return r >= 0 && r < ks.length ? { k: ks[r] } : null; }
  let best = null, bd = 64;
  for (const k of ks) { const im = IM[k], X = im.C[S.metric], Y = im.C[S.metricY]; if (!X || !Y) continue;
    for (let i = 0; i < im.n_shown; i++) { if (!Number.isFinite(X[i]) || !Number.isFinite(Y[i])) continue; const d = (MP.X(X[i]) - px) ** 2 + (MP.Y(Y[i]) - py) ** 2; if (d < bd) { bd = d; best = { k, i }; } } }
  return best;
}
function metricHover(e) {
  const p = metricPick(e); if (!p) { showTip(null); return; }
  const im = IM[p.k], m = S.metric;
  if (p.i === undefined) {
    const fin = finite(im.C[m], S.logx), [q1, q2, q3] = quantiles(fin, [0.25, 0.5, 0.75]), nh = im.C.hit ? Array.from(im.C.hit).filter(Boolean).length : 0;
    showTip(`<b>${esc(im.name)}</b><br>${m}: median ${fmt(q2)} <span class="muted">(25–75 %: ${fmt(q1)}–${fmt(q3)})</span><br>${fin.length.toLocaleString("en")} cells shown${SCREEN ? ` · ${nh} hits` : ""}`, e);
  } else {
    const c = im.C.cell[p.i];
    showTip(`<b>${esc(im.name)} · cell ${c}</b>${im.C.hit && im.C.hit[p.i] ? ' · <span class="h">hit</span>' : ""}<br>${S.metric}: ${fmt(im.C[S.metric][p.i])}<br>${S.metricY}: ${fmt(im.C[S.metricY][p.i])}${im.href ? '<br><span class="muted">click to open in the dashboard</span>' : ""}`, e);
  }
}
function initPanels() {
  $("legend").addEventListener("click", (e) => { const b = e.target.closest("[data-k]"); if (!b) return; const k = +b.dataset.k; S.hidden.has(k) ? S.hidden.delete(k) : S.hidden.add(k); invalidate("legend", "resp", "metric", "maps", "hits"); });
  $("legend").addEventListener("mouseover", (e) => { const b = e.target.closest("[data-k]"); setHover(b ? +b.dataset.k : -1); });
  $("legend").addEventListener("mouseleave", () => setHover(-1));
  $("align").checked = S.align; $("align").disabled = !hasStim; if (!hasStim) $("align").parentElement.title = "No image of this run has a stimulation";
  $("align").onchange = () => { S.align = $("align").checked; invalidate("resp"); };
  $("hitsOnlyL").style.display = SCREEN ? "" : "none"; $("hitsOnly").onchange = () => { S.hitsOnly = $("hitsOnly").checked; invalidate("resp"); };
  $("rph").addEventListener("mousemove", respHover); $("rph").addEventListener("mouseleave", () => showTip(null));
  for (const id of ["metric", "metricY"]) { const sel = $(id); METRIC_KEYS.forEach(m => { const o = new Option(m, m); o.title = metricTip(m); sel.add(o); }); }
  $("metric").value = S.metric; $("metricY").value = S.metricY;
  const tipSel = () => { $("metric").title = metricTip(S.metric); $("metricY").title = metricTip(S.metricY); }; tipSel();
  $("metric").onchange = () => { S.metric = $("metric").value; tipSel(); invalidate("metric"); };
  $("metricY").onchange = () => { S.metricY = $("metricY").value; tipSel(); invalidate("metric"); };
  $("logx").onchange = () => { S.logx = $("logx").checked; invalidate("metric"); }; $("logy").onchange = () => { S.logy = $("logy").checked; invalidate("metric"); };
  const seg = () => document.querySelectorAll("#cmode button").forEach(b => b.classList.toggle("on", b.dataset.v === S.cmode)); seg();
  $("cmode").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; S.cmode = b.dataset.v; seg(); invalidate("metric"); });
  $("mph").addEventListener("mousemove", (e) => { metricHover(e); const p = metricPick(e); setHover(p ? p.k : -1); });
  $("mph").addEventListener("mouseleave", () => { showTip(null); setHover(-1); });
  $("mph").addEventListener("click", (e) => { const p = metricPick(e); if (p && p.i !== undefined) openCell(IM[p.k], IM[p.k].C.cell[p.i]); });
}
layer("legend", drawLegend); layer("resp", drawResp); layer("metric", drawMetric);
