// ---------------------------------------------------------------- plot geometry shared by all charts
class Plot {
  constructor(canvases, margin = { l: 50, r: 12, t: 10, b: 32 }) { this.cs = canvases; this.m = margin; this.logx = false; this.logy = false; }
  resize() {
    const r = this.cs[0].getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    this.w = r.width; this.h = r.height; this.dpr = dpr;
    for (const c of this.cs) { const W = Math.max(1, Math.round(r.width * dpr)), H = Math.max(1, Math.round(r.height * dpr)); if (c.width !== W) c.width = W; if (c.height !== H) c.height = H; }
    this.pw = Math.max(1, this.w - this.m.l - this.m.r); this.ph = Math.max(1, this.h - this.m.t - this.m.b);
  }
  ctx(i = 0) { const x = this.cs[i].getContext("2d"); x.setTransform(this.dpr, 0, 0, this.dpr, 0, 0); return x; }
  clear(i) { const x = this.ctx(i); x.clearRect(0, 0, this.w, this.h); return x; }
  range(x0, x1, y0, y1) { this.x0 = x0; this.x1 = x1; this.y0 = y0; this.y1 = y1; }
  tx(v) { return this.logx ? Math.log10(Math.max(v, 1e-12)) : v; }
  ty(v) { return this.logy ? Math.log10(Math.max(v, 1e-12)) : v; }
  X(v) { const a = this.tx(this.x0), b = this.tx(this.x1); return this.m.l + (this.tx(v) - a) / (b - a || 1) * this.pw; }
  Y(v) { const a = this.ty(this.y0), b = this.ty(this.y1); return this.m.t + (1 - (this.ty(v) - a) / (b - a || 1)) * this.ph; }
  iX(px) { const a = this.tx(this.x0), b = this.tx(this.x1); const v = a + (px - this.m.l) / this.pw * (b - a); return this.logx ? Math.pow(10, v) : v; }
  iY(py) { const a = this.ty(this.y0), b = this.ty(this.y1); const v = a + (1 - (py - this.m.t) / this.ph) * (b - a); return this.logy ? Math.pow(10, v) : v; }
  axes(ctx, xl, yl, opt = {}) {
    ctx.save(); ctx.font = "11px system-ui, sans-serif"; ctx.fillStyle = css("--muted"); ctx.strokeStyle = css("--grid"); ctx.lineWidth = 1;
    const xt = this.logx ? logTicks(this.x0, this.x1) : niceTicks(this.x0, this.x1, Math.max(2, Math.floor(this.pw / 70)));
    const yt = this.logy ? logTicks(this.y0, this.y1) : niceTicks(this.y0, this.y1, Math.max(2, Math.floor(this.ph / 40)));
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    for (const v of xt) { const x = this.X(v); if (x < this.m.l - 1 || x > this.m.l + this.pw + 1) continue; if (!opt.nogrid) { ctx.beginPath(); ctx.moveTo(x, this.m.t); ctx.lineTo(x, this.m.t + this.ph); ctx.stroke(); } ctx.fillText(tickFmt(v), x, this.m.t + this.ph + 4); }
    ctx.textAlign = "right"; ctx.textBaseline = "middle";
    for (const v of yt) { const y = this.Y(v); if (y < this.m.t - 1 || y > this.m.t + this.ph + 1) continue; if (!opt.nogrid) { ctx.beginPath(); ctx.moveTo(this.m.l, y); ctx.lineTo(this.m.l + this.pw, y); ctx.stroke(); } ctx.fillText(tickFmt(v), this.m.l - 5, y); }
    ctx.textAlign = "center"; ctx.textBaseline = "bottom"; if (xl) ctx.fillText(xl, this.m.l + this.pw / 2, this.h - 1);
    if (yl) { ctx.translate(11, this.m.t + this.ph / 2); ctx.rotate(-Math.PI / 2); ctx.textBaseline = "middle"; ctx.fillText(yl, 0, 0); }
    ctx.restore();
  }
  clip(ctx) { ctx.beginPath(); ctx.rect(this.m.l, this.m.t, this.pw, this.ph); ctx.clip(); }
  inside(px, py) { return px >= this.m.l && px <= this.m.l + this.pw && py >= this.m.t && py <= this.m.t + this.ph; }
}
function niceTicks(a, b, n) {
  if (a > b) [a, b] = [b, a];
  if (!(b > a)) return [a];
  const span = b - a, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= n) || 10 * mag;
  const out = []; for (let v = Math.ceil(a / step) * step; v <= b + step * 1e-9; v += step) out.push(+v.toPrecision(12)); return out;
}
function logTicks(a, b) {
  if (a > b) [a, b] = [b, a];
  const out = [], e0 = Math.floor(Math.log10(Math.max(a, 1e-12))), e1 = Math.ceil(Math.log10(Math.max(b, 1e-12)));
  for (let e = e0; e <= e1; e++) for (const m of (e1 - e0 <= 2 ? [1, 2, 5] : [1])) out.push(m * Math.pow(10, e));
  return out;
}
function tickFmt(v) { const a = Math.abs(v); return a >= 1e6 || (a < 1e-3 && a > 0) ? v.toExponential(1) : String(+v.toPrecision(4)); }
function localXY(ev, el) { const r = el.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; }
function finiteRange(arr, ids, log) {
  let a = Infinity, b = -Infinity;
  for (const i of ids) { const v = arr[i]; if (!Number.isFinite(v) || (log && v <= 0)) continue; if (v < a) a = v; if (v > b) b = v; }
  if (!Number.isFinite(a)) return log ? [0.1, 10] : [0, 1];
  if (a === b) { if (log) return [a / 2, b * 2]; a -= 0.5; b += 0.5; }
  if (log) return [a / 1.2, b * 1.2];
  const p = (b - a) * 0.05; return [a - p, b + p];
}
// quantiles of the finite values of an array (sorted copy)
function quantiles(values, qs) {
  const a = values.filter(Number.isFinite).sort((x, y) => x - y);
  if (!a.length) return qs.map(() => NaN);
  return qs.map(q => { const p = (a.length - 1) * q, i = Math.floor(p), f = p - i; return i + 1 < a.length ? a[i] * (1 - f) + a[i + 1] * f : a[i]; });
}
