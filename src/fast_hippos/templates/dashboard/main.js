// ---------------------------------------------------------------- header, toolbar, start-up
function updateChips() {
  const ev = EV, p = SCR.params, nh = nHits();
  const ch = [
    `<span class="chip"><b>${N}</b> cells</span>`,
    `<span class="chip"><b>${T}</b> frames × ${FI.toFixed(3).replace(/\.?0+$/, "")} s</span>`,
    ev.baseline_only ? `<span class="chip">baseline only</span>` :
      `<span class="chip">stim <b>${ev.stimulation ?? "–"}</b> · cal <b>${ev.calibration ?? "–"}</b>${ev.detected ? " (auto)" : " (manual)"}</span>`,
  ];
  if (p.criteria.length || SCR.mode === "selection" || nh) ch.push(`<span class="chip hit" title="${SCR.mode === "selection" ? "hits chosen by hand" : p.criteria.map(c => `${c.logic} ${critText(c)}`).join("\n")}"><b>${nh}</b> hits${SCR.mode === "selection" ? " (manual)" : ""}</span>`);
  if (S.sel.size) ch.push(`<span class="chip"><b>${S.sel.size}</b> selected</span>`);
  $("chips").innerHTML = ch.join("");
}
function updateTimeLabel() { $("tlabel").textContent = `frame ${S.frame} / ${T - 1} · ${(S.frame * FI).toFixed(1)} s`; }
let playTimer = null;
function togglePlay() {
  S.playing = !S.playing; $("play").textContent = S.playing ? "❚❚" : "▶";
  if (S.playing) { const step = () => { if (!S.playing) return; setFrame(S.frame >= T - 1 ? 0 : S.frame + 1); playTimer = setTimeout(step, 110); }; step(); }
  else clearTimeout(playTimer);
}
function drawColorbar() {
  const c = $("vbarc"), x = c.getContext("2d"), img = x.createImageData(256, 1), L = LUTS[S.lut];
  for (let i = 0; i < 256; i++) { img.data[i * 4] = L[i * 3]; img.data[i * 4 + 1] = L[i * 3 + 1]; img.data[i * 4 + 2] = L[i * 3 + 2]; img.data[i * 4 + 3] = 255; }
  x.putImageData(img, 0, 0);
  $("vbarname").textContent = D.is_lifetime ? "Lifetime (ns)" : D.unit; $("vbar0").textContent = (+S.dmin).toPrecision(3); $("vbar1").textContent = (+S.dmax).toPrecision(3);
}
function initControls() {
  $("title").textContent = D.name; document.title = `${D.name} · FAST-HIPPOS`; $("ver").textContent = `fast-hippos ${D.version}`;
  const fr = $("frame"); fr.max = T - 1; fr.oninput = () => setFrame(+fr.value);
  $("play").onclick = togglePlay;
  const lut = $("lut"); Object.keys(LUTS).forEach(k => lut.add(new Option(k, k))); lut.value = S.lut;
  lut.onchange = () => { S.lut = lut.value; imageChanged(); invalidate("kymo", "hist"); drawColorbar(); };
  $("rangeName").textContent = D.is_lifetime ? "Lifetime (ns)" : D.unit;
  const step = D.is_lifetime ? 0.05 : Math.max(1e-3, +((S.dmax - S.dmin) / 50).toPrecision(1));
  for (const id of ["dmin", "dmax"]) { $(id).step = step; $(id).value = +S[id].toPrecision(4); $(id).oninput = () => {
    const v = parseFloat($(id).value); if (!Number.isFinite(v)) return; S[id] = v; if (S.dmax <= S.dmin) return;
    imageChanged(); invalidate(...ON.display); drawColorbar(); }; }
  $("tsrc").value = S.tsrc; $("tsrc").onchange = () => { S.tsrc = $("tsrc").value; invalidate(...ON.display, "table"); };
  $("show").value = S.show; $("show").onchange = () => { S.show = $("show").value; invalidate("traces", "tracesSel", "kymo", "kymoOvl", "hist", "scatter", "scatterSel", "cell"); };
  const setTool = seg($("tool"), S.tool, (v) => { S.tool = v; });
  $("theme").onclick = () => {
    const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    document.documentElement.dataset.theme = cur === "light" ? "dark" : "light"; hitRGB = hexToRgb(css("--hit")); outlinesChanged(); invalidate(...ALL()); updateScreenUI();
  };
  document.addEventListener("keydown", (e) => {
    const tag = e.target.tagName;
    if ((tag === "INPUT" && e.target.type !== "range" && e.target.type !== "checkbox") || tag === "SELECT" || tag === "TEXTAREA") return;
    if (e.key === " ") { e.preventDefault(); togglePlay(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); setFrame(S.frame + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); setFrame(S.frame - 1); }
    else if (e.key === "Escape") select(-1);
    else if (e.key === "z") $("vzsel").click();
    else if (e.key === "f") fitView();
    else if (e.key === "l") { S.tool = S.tool === "lasso" ? "rect" : "lasso"; setTool(S.tool); }
  });
  updateTimeLabel();
}

initControls(); initScreening(); initViewer(); initTraces(); initKymo(); initScatter(); initTable();
recompute(); drawColorbar(); updateChips();
new ResizeObserver(() => invalidate("traces", "tracesSel", "tracesHov", "kymo", "kymoOvl", "hist", "scatter", "scatterSel", "scatterHov", "cell")).observe(document.querySelector("main"));
matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => { hitRGB = hexToRgb(css("--hit")); outlinesChanged(); invalidate(...ALL()); });
invalidate(...ALL());
request("O/lab"); request("O/p");
const m0 = location.hash.match(/cell=(\d+)/);
if (m0) { const i = C.cell.indexOf(+m0[1]); if (i >= 0) { select(i); setTimeout(() => zoomTo([i]), 200); } }
