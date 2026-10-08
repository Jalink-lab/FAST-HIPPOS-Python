// ---------------------------------------------------------------- distribution of the current frame
const HP = new Plot([$("hib")], { l: 50, r: 12, t: 10, b: 30 });
function histogram(t, filter) {
  const nb = D.display.bins, h = new Float64Array(nb), k = K(); let s = 0, s2 = 0, n = 0;
  for (let i = 0; i < N; i++) { if (!filter(i)) continue; const v = k[t * N + i]; if (Number.isNaN(v)) continue; s += v; s2 += v * v; n++; const b = Math.floor((v - S.dmin) / (S.dmax - S.dmin) * nb); if (b >= 0 && b < nb) h[b]++; }
  const mean = n ? s / n : NaN; return { h, n, mean, sd: n > 1 ? Math.sqrt(Math.max(0, s2 / n - mean * mean)) : NaN };
}
function drawHist() {
  HP.resize(); const all = histogram(S.frame, visible), nb = D.display.bins;
  const hits = HIT.some(Boolean) ? histogram(S.frame, i => visible(i) && HIT[i]) : null;
  const sel = S.sel.size ? histogram(S.frame, i => S.sel.has(i)) : null;
  let max = 1; all.h.forEach(v => max = Math.max(max, v));
  HP.range(S.dmin, S.dmax, 0, max * 1.08);
  const ctx = HP.clear(0); HP.axes(ctx, D.is_lifetime ? "lifetime (ns)" : D.unit, "cells"); ctx.save(); HP.clip(ctx);
  const bw = (S.dmax - S.dmin) / nb, rgb = [0, 0, 0];
  for (let b = 0; b < nb; b++) { lutRGB(S.dmin + (b + 0.5) * bw, rgb); ctx.fillStyle = `rgb(${rgb})`; const x0 = HP.X(S.dmin + b * bw), x1 = HP.X(S.dmin + (b + 1) * bw); ctx.fillRect(x0 + 0.5, HP.Y(all.h[b]), Math.max(1, x1 - x0 - 1), HP.Y(0) - HP.Y(all.h[b])); }
  const outline = (H, col) => { ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.beginPath(); for (let b = 0; b < nb; b++) { const x0 = HP.X(S.dmin + b * bw), x1 = HP.X(S.dmin + (b + 1) * bw), y = HP.Y(H.h[b]); b ? ctx.lineTo(x0, y) : ctx.moveTo(x0, y); ctx.lineTo(x1, y); } ctx.stroke(); };
  if (hits && hits.n) outline(hits, css("--hit")); if (sel && sel.n) outline(sel, css("--sel"));
  ctx.restore();
  $("distinfo").textContent = `t = ${(S.frame * FI).toFixed(1)} s · mean ± sd ${fmt(all.mean)} ± ${fmt(all.sd)} (n=${all.n})` + (hits && hits.n ? ` · hits ${fmt(hits.mean)}` : "") + (sel && sel.n ? ` · selection ${fmt(sel.mean)}` : "");
}
layer("hist", drawHist);
