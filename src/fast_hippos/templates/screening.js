// FAST-HIPPOS screening in the browser. Mirrors fast_hippos.events / screening / kymograph.smooth_time
// exactly (tested against the Python implementation in tests/test_dashboard_js.py).
// Kymographs are Float32Array(T * N), row-major: K[t * N + i].
"use strict";
const FHScreen = (() => {
  const nan = NaN;

  function windows(T, ev) {
    const m = ev.margin ?? 1, s = ev.stimulation, c = ev.calibration;
    const none = ev.baseline_only || (s === null && c === null);
    const first = s !== null ? s : c;
    const baseline = none ? [0, T] : [0, Math.max(first - m, 1)];
    let response = [0, 0];
    if (!ev.baseline_only && s !== null) {
      const end = c !== null ? c - m : T;
      response = [s, Math.max(end, s + 1)];
    }
    const calibration = ev.baseline_only || c === null ? [0, 0] : [c, T];
    return { baseline: clip(baseline, T), response: clip(response, T), calibration: clip(calibration, T) };
  }
  function clip(w, T) { const a = Math.max(0, Math.min(T, w[0])), b = Math.max(0, Math.min(T, w[1])); return [a, Math.max(a, b)]; }

  function timedWindow(resp, p) {
    const [r0, r1] = resp, w = p.response_window, m = p.response_window_margin;
    if (r1 <= r0 || w < 0) return [r0, r1];
    if (p.response_window_anchor === "after_stimulation") { const a = Math.min(r0 + m, r1); return [a, Math.min(a + w, r1)]; }
    const b = Math.max(r1 - m, r0); return [Math.max(b - w, r0), b];
  }

  function smooth(K, T, N, radius) {
    const r = Math.floor(radius);
    if (r <= 0) return K;
    const out = new Float32Array(T * N);
    for (let i = 0; i < N; i++) for (let t = 0; t < T; t++) {
      let s = 0, n = 0;
      for (let k = -r; k <= r; k++) { const tt = Math.min(T - 1, Math.max(0, t + k)); const v = K[tt * N + i]; if (!Number.isNaN(v)) { s += v; n++; } }
      out[t * N + i] = n ? s / n : nan;
    }
    return out;
  }

  function colMean(K, N, i, a, b) { let s = 0, n = 0; for (let t = a; t < b; t++) { const v = K[t * N + i]; if (!Number.isNaN(v)) { s += v; n++; } } return n ? s / n : nan; }
  function colMax(K, N, i, a, b) { let m = -Infinity, n = 0; for (let t = a; t < b; t++) { const v = K[t * N + i]; if (!Number.isNaN(v)) { if (v > m) m = v; n++; } } return n ? m : nan; }

  // Response metrics for all cells. Returns {cols: {name: Float64Array}, population_baseline}
  function metrics(K, T, N, ev, p, additional) {
    const win = windows(T, ev), [b0, b1] = win.baseline, [r0, r1] = win.response, [c0, c1] = win.calibration;
    const [w0, w1] = timedWindow(win.response, p);
    const col = () => new Float64Array(N).fill(nan);
    const c = {}; for (const k of ["baseline_mean", "baseline_dev_pop", "response_mean_abs", "response_mean_diff", "response_max_abs",
      "response_max_diff", "response_max_diff_pop", "response_fraction", "rise_time_frames", "rapid_response_ratio",
      "calibration_mean", "calibration_diff"]) c[k] = col();
    let ps = 0, pn = 0;
    for (let i = 0; i < N; i++) { const b = colMean(K, N, i, b0, b1); c.baseline_mean[i] = b; if (!Number.isNaN(b)) { ps += b; pn++; } }
    const pop = pn ? ps / pn : nan;
    const frac = p.rise_time_fraction, half = Math.floor((r1 - r0) / 2);
    for (let i = 0; i < N; i++) {
      const base = c.baseline_mean[i];
      c.baseline_dev_pop[i] = base - pop;
      if (r1 > r0) {
        const abs = colMean(K, N, i, w0, w1), mx = colMax(K, N, i, r0, r1);
        c.response_mean_abs[i] = abs; c.response_mean_diff[i] = abs - base;
        c.response_max_abs[i] = mx; c.response_max_diff[i] = mx - base; c.response_max_diff_pop[i] = mx - pop;
        c.response_fraction[i] = (abs - base) / (mx - base);
        const thr = frac * (mx - base); let rise = nan;
        for (let t = r0; t < r1; t++) { const v = K[t * N + i]; const d = Number.isNaN(v) ? -Infinity : v - base; if (d >= thr) { rise = t - r0 + 1; break; } }
        c.rise_time_frames[i] = rise;
        if (half) c.rapid_response_ratio[i] = (colMean(K, N, i, r0 + half, r1) - base) / (colMean(K, N, i, r0, r0 + half) - base);
      }
      if (c1 > c0) { const cm = colMean(K, N, i, c0, c1); c.calibration_mean[i] = cm; c.calibration_diff[i] = cm - base; }
    }
    if (additional) {
      c.additional_intensity = col();
      for (let i = 0; i < N; i++) c.additional_intensity[i] = p.additional_channel_metric === "first" ? additional[i] : colMean(additional, N, i, 0, T);
    }
    return { cols: c, population_baseline: pop, windows: win, timed_window: [w0, w1] };
  }

  function evaluate(crit, v) {
    if (Number.isNaN(v)) return false;
    if (crit.op === "<") return v < crit.value;
    if (crit.op === ">") return v > crit.value;
    if (crit.op === "between") return v > crit.value && v < crit.value2;
    return false;
  }

  // Validity gates and criteria -> {valid, hit, pass: {metric: Uint8Array}}
  function hits(cols, N, p, hasCalibration) {
    const valid = new Uint8Array(N), hit = new Uint8Array(N), pass = {};
    const gate = p.baseline_calibration_diff, dev = p.max_baseline_deviation;
    for (let i = 0; i < N; i++) {
      let ok = !Number.isNaN(cols.baseline_mean[i]);
      if (gate && hasCalibration) { const d = cols.calibration_diff[i]; ok = ok && d >= gate[0] && d <= gate[1]; }
      if (dev !== null && dev !== undefined) ok = ok && Math.abs(cols.baseline_dev_pop[i]) <= dev;
      valid[i] = ok ? 1 : 0;
    }
    // AND criteria must all pass; of the OR criteria at least one must pass (criterion.logic, default p.logic)
    const crits = (p.criteria || []).map((c, k) => [c, k]).filter(([c]) => c.metric in cols);
    const isAnd = (c) => String(c.logic || p.logic).toUpperCase() === "AND";
    crits.forEach(([c, k]) => { const a = new Uint8Array(N); for (let i = 0; i < N; i++) a[i] = evaluate(c, cols[c.metric][i]) ? 1 : 0; pass[k] = a; });
    if (crits.length) {
      const ands = crits.filter(([c]) => isAnd(c)).map(([, k]) => pass[k]), ors = crits.filter(([c]) => !isAnd(c)).map(([, k]) => pass[k]);
      for (let i = 0; i < N; i++) {
        let r = ands.every(a => a[i] === 1);
        if (ors.length) r = r && ors.some(a => a[i] === 1);
        hit[i] = valid[i] && r ? 1 : 0;
      }
    }
    return { valid, hit, pass };
  }

  // Cell order on mean response (whole trace if there is no response window); NaN first, stable.
  function order(K, T, N, win) {
    const [a, b] = win.response[1] > win.response[0] ? win.response : [0, T];
    const v = new Float64Array(N); for (let i = 0; i < N; i++) { const m = colMean(K, N, i, a, b); v[i] = Number.isNaN(m) ? -Infinity : m; }
    return Array.from({ length: N }, (_, i) => i).sort((x, y) => v[x] - v[y] || x - y);
  }

  // skimage.filters.threshold_otsu (256 bins over the data range), on log10 of positive values
  function otsuLog10(values) {
    const x = []; for (const v of values) if (Number.isFinite(v) && v > 0) x.push(Math.log10(v));
    if (x.length < 2) return nan;
    let lo = Infinity, hi = -Infinity; for (const v of x) { if (v < lo) lo = v; if (v > hi) hi = v; }
    if (lo === hi) return Math.pow(10, lo);
    const nb = 256, h = new Float64Array(nb), w = (hi - lo) / nb;
    for (const v of x) { let b = Math.floor((v - lo) / w); if (b >= nb) b = nb - 1; h[b]++; }
    const ctr = Array.from({ length: nb }, (_, b) => lo + (b + 0.5) * w);
    const w1 = new Float64Array(nb), m1 = new Float64Array(nb), w2 = new Float64Array(nb), m2 = new Float64Array(nb);
    let cw = 0, cm = 0; for (let b = 0; b < nb; b++) { cw += h[b]; cm += h[b] * ctr[b]; w1[b] = cw; m1[b] = cm / cw; }
    cw = 0; cm = 0; for (let b = nb - 1; b >= 0; b--) { cw += h[b]; cm += h[b] * ctr[b]; w2[b] = cw; m2[b] = cm / cw; }
    let best = -1, idx = 0;
    for (let b = 0; b < nb - 1; b++) { const v = w1[b] * w2[b + 1] * (m1[b] - m2[b + 1]) ** 2; if (v > best) { best = v; idx = b; } }
    return Math.pow(10, ctr[idx]);
  }

  // ---- route through the hits, as fast_hippos.stage.optimize_path: nearest neighbour from the point closest to
  // `start` (default: stage origin), then 2-opt and Or-opt moves between nearby points, within maxMs.
  // A generator that yields now and then, so that the dashboard can keep the page responsive (routeSteps is run at
  // once by optimizePath, e.g. in the tests).
  function* routeSteps(pts, maxMs = 5000, start = null, K = 25) {
    const n = pts.length;
    if (n < 3) return pts.map((_, i) => i);
    const X = Float64Array.from(pts, p => p[0]), Y = Float64Array.from(pts, p => p[1]);
    const d = (a, b) => Math.sqrt((X[a] - X[b]) ** 2 + (Y[a] - Y[b]) ** 2);
    const deadline = Date.now() + maxMs, late = () => Date.now() > deadline;
    // nearest neighbour
    const [sx, sy] = start || [0, 0], used = new Uint8Array(n);
    let order = [], cur = 0, bc = Infinity;
    for (let i = 0; i < n; i++) { const v = (X[i] - sx) ** 2 + (Y[i] - sy) ** 2; if (v < bc) { bc = v; cur = i; } }
    for (let s = 0; s < n; s++) {
      order.push(cur); used[cur] = 1; if (s === n - 1) break;
      let best = -1, bd = Infinity;
      for (let j = 0; j < n; j++) if (!used[j]) { const v = (X[j] - X[cur]) ** 2 + (Y[j] - Y[cur]) ** 2; if (v < bd) { bd = v; best = j; } }
      cur = best; if (s % 500 === 499) yield;
    }
    // the K nearest other points of every point, nearest first
    const k = Math.min(K, n - 1), nbr = new Array(n);
    for (let i = 0; i < n; i++) {
      const bi = [], bv = [];
      for (let j = 0; j < n; j++) {
        if (j === i) continue;
        const v = (X[j] - X[i]) ** 2 + (Y[j] - Y[i]) ** 2;
        if (bi.length === k && v >= bv[k - 1]) continue;
        let p = bi.length; while (p > 0 && bv[p - 1] > v) p--;
        bi.splice(p, 0, j); bv.splice(p, 0, v); if (bi.length > k) { bi.pop(); bv.pop(); }
      }
      nbr[i] = bi; if (i % 500 === 499) yield;
    }
    let pos = new Int32Array(n);
    const reindex = () => { for (let i = 0; i < n; i++) pos[order[i]] = i; };
    const length = () => { let L = 0; for (let i = 1; i < n; i++) L += d(order[i - 1], order[i]); return L; };

    function* twoOpt() {  // as fast_hippos.stage.two_opt (first point fixed)
      reindex();
      const queued = new Uint8Array(n).fill(1), todo = order.slice(); let head = 0, steps = 0;
      const push = (p) => { if (!queued[p]) { queued[p] = 1; todo.push(p); } };
      const reverse = (i, j) => { for (let a = i, b = j; a < b; a++, b--) { const t = order[a]; order[a] = order[b]; order[b] = t; } for (let t = i; t <= j; t++) pos[order[t]] = t; };
      const improve = (a) => {
        const i = pos[a];
        for (const side of [1, -1]) {
          if (i + side < 0 || i + side >= n) continue;
          const b = order[i + side], dab = d(a, b);
          for (const c of nbr[a]) {
            const dac = d(a, c); if (dac >= dab) break;
            const j = pos[c]; let e = null, gain, lo, hi;
            if (side === 1) {
              if (j > i + 1) { e = j + 1 < n ? order[j + 1] : null; gain = dab - dac + (e !== null ? d(c, e) - d(b, e) : 0); lo = i + 1; hi = j; }
              else if (j < i) { e = order[j + 1]; gain = dab - dac + d(c, e) - d(e, b); lo = j + 1; hi = i; }
              else continue;
            } else {
              if (j < i - 1) { e = j > 0 ? order[j - 1] : null; if (e === null) continue; gain = dab - dac + d(e, c) - d(e, b); lo = j; hi = i - 1; }
              else if (j > i) { e = order[j - 1]; gain = dab - dac + d(e, c) - d(b, e); lo = i; hi = j - 1; }
              else continue;
            }
            if (lo === 0) continue;
            if (gain > 1e-12) { reverse(lo, hi); push(a); push(b); push(c); if (e !== null) push(e); return true; }
          }
        }
        return false;
      };
      for (;;) {
        while (head < todo.length) {
          if (late()) return;
          const a = todo[head++]; queued[a] = 0;
          if (improve(a) && !queued[a]) { queued[a] = 1; todo.push(a); }
          if (++steps % 2000 === 0) yield;
        }
        let swept = false;
        for (const a of order.slice()) { if (late()) return; if (improve(a)) swept = true; if (++steps % 2000 === 0) yield; }
        if (!swept) return;
      }
    }
    function* orOpt() {  // as fast_hippos.stage.or_opt
      reindex(); let steps = 0;
      for (let improved = true; improved && !late();) {
        improved = false;
        for (let s = 1; s < n; s++) {
          if (late()) break;
          for (const len of [1, 2, 3]) {
            const t = s + len - 1; if (t >= n) break;
            const seg = order.slice(s, t + 1), p = order[s - 1], q = t + 1 < n ? order[t + 1] : null;
            const removed = d(p, seg[0]) + (q !== null ? d(seg[len - 1], q) - d(p, q) : 0);
            let best = 1e-12, at = null;
            for (const end of [seg[0], seg[len - 1]]) for (const u of nbr[end]) {
              const iu = pos[u]; if (iu >= s - 1 && iu <= t) continue;
              const v = iu + 1 < n ? order[iu + 1] : null;
              if (v !== null && pos[v] >= s && pos[v] <= t) continue;
              for (const [first, last] of [[seg[0], seg[len - 1]], [seg[len - 1], seg[0]]]) {
                const added = d(u, first) + (v !== null ? d(last, v) - d(u, v) : 0);
                if (removed - added > best) { best = removed - added; at = [u, first !== seg[0]]; }
              }
            }
            if (at) {
              const rest = order.slice(0, s).concat(order.slice(t + 1)), kk = rest.indexOf(at[0]) + 1;
              order = rest.slice(0, kk).concat(at[1] ? seg.slice().reverse() : seg, rest.slice(kk)); reindex();
              improved = true; break;
            }
          }
          if (++steps % 200 === 0) yield;
        }
      }
    }
    yield* twoOpt();
    while (!late()) {
      const before = length();
      yield* orOpt(); yield* twoOpt();
      if (length() > before - 1e-12 * Math.max(1, before)) break;
    }
    return order;
  }
  function optimizePath(pts, maxMs = 5000, start = null) {
    const g = routeSteps(pts, maxMs, start); let r;
    while (!(r = g.next()).done);
    return r.value;
  }

  return { windows, timedWindow, smooth, metrics, hits, order, otsuLog10, routeSteps, optimizePath };
})();
if (typeof module !== "undefined") module.exports = FHScreen;
