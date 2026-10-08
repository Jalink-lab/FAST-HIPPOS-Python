// ---------------------------------------------------------------- live screening panel
const METRIC_KEYS = Object.keys(D.screen.metrics).filter(k => k !== "additional_intensity" || KA);
const critText = (c) => `${c.metric} ${c.op === "between" ? "between" : c.op} ${c.value}` + (c.op === "between" ? ` and ${c.value2}` : "");
const screeningModified = () => JSON.stringify({ events: SCR.events, params: SCR.params, mode: SCR.mode }) !== SCR0 || SCR.mode === "selection";
let eventsTouched = false;
SCR.version = 0;

function hitSignature() { let s = ""; for (let i = 0; i < N; i++) if (HIT[i]) s += i + ","; return s; }
function recompute() {
  const p = SCR.params, ev = SCR.events;
  SCR.version++;
  KS = FHScreen.smooth(KR, T, N, p.smooth_traces);
  const m = FHScreen.metrics(KS, T, N, ev, p, KA);
  Object.assign(C, m.cols);
  const hasCal = m.windows.calibration[1] > m.windows.calibration[0];
  const h = FHScreen.hits(m.cols, N, p, hasCal);
  C.valid = Array.from(h.valid); SCR.pass = h.pass; SCR.hasCal = hasCal;
  if (SCR.mode === "selection") HIT = Array.from({ length: N }, (_, i) => SCR.manual.has(i));
  else if (D.screening.random && JSON.stringify({ events: SCR.events, params: SCR.params, mode: SCR.mode }) === SCR0) HIT = D.cells.hit.map(Boolean);
  else HIT = Array.from(h.hit, Boolean);
  C.hit = HIT.map(Number);
  if (KA && p.classify_additional_channel && Number.isFinite(p.classification_threshold))
    C.class_additional = Array.from(C.additional_intensity, v => v > p.classification_threshold ? 1 : 0);
  else delete C.class_additional;
  ORDER = FHScreen.order(KR, T, N, m.windows);
  C.response_rank = new Array(N); ORDER.forEach((c, r) => C.response_rank[c] = r);
  EV = { ...ev, baseline: m.windows.baseline, response: m.windows.response, calibration_window: m.windows.calibration, timed_window: m.timed_window };
  SCR.population_baseline = m.population_baseline;
  if (SCR.route) SCR.route.stale = SCR.route.sig !== hitSignature();
  $("tsrc").disabled = !(p.smooth_traces > 0); if (!(p.smooth_traces > 0)) { S.tsrc = "raw"; $("tsrc").value = "raw"; }
  updateChips(); updateScreenUI(); outlinesChanged();
  invalidate(...ON.hits, "tracesHov");
}
let recomputeTimer = null;
function scheduleRecompute(delay = 80) { clearTimeout(recomputeTimer); recomputeTimer = setTimeout(recompute, delay); }

// ---- histogram slider: distribution of a per-cell value with draggable threshold(s)
class HistSlider {
  // o.values(): array; o.mode(): 'gt'|'lt'|'between'|'abs'; o.get(): [a, b]; o.set(a, b); o.log: bool; o.passColor()
  constructor(canvas, o) {
    this.c = canvas; this.o = o; let handle = null;
    canvas.addEventListener("pointerdown", (e) => {
      canvas.setPointerCapture(e.pointerId); const v = this.valueAt(e); if (v === null) return;
      const [a, b] = this.o.get(), mode = this.o.mode();
      handle = mode === "between" && Math.abs(v - b) < Math.abs(v - a) ? 1 : 0; this.drag(v, handle);
    });
    canvas.addEventListener("pointermove", (e) => { if (handle === null) return; const v = this.valueAt(e); if (v !== null) this.drag(v, handle); });
    canvas.addEventListener("pointerup", () => { handle = null; });
  }
  valueAt(e) { const g = this.g; if (!g) return null; const r = this.c.getBoundingClientRect(); const f = (e.clientX - r.left) / r.width, u = g.lo + f * (g.hi - g.lo); return this.o.log ? Math.pow(10, u) : u; }
  drag(v, handle) {
    const [a, b] = this.o.get(), mode = this.o.mode(); v = +v.toPrecision(4);
    if (mode === "abs") v = Math.abs(v);
    handle === 1 ? this.o.set(a, Math.max(v, a)) : this.o.set(mode === "between" ? Math.min(v, b ?? v) : v, b);
  }
  draw() {
    const c = this.c, dpr = window.devicePixelRatio || 1, w = c.clientWidth || 200, h = c.clientHeight || 36;
    c.width = w * dpr; c.height = h * dpr; const x = c.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, w, h);
    const tr = (v) => this.o.log ? Math.log10(v) : v;
    let vals = Array.from(this.o.values()).filter(v => Number.isFinite(v) && (!this.o.log || v > 0)).map(tr).sort((p, q) => p - q);
    if (!vals.length) { this.g = null; x.fillStyle = css("--muted"); x.font = "11px system-ui"; x.fillText("no values", 6, h / 2 + 4); return; }
    const mode = this.o.mode(), [a, b] = this.o.get();
    let lo = vals[Math.floor(vals.length * 0.01)], hi = vals[Math.min(vals.length - 1, Math.floor(vals.length * 0.99))];
    const marks = mode === "abs" ? [-a, a] : mode === "between" ? [a, b] : [a];
    for (const t of marks) if (Number.isFinite(t) && (!this.o.log || t > 0)) { lo = Math.min(lo, tr(t)); hi = Math.max(hi, tr(t)); }
    if (hi <= lo) hi = lo + 1; const pad = (hi - lo) * 0.04; lo -= pad; hi += pad; this.g = { lo, hi };
    const nb = Math.max(20, Math.min(64, Math.floor(w / 5))), cnt = new Float64Array(nb);
    for (const v of vals) { const k = Math.floor((v - lo) / (hi - lo) * nb); if (k >= 0 && k < nb) cnt[k]++; }
    const mx = Math.max(...cnt) || 1, bw = w / nb, pc = this.o.passColor ? this.o.passColor() : css("--hit"), base = css("--muted");
    const passes = (u) => { const v = this.o.log ? Math.pow(10, u) : u; return mode === "lt" ? v < a : mode === "gt" ? v > a : mode === "between" ? v > a && v < b : Math.abs(v) <= a; };
    for (let k = 0; k < nb; k++) { const ok = passes(lo + (k + 0.5) / nb * (hi - lo)); x.fillStyle = ok ? pc : base; x.globalAlpha = ok ? 0.85 : 0.3; const bh = Math.sqrt(cnt[k] / mx) * (h - 3); x.fillRect(k * bw + 0.5, h - bh, Math.max(1, bw - 1), bh); }
    x.globalAlpha = 1; x.strokeStyle = css("--text"); x.lineWidth = 2;
    for (const t of marks) if (Number.isFinite(t) && (!this.o.log || t > 0)) { const px = (tr(t) - lo) / (hi - lo) * w; x.beginPath(); x.moveTo(px, 0); x.lineTo(px, h); x.stroke(); x.fillStyle = css("--text"); x.fillRect(px - 3, 0, 6, 5); }
  }
}

// ---- timeline: population median with windows; drag S and C
const TLP = new Plot([$("tl")], { l: 8, r: 8, t: 14, b: 16 });
let tlDrag = null;
function drawTimeline() {
  TLP.resize(); const k = KS, ids = []; for (let i = 0; i < N; i++) ids.push(i);
  const st = bandStats(ids, k);
  let lo = Infinity, hi = -Infinity; for (let t = 0; t < T; t++) { if (Number.isFinite(st[1][t])) lo = Math.min(lo, st[1][t]); if (Number.isFinite(st[3][t])) hi = Math.max(hi, st[3][t]); }
  if (!Number.isFinite(lo)) { lo = 0; hi = 1; } const pad = (hi - lo) * 0.15 || 0.1;
  TLP.range(-0.5, T - 0.5, lo - pad, hi + pad);
  const x = TLP.clear(0), ev = EV, X = (f) => TLP.X(f);
  const shade = (w, col, label) => { if (w[1] > w[0]) { x.fillStyle = col; x.fillRect(X(w[0] - 0.5), TLP.m.t, X(w[1] - 0.5) - X(w[0] - 0.5), TLP.ph); if (label) { x.fillStyle = css("--muted"); x.font = "10px system-ui"; x.fillText(label, X(w[0] - 0.5) + 3, TLP.m.t - 3); } } };
  shade(ev.baseline, css("--base-win"), ev.baseline_only ? "baseline (all frames)" : "baseline");
  shade(ev.response, withAlpha(css("--resp-solid"), 0.10), "response");
  shade(ev.timed_window, withAlpha(css("--resp-solid"), 0.22), "");
  shade(ev.calibration_window, css("--cal-win"), "calibration");
  x.fillStyle = withAlpha(css("--accent"), 0.2); x.beginPath(); for (let t = 0; t < T; t++) x.lineTo(X(t), TLP.Y(st[3][t])); for (let t = T - 1; t >= 0; t--) x.lineTo(X(t), TLP.Y(st[1][t])); x.fill();
  x.strokeStyle = css("--accent"); x.lineWidth = 2; x.beginPath(); for (let t = 0; t < T; t++) x.lineTo(X(t), TLP.Y(st[2][t])); x.stroke();
  const handle = (f, name, col) => { const px = X(f - 0.5); x.strokeStyle = col; x.lineWidth = 2; x.beginPath(); x.moveTo(px, TLP.m.t); x.lineTo(px, TLP.m.t + TLP.ph); x.stroke(); x.fillStyle = col; x.beginPath(); x.roundRect(px - 9, TLP.m.t + TLP.ph - 2, 18, 16, 4); x.fill(); x.fillStyle = "#fff"; x.font = "bold 11px system-ui"; x.textAlign = "center"; x.fillText(name, px, TLP.m.t + TLP.ph + 10); x.textAlign = "start"; };
  if (!SCR.events.baseline_only) { if (SCR.events.stimulation !== null) handle(SCR.events.stimulation, "S", css("--resp-solid")); if (SCR.events.calibration !== null) handle(SCR.events.calibration, "C", css("--cal-solid")); }
  const fx = X(S.frame); x.strokeStyle = withAlpha(css("--text"), 0.5); x.lineWidth = 1; x.setLineDash([2, 3]); x.beginPath(); x.moveTo(fx, TLP.m.t); x.lineTo(fx, TLP.m.t + TLP.ph); x.stroke(); x.setLineDash([]);
}
function initTimeline() {
  const c = $("tl");
  const frameAt = (e) => { const [px] = localXY(e, c); return Math.round(TLP.iX(px) + 0.5); };
  c.addEventListener("pointerdown", (e) => {
    const f = frameAt(e), ev = SCR.events; c.setPointerCapture(e.pointerId);
    const ds = ev.stimulation !== null ? Math.abs(f - ev.stimulation) : Infinity, dc = ev.calibration !== null ? Math.abs(f - ev.calibration) : Infinity;
    tlDrag = Math.min(ds, dc) <= 2 ? (ds <= dc ? "stimulation" : "calibration") : null;
    if (!tlDrag) setFrame(f);
  });
  c.addEventListener("pointermove", (e) => {
    const f = Math.max(1, Math.min(T - 1, frameAt(e))), ev = SCR.events;
    if (!tlDrag) { const near = [ev.stimulation, ev.calibration].some(v => v !== null && Math.abs(f - v) <= 2); c.style.cursor = near ? "ew-resize" : "pointer"; return; }
    if (ev[tlDrag] === f) return;
    if (tlDrag === "stimulation" && ev.calibration !== null && f >= ev.calibration) return;
    if (tlDrag === "calibration" && ev.stimulation !== null && f <= ev.stimulation) return;
    ev[tlDrag] = f; ev.detected = false; eventsTouched = true; fillEventInputs(); scheduleRecompute(30);
  });
  c.addEventListener("pointerup", () => { tlDrag = null; });
}

// ---- panel
const sliders = [];
function seg(el, value, onChange) {  // segmented buttons: <div class="seg"><button data-v=...>
  const set = (v) => el.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === String(v)));
  set(value); el.querySelectorAll("button").forEach(b => b.onclick = () => { set(b.dataset.v); onChange(b.dataset.v); });
  return set;
}
function numOrNull(el) { const v = parseFloat(el.value); return Number.isFinite(v) ? v : null; }
function fillEventInputs() { const e = SCR.events; $("evs").value = e.stimulation ?? ""; $("evc").value = e.calibration ?? ""; $("evm").value = e.margin; $("evb").checked = e.baseline_only; }
let setWinMode = null, setAnchor = null, setSrc = null;
function fillParams() {
  const p = SCR.params;
  fillEventInputs();
  setWinMode(p.response_window < 0 ? "full" : "n"); $("rw").value = p.response_window < 0 ? 3 : p.response_window; $("rw").disabled = p.response_window < 0;
  setAnchor(p.response_window_anchor); $("rm").value = p.response_window_margin;
  $("sm").value = p.smooth_traces; $("smv").textContent = p.smooth_traces ? `r = ${p.smooth_traces}` : "off";
  $("rf").value = p.rise_time_fraction; $("rfv").textContent = `${Math.round(p.rise_time_fraction * 100)} %`;
  $("g1").checked = !!p.baseline_calibration_diff; [$("g1a").value, $("g1b").value] = p.baseline_calibration_diff || [0.5, 1];
  $("g2").checked = p.max_baseline_deviation !== null && p.max_baseline_deviation !== undefined; $("g2v").value = p.max_baseline_deviation ?? 0.2;
  $("am").value = p.additional_channel_metric; $("cls").checked = p.classify_additional_channel; $("clt").value = p.classification_threshold ?? "";
  const sb = $("sortby"); if (!sb.options.length) [["", "(cell order)"], ...METRIC_KEYS.map(k => [k, k])].forEach(([v, l]) => sb.add(new Option(l, v)));
  sb.value = p.sort_by || ""; $("sortdir").value = p.sort_descending ? "1" : "0"; $("chunk").value = p.max_hits_per_rgn; $("optpath").checked = p.optimize_path;
  setSrc(SCR.mode);
  renderCriteria();
}
function initScreening() {
  const p = SCR.params, e = SCR.events, body = $("scrbody");
  if (!(D.screening.enabled || p.criteria.length)) { body.classList.add("closed"); $("scrtoggle").textContent = "▸"; }
  $("scrtoggle").onclick = () => { body.classList.toggle("closed"); $("scrtoggle").textContent = body.classList.contains("closed") ? "▸" : "▾"; updateScreenUI(); };
  setWinMode = seg($("winmode"), "full", (v) => { $("rw").disabled = v === "full"; p.response_window = v === "full" ? -1 : Math.max(1, numOrNull($("rw")) ?? 3); scheduleRecompute(); });
  setAnchor = seg($("anchor"), p.response_window_anchor, (v) => { p.response_window_anchor = v; scheduleRecompute(); });
  setSrc = seg($("hitsrc"), "criteria", (v) => { SCR.mode = v; if (v === "selection" && !SCR.manual.size) SCR.manual = new Set(S.sel); renderCriteria(); recompute(); });
  const readEvents = () => { e.stimulation = numOrNull($("evs")); e.calibration = numOrNull($("evc")); e.margin = numOrNull($("evm")) ?? 1; e.baseline_only = $("evb").checked; e.detected = false; eventsTouched = true; scheduleRecompute(); };
  ["evs", "evc", "evm"].forEach(id => $(id).oninput = readEvents); $("evb").onchange = readEvents;
  $("evauto").onclick = () => { Object.assign(e, structuredClone(D.screen.events)); eventsTouched = false; fillEventInputs(); recompute(); };
  $("rw").oninput = () => { if (p.response_window >= 0) { p.response_window = Math.max(1, numOrNull($("rw")) ?? 3); scheduleRecompute(); } };
  $("rm").oninput = () => { p.response_window_margin = Math.max(0, numOrNull($("rm")) ?? 0); scheduleRecompute(); };
  $("sm").oninput = () => { p.smooth_traces = +$("sm").value; $("smv").textContent = p.smooth_traces ? `r = ${p.smooth_traces}` : "off"; if (p.smooth_traces > 0) { S.tsrc = "smoothed"; $("tsrc").value = "smoothed"; } scheduleRecompute(); };
  $("rf").oninput = () => { p.rise_time_fraction = +$("rf").value; $("rfv").textContent = `${Math.round(p.rise_time_fraction * 100)} %`; scheduleRecompute(); };
  const readGates = () => {
    p.baseline_calibration_diff = $("g1").checked ? [numOrNull($("g1a")) ?? 0.5, numOrNull($("g1b")) ?? 1] : null;
    p.max_baseline_deviation = $("g2").checked ? Math.abs(numOrNull($("g2v")) ?? 0.2) : null;
    p.additional_channel_metric = $("am").value; p.classify_additional_channel = $("cls").checked; p.classification_threshold = numOrNull($("clt"));
    scheduleRecompute();
  };
  ["g1a", "g1b", "g2v", "clt"].forEach(id => $(id).oninput = readGates); ["g1", "g2", "am", "cls"].forEach(id => $(id).onchange = readGates);
  $("clotsu").onclick = () => { const t = FHScreen.otsuLog10(C.additional_intensity); if (Number.isFinite(t)) { $("clt").value = +t.toPrecision(4); $("cls").checked = true; readGates(); } };
  if (!KA) $("gate3").style.display = "none";
  sliders.push(new HistSlider($("g1h"), { values: () => C.calibration_diff, mode: () => "between", get: () => p.baseline_calibration_diff || [+$("g1a").value, +$("g1b").value],
    set: (a, b) => { $("g1a").value = a; $("g1b").value = b; $("g1").checked = true; readGates(); }, passColor: () => css("--ok") }));
  sliders.push(new HistSlider($("g2h"), { values: () => C.baseline_dev_pop, mode: () => "abs", get: () => [p.max_baseline_deviation ?? +$("g2v").value],
    set: (a) => { $("g2v").value = a; $("g2").checked = true; readGates(); }, passColor: () => css("--ok") }));
  if (KA) sliders.push(new HistSlider($("clh"), { values: () => C.additional_intensity, mode: () => "gt", log: true, get: () => [p.classification_threshold ?? NaN],
    set: (a) => { $("clt").value = a; $("cls").checked = true; readGates(); }, passColor: () => css("--accent") }));
  $("addcrit").onclick = () => {
    const metric = METRIC_KEYS.includes("response_max_diff") ? "response_max_diff" : METRIC_KEYS[0], s = finiteSorted(metric);
    p.criteria.push({ metric, op: ">", value: s.length ? +s[Math.floor(s.length / 2)].toPrecision(3) : 0, value2: null, logic: p.criteria.length ? "AND" : "OR" });
    renderCriteria(); recompute();
  };
  $("usesel").onclick = () => { SCR.manual = new Set(S.sel); SCR.mode = "selection"; setSrc("selection"); renderCriteria(); recompute(); };
  $("addsel").onclick = () => { S.sel.forEach(i => SCR.manual.add(i)); recompute(); };
  $("clearmanual").onclick = () => { SCR.manual.clear(); recompute(); };
  $("scrreset").onclick = () => { const o = JSON.parse(SCR0); Object.assign(e, o.events); Object.assign(p, o.params); SCR.mode = o.mode; eventsTouched = false; fillParams(); recompute(); };
  const readOut = () => { p.sort_by = $("sortby").value || null; p.sort_descending = $("sortdir").value === "1"; p.max_hits_per_rgn = Math.max(1, numOrNull($("chunk")) ?? 1000); p.optimize_path = $("optpath").checked; if (SCR.route) SCR.route.stale = true; updateScreenUI(); invalidate("viewerHov"); };
  ["sortby", "sortdir", "optpath"].forEach(id => $(id).onchange = readOut); $("chunk").oninput = readOut;
  $("route").onclick = () => computeRoute(); $("vroute2").checked = S.showRoute;
  $("vroute2").onchange = () => { S.showRoute = $("vroute2").checked; $("vroute").checked = S.showRoute; invalidate("viewerHov"); };
  $("scrtoml").onclick = exportTOML; $("hitstsv").onclick = exportHitsTSV; $("hitsrgn").onclick = exportHitsRGN; $("hitsrgn").disabled = !HAS_ABS;
  initTimeline(); fillParams();
  new ResizeObserver(() => updateScreenUI()).observe(body);
}
function finiteSorted(metric) { const a = []; for (const v of C[metric] || []) if (v !== null && Number.isFinite(v)) a.push(v); return a.sort((x, y) => x - y); }

function renderCriteria() {
  const box = $("crits"), p = SCR.params; box.innerHTML = "";
  box.classList.toggle("disabled", SCR.mode === "selection"); $("manualbox").style.display = SCR.mode === "selection" ? "" : "none";
  p.criteria.forEach((c, k) => {
    const row = document.createElement("div"); row.className = "crit";
    row.innerHTML = `<button class="pill ${c.logic.toLowerCase()}" title="AND: required · OR: at least one of the OR criteria">${c.logic}</button>
      <select class="m"></select>
      <div class="seg op"><button data-v="&lt;" title="lower than">&lt;</button><button data-v="&gt;" title="higher than">&gt;</button><button data-v="between" title="between">↔</button></div>
      <span class="vals"><input class="v" type="number" step="any"><input class="v2" type="number" step="any"></span>
      <canvas class="hs" title="drag to set the threshold"></canvas><span class="n"></span><button class="x" title="remove">✕</button>`;
    const ms = row.querySelector(".m"); METRIC_KEYS.forEach(m => ms.add(new Option(m, m))); ms.value = c.metric; ms.title = D.screen.metrics[c.metric] || "";
    const v1 = row.querySelector(".v"), v2 = row.querySelector(".v2");
    const showV2 = () => { v2.style.display = c.op === "between" ? "" : "none"; };
    v1.value = c.value; v2.value = c.value2 ?? ""; showV2();
    const changed = () => { c.value = numOrNull(v1) ?? 0; c.value2 = c.op === "between" ? (numOrNull(v2) ?? c.value) : null; showV2(); scheduleRecompute(40); };
    row.querySelector(".pill").onclick = (ev) => { c.logic = c.logic === "AND" ? "OR" : "AND"; ev.target.textContent = c.logic; ev.target.className = `pill ${c.logic.toLowerCase()}`; recompute(); };
    seg(row.querySelector(".op"), c.op, (v) => { c.op = v; if (v === "between" && c.value2 === null) { const s = finiteSorted(c.metric); v2.value = s.length ? +s[Math.floor(s.length * 0.9)].toPrecision(3) : c.value; } changed(); });
    ms.onchange = () => { c.metric = ms.value; ms.title = D.screen.metrics[c.metric] || ""; const s = finiteSorted(c.metric); if (s.length) { v1.value = +s[Math.floor(s.length / 2)].toPrecision(3); v2.value = +s[Math.floor(s.length * 0.9)].toPrecision(3); } changed(); };
    v1.oninput = changed; v2.oninput = changed;
    row.querySelector(".x").onclick = () => { p.criteria.splice(k, 1); renderCriteria(); recompute(); };
    row._slider = new HistSlider(row.querySelector(".hs"), { values: () => C[c.metric] || [], mode: () => c.op === ">" ? "gt" : c.op === "<" ? "lt" : "between", get: () => [c.value, c.value2],
      set: (a, b) => { v1.value = a; if (b !== undefined && b !== null) v2.value = b; changed(); } });
    row._k = k; box.appendChild(row);
  });
  updateScreenUI();
}
function updateScreenUI() {
  const nh = nHits(), nv = C.valid.reduce((s, v) => s + v, 0), p = SCR.params;
  // funnel: cells -> pass gates -> hits
  const bar = (n, cls, label) => `<span class="fbar ${cls}" style="width:${Math.max(2, 100 * n / Math.max(1, N))}%"></span><span class="flab">${label}</span>`;
  $("funnel").innerHTML = `<span class="frow">${bar(N, "f0", `${N} cells`)}</span><span class="frow">${bar(nv, "f1", `${nv} valid`)}</span><span class="frow">${bar(nh, "f2", `<b>${nh}</b> hits`)}</span>`;
  $("scrmod").textContent = screeningModified() ? "changed — not yet in the run output" : "";
  $("g1n").textContent = p.baseline_calibration_diff && SCR.hasCal ? `${countFail(i => !(C.calibration_diff[i] >= p.baseline_calibration_diff[0] && C.calibration_diff[i] <= p.baseline_calibration_diff[1]))} fail` : (p.baseline_calibration_diff ? "no calibration" : "off");
  $("g2n").textContent = p.max_baseline_deviation !== null && p.max_baseline_deviation !== undefined ? `${countFail(i => !(Math.abs(C.baseline_dev_pop[i]) <= p.max_baseline_deviation))} fail` : "off";
  if (KA) $("cln").textContent = C.class_additional ? `${C.class_additional.reduce((s, v) => s + v, 0)} positive` : "off";
  $("mancount").textContent = `${SCR.manual.size} cells`; $("usesel").textContent = `Use selection (${S.sel.size})`;
  [...$("crits").children].forEach(row => { const pass = SCR.pass[row._k]; row.querySelector(".n").textContent = pass ? `${pass.reduce((s, v) => s + v, 0)} pass` : "—"; });
  const r = SCR.route;
  $("routeinfo").textContent = SCR.routeBusy ? "computing…" : r ? `${r.chunks.length} chunk${r.chunks.length > 1 ? "s" : ""} · ${r.n} positions · ${(r.length * 1e3).toFixed(1)} ${r.unit}` + (r.stale ? " · outdated" : "") : (nh ? "not computed" : "no hits");
  if ($("scrbody").classList.contains("closed")) return;
  drawTimeline(); sliders.forEach(s => s.draw()); [...$("crits").children].forEach(row => row._slider.draw());
}
function countFail(fn) { let n = 0; for (let i = 0; i < N; i++) if (fn(i)) n++; return n; }
layer("screenSel", () => { $("usesel").textContent = `Use selection (${S.sel.size})`; });

// ---- route (only when asked: it is the last step, after the hits are final)
function sortedHits() {
  const p = SCR.params, ids = HIT.map((h, i) => h ? i : -1).filter(i => i >= 0);
  if (p.sort_by && p.sort_by in C) { const k = p.sort_by, dir = p.sort_descending ? -1 : 1; ids.sort((a, b) => { const va = C[k][a], vb = C[k][b]; const na = va === null || Number.isNaN(va), nb = vb === null || Number.isNaN(vb); if (na || nb) return na - nb; return (va - vb) * dir; }); }
  return ids;
}
async function optimizeAsync(pts, maxMs) {
  const n = pts.length; if (n < 3) return pts.map((_, i) => i);
  const d = (a, b) => Math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1]);
  const used = new Uint8Array(n), order = [];
  let cur = 0; for (let i = 1; i < n; i++) if (pts[i][0] ** 2 + pts[i][1] ** 2 < pts[cur][0] ** 2 + pts[cur][1] ** 2) cur = i;
  for (let k = 0; k < n; k++) { order.push(cur); used[cur] = 1; let best = -1, bd = Infinity; for (let j = 0; j < n; j++) if (!used[j]) { const v = d(cur, j); if (v < bd) { bd = v; best = j; } } cur = best; }
  const t0 = performance.now(); let slice = performance.now();
  for (let improved = true; improved && performance.now() - t0 < maxMs;) {
    improved = false;
    for (let i = 0; i < n - 2; i++) {
      for (let j = i + 2; j < n - 1; j++) {
        const gain = d(order[i], order[i + 1]) + d(order[j], order[j + 1]) - d(order[i], order[j]) - d(order[i + 1], order[j + 1]);
        if (gain > 1e-12) { const seg = order.slice(i + 1, j + 1).reverse(); order.splice(i + 1, seg.length, ...seg); improved = true; }
      }
      if (performance.now() - slice > 40) { await new Promise(r => setTimeout(r)); slice = performance.now(); }
    }
  }
  return order;
}
async function computeRoute() {
  if (SCR.routeBusy) return SCR.route;
  const ids = sortedHits(); if (!ids.length) { SCR.route = null; updateScreenUI(); return null; }
  SCR.routeBusy = true; updateScreenUI();
  const p = SCR.params, size = p.max_hits_per_rgn || ids.length, chunks = [];
  const useAbs = HAS_ABS && ids.every(i => C.abs_x_m[i] !== null);
  const pt = (i) => useAbs ? [C.abs_x_m[i], C.abs_y_m[i]] : [POSX[i], POSY[i]];
  let length = 0;
  for (let a = 0; a < ids.length; a += size) {
    let chunk = ids.slice(a, a + size);
    if (p.optimize_path && chunk.length > 2) { const o = await optimizeAsync(chunk.map(pt), 5000); chunk = o.map(k => chunk[k]); }
    for (let j = 1; j < chunk.length; j++) { const [x0, y0] = pt(chunk[j - 1]), [x1, y1] = pt(chunk[j]); length += Math.hypot(x1 - x0, y1 - y0); }
    chunks.push(chunk);
  }
  SCR.route = { chunks, sig: hitSignature(), n: ids.length, length: useAbs ? length : length * D.pixel_size * 1e-6, unit: "mm", stale: false };
  SCR.routeBusy = false; S.showRoute = true; $("vroute").checked = $("vroute2").checked = true;
  updateScreenUI(); invalidate("viewerHov");
  return SCR.route;
}
