// ---------------------------------------------------------------- cell table (virtual scrolling)
let TCOLS = [], tableRows = [];
const hasValues = (k) => k in C && Array.prototype.some.call(C[k], v => v !== null && !Number.isNaN(v));
function tableColumns() {
  const crit = SCR.params.criteria.map(c => c.metric);
  return [["cell", "cell", 0], ["hit", "hit", -1], ["@value", D.is_lifetime ? "τ @ frame" : "value @ frame", 3]].concat(
    ["valid", "class_additional"].filter(k => k in C).map(k => [k, k.replace("class_additional", "class"), 0]),
    [...new Set([...crit, "area_px", "mean_intensity", "baseline_mean", "response_mean_abs", "response_mean_diff", "response_max_diff",
      "response_fraction", "rise_time_frames", "rapid_response_ratio", "calibration_diff", "additional_intensity", "pos_x_px", "pos_y_px", "abs_x_m", "abs_y_m"])]
      .filter(hasValues).map(k => [k, k, k.startsWith("abs_") ? 7 : k.endsWith("_px") || k === "area_px" ? 0 : 3]));
}
function cellValue(key, i) { if (key === "@value") return val(S.frame, i); const v = C[key][i]; return v === null ? NaN : v; }
function drawTable() {
  TCOLS = tableColumns();
  const rows = [];
  for (let i = 0; i < N; i++) { if (S.rows === "hits" && !HIT[i]) continue; if (S.rows === "sel" && !S.sel.has(i)) continue; if (S.rows === "valid" && !C.valid[i]) continue; rows.push(i); }
  if (S.sortCol) { const k = S.sortCol, dir = S.sortDir; rows.sort((a, b) => { const va = cellValue(k, a), vb = cellValue(k, b); if (Number.isNaN(va)) return 1; if (Number.isNaN(vb)) return -1; return (va - vb) * dir; }); }
  tableRows = rows;
  const head = TCOLS.map(([k, l]) => `<th data-k="${k}" title="${(D.screen.metrics[k] || "").replace(/"/g, "")}">${l}${S.sortCol === k ? (S.sortDir > 0 ? " ▲" : " ▼") : ""}</th>`).join("");
  $("tbl").innerHTML = `<table><thead><tr>${head}</tr></thead><tbody></tbody></table>`;
  $("tbl").querySelectorAll("th").forEach(th => th.onclick = () => { const k = th.dataset.k; if (S.sortCol === k) S.sortDir *= -1; else { S.sortCol = k; S.sortDir = k === "cell" ? 1 : -1; } drawTable(); });
  $("tinfo").textContent = `${rows.length} rows`;
  updateTableRows();
}
const ROWH = 24;
function updateTableRows() {
  const box = $("tbl"), tb = box.querySelector("tbody"); if (!tb) return;
  const first = Math.max(0, Math.floor(box.scrollTop / ROWH) - 10), last = Math.min(tableRows.length, first + Math.ceil(box.clientHeight / ROWH) + 30);
  let html = first ? `<tr style="height:${first * ROWH}px"><td colspan="${TCOLS.length}"></td></tr>` : "";
  for (let r = first; r < last; r++) {
    const i = tableRows[r], cls = ["r"]; if (S.sel.has(i)) cls.push("sel"); if (S.hover === i) cls.push("hov");
    html += `<tr class="${cls.join(" ")}" data-i="${i}">` + TCOLS.map(([k, , d]) => {
      if (k === "hit") return `<td>${HIT[i] ? '<span class="dot"></span>' : ""}</td>`;
      if (k === "valid") return `<td>${C.valid[i] ? "✓" : "<span class=muted>✗</span>"}</td>`;
      const v = cellValue(k, i); return `<td>${Number.isNaN(v) ? "–" : d === 0 ? Math.round(v) : fmt(v, d)}</td>`;
    }).join("") + "</tr>";
  }
  const rest = tableRows.length - last; if (rest > 0) html += `<tr style="height:${rest * ROWH}px"><td colspan="${TCOLS.length}"></td></tr>`;
  tb.innerHTML = html;
}
let hovRow = null;
function markTableHover() {  // cheap: only toggles a class on the rendered rows
  if (hovRow) hovRow.classList.remove("hov");
  hovRow = S.hover >= 0 ? $("tbl").querySelector(`tr[data-i="${S.hover}"]`) : null;
  if (hovRow) hovRow.classList.add("hov");
}
layer("table", drawTable); layer("tableRows", updateTableRows); layer("tableHov", markTableHover);
function initTable() {
  const box = $("tbl");
  box.addEventListener("scroll", () => invalidate("tableRows"));
  box.addEventListener("mouseover", (e) => { const tr = e.target.closest("tr.r"); if (tr) setHover(+tr.dataset.i); });
  box.addEventListener("mouseleave", () => setHover(-1));
  box.addEventListener("click", (e) => {
    const tr = e.target.closest("tr.r"); if (!tr) return; const i = +tr.dataset.i;
    if (e.shiftKey && S.lastClicked >= 0) { const a = tableRows.indexOf(S.lastClicked), b = tableRows.indexOf(i); if (a >= 0 && b >= 0) { selectMany(tableRows.slice(Math.min(a, b), Math.max(a, b) + 1), true); return; } }
    select(i, e);
  });
  box.addEventListener("dblclick", (e) => { const tr = e.target.closest("tr.r"); if (tr) zoomTo([+tr.dataset.i]); });
  $("rows").value = S.rows; $("rows").onchange = () => { S.rows = $("rows").value; invalidate("table"); };
  $("clearsel").onclick = () => select(-1);
  $("selhits").onclick = () => selectMany(HIT.map((h, i) => h ? i : -1).filter(i => i >= 0), false);
  $("csv").onclick = exportCSV; $("rgn").onclick = exportRGN; $("rgn").disabled = !HAS_ABS;
}
