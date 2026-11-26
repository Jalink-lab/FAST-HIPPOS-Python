// ---------------------------------------------------------------- curve fits of the scatter plot (weighted least squares)
// Pure functions (no page state), so that tests can run them. fitCurve(model, xs, ys, ws) fits one of FIT_MODELS:
// a start from a grid search on the non-linear parameters (the linear ones solved exactly for each grid point), then
// Levenberg-Marquardt. Weights are frequency weights (normalized to a mean of 1, so the standard errors are those of
// the points given). Returns { p, se, r2, n, sse } or { error }.
const FIT_MODELS = {
  linear: {
    label: "linear", eq: "y = a + b·x", names: ["a", "b"],
    f: (x, p) => p[0] + p[1] * x,
    J: (x) => [1, x],
    start: (X, Y, W) => wls([X.map(() => 1), X], Y, W),
  },
  exponential: {
    label: "exponential", eq: "y = a·e^(b·x) + c", names: ["a", "b", "c"],
    f: (x, p) => p[0] * Math.exp(p[1] * x) + p[2],
    J: (x, p) => { const e = Math.exp(p[1] * x); return [e, p[0] * x * e, 1]; },
    start: (X, Y, W) => {  // for each rate b, a and c are linear
      const span = rangeOf(X), x0 = X.reduce((s, x) => s + x, 0) / X.length;
      let best = null;
      for (const sign of [-1, 1]) for (let i = 0; i <= 24; i++) {
        const b = sign * Math.pow(10, -1.5 + i * 0.125) / span;  // 0.03 to 30 e-folds over the data
        const E = X.map(x => Math.exp(b * (x - x0)));
        const ac = wls([E, X.map(() => 1)], Y, W); if (!ac) continue;
        const p = [ac[0] * Math.exp(-b * x0), b, ac[1]], s = sseOf(FIT_MODELS.exponential.f, p, X, Y, W);
        if (Number.isFinite(s) && (!best || s < best.s)) best = { p, s };
      }
      return best && best.p;
    },
  },
  logarithmic: {
    label: "logarithmic", eq: "y = a + b·ln(x)", names: ["a", "b"], positiveX: true,
    f: (x, p) => p[0] + p[1] * Math.log(x),
    J: (x) => [1, Math.log(x)],
    start: (X, Y, W) => wls([X.map(() => 1), X.map(Math.log)], Y, W),
  },
  sigmoid: {
    label: "sigmoid", eq: "y = bottom + (top − bottom) / (1 + e^((x50 − x) / slope))", names: ["bottom", "top", "x50", "slope"],
    f: (x, p) => p[0] + (p[1] - p[0]) / (1 + Math.exp((p[2] - x) / p[3])),
    J: (x, p) => {
      const L = 1 / (1 + Math.exp((p[2] - x) / p[3])), d = (p[1] - p[0]) * L * (1 - L);
      return [1 - L, L, -d / p[3], d * (p[2] - x) / (p[3] * p[3])];
    },
    start: (X, Y, W) => {  // for each midpoint and slope, bottom and top are linear
      const span = rangeOf(X), sorted = [...X].sort((a, b) => a - b);
      let best = null;
      for (let q = 1; q <= 19; q++) {
        const x50 = sorted[Math.floor((sorted.length - 1) * q / 20)];
        for (const k of [0.01, 0.02, 0.05, 0.1, 0.2, 0.5]) {
          const s = k * span, L = X.map(x => 1 / (1 + Math.exp((x50 - x) / s)));
          const bt = wls([L.map(l => 1 - l), L], Y, W); if (!bt) continue;
          const p = [bt[0], bt[1], x50, s], e = sseOf(FIT_MODELS.sigmoid.f, p, X, Y, W);
          if (Number.isFinite(e) && (!best || e < best.e)) best = { p, e };
        }
      }
      return best && best.p;
    },
  },
};
function rangeOf(X) { let a = Infinity, b = -Infinity; for (const x of X) { if (x < a) a = x; if (x > b) b = x; } return b > a ? b - a : 1; }
function sseOf(f, p, X, Y, W) { let s = 0; for (let i = 0; i < X.length; i++) { const r = Y[i] - f(X[i], p); s += W[i] * r * r; } return s; }
// solve A x = b (small, dense; partial pivoting); null when singular
function solveLin(A, b) {
  const n = b.length, M = A.map((r, i) => [...r, b[i]]);
  for (let c = 0; c < n; c++) {
    let piv = c; for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[piv][c])) piv = r;
    if (!(Math.abs(M[piv][c]) > 1e-300)) return null;
    [M[c], M[piv]] = [M[piv], M[c]];
    for (let r = c + 1; r < n; r++) { const f = M[r][c] / M[c][c]; for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k]; }
  }
  const x = new Array(n);
  for (let r = n - 1; r >= 0; r--) { let s = M[r][n]; for (let k = r + 1; k < n; k++) s -= M[r][k] * x[k]; x[r] = s / M[r][r]; }
  return x.every(Number.isFinite) ? x : null;
}
// weighted linear least squares with the given columns
function wls(cols, Y, W) {
  const m = cols.length, A = Array.from({ length: m }, () => new Array(m).fill(0)), b = new Array(m).fill(0);
  for (let i = 0; i < Y.length; i++) for (let j = 0; j < m; j++) { b[j] += W[i] * cols[j][i] * Y[i]; for (let k = 0; k < m; k++) A[j][k] += W[i] * cols[j][i] * cols[k][i]; }
  return solveLin(A, b);
}
function normalEq(model, p, X, Y, W) {
  const m = p.length, A = Array.from({ length: m }, () => new Array(m).fill(0)), g = new Array(m).fill(0);
  for (let i = 0; i < X.length; i++) {
    const j = model.J(X[i], p), r = Y[i] - model.f(X[i], p);
    for (let a = 0; a < m; a++) { g[a] += W[i] * j[a] * r; for (let c = 0; c < m; c++) A[a][c] += W[i] * j[a] * j[c]; }
  }
  return { A, g };
}
function fitCurve(name, xs, ys, ws) {
  const model = FIT_MODELS[name]; if (!model) return { error: "unknown fit" };
  const X = [], Y = [], W0 = [];
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i], y = ys[i], w = ws ? ws[i] : 1;
    if (!Number.isFinite(x) || !Number.isFinite(y) || !(w > 0) || (model.positiveX && !(x > 0))) continue;
    X.push(x); Y.push(y); W0.push(w);
  }
  const n = X.length, m = model.names.length;
  if (n < m + 2) return { error: `too few cells (${n})`, n };
  if (!(rangeOf(X) > 0) || X.every(x => x === X[0])) return { error: "all x values are the same", n };
  const wMean = W0.reduce((s, w) => s + w, 0) / n, W = W0.map(w => w / wMean);
  let p = model.start(X, Y, W);
  if (!p) return { error: "no start values found", n };
  let sse = sseOf(model.f, p, X, Y, W), lambda = 1e-3;
  for (let it = 0; it < 200; it++) {
    const { A, g } = normalEq(model, p, X, Y, W);
    let improved = false;
    while (lambda < 1e12) {
      const Al = A.map((r, i) => r.map((v, j) => (i === j ? v * (1 + lambda) + 1e-300 : v)));
      const d = solveLin(Al, g);
      const q = d && p.map((v, i) => v + d[i]), s = q ? sseOf(model.f, q, X, Y, W) : NaN;
      if (Number.isFinite(s) && s <= sse) { const rel = (sse - s) / (sse || 1); p = q; sse = s; lambda = Math.max(lambda / 10, 1e-12); improved = rel > 1e-12; break; }
      lambda *= 10;
    }
    if (!improved) break;
  }
  if (!p.every(Number.isFinite) || !Number.isFinite(sse)) return { error: "the fit did not converge", n };
  // goodness and standard errors: s² (JᵀWJ)⁻¹
  const yMean = Y.reduce((s, y, i) => s + W[i] * y, 0) / n, sst = Y.reduce((s, y, i) => s + W[i] * (y - yMean) ** 2, 0);
  const { A } = normalEq(model, p, X, Y, W), s2 = sse / (n - m);
  const se = model.names.map((_, j) => { const e = new Array(m).fill(0); e[j] = 1; const c = solveLin(A, e); return c && c[j] >= 0 ? Math.sqrt(s2 * c[j]) : NaN; });
  return { p, se, r2: sst > 0 ? 1 - sse / sst : NaN, n, sse };
}
// numbers of a fit: 4 significant digits
function fitFmt(v) {
  if (!Number.isFinite(v)) return "–";
  const a = Math.abs(v); return a >= 1e5 || (a < 1e-3 && a > 0) ? v.toExponential(3) : String(+v.toPrecision(4));
}
