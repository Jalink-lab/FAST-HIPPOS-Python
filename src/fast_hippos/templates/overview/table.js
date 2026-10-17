// ---------------------------------------------------------------- the images table
const pct = (a, b) => (b ? (100 * a) / b : NaN);
const num = (v, d = 3) => (v === null || v === undefined || Number.isNaN(v) ? "–" : fmt(v, d));
const flagLevel = (im) => (im.flags.some(f => f.level === "bad") ? "bad" : im.flags.some(f => f.level === "warn") ? "warn" : im.flags.length ? "info" : "ok");
const LEVEL_RANK = { ok: 0, info: 1, warn: 2, bad: 3 };
const flagOn = (im, key) => im.flags.find(f => f.key === key);
const maxHitPct = Math.max(1e-9, ...IM.map(im => pct(im.n_hits, im.n_valid)).filter(Number.isFinite));
const shortMetric = (m) => m.replace("response_", "resp. ").replace("_diff", " Δ").replace("_abs", "").replace("_", " ");

// columns: key, label, tip, value (for sorting), cell (html), optional condition; QC flags tint the cell they concern
const COLS = [
  { key: "index", label: "#", tip: "Number of the image in the run (the order in which they were analyzed)", v: im => im.index, cell: im => im.index + 1 },
  { key: "name", label: "Image", l: true, tip: "Name of the image; click it to open its dashboard (cells, traces, kymograph and hits of this image)",
    v: im => im.name.toLowerCase(),
    cell: im => (im.thumb ? `<img class="thumb" src="${im.thumb}" alt="">` : "") +
      (im.href ? `<a href="${esc(im.href)}" target="_blank" title="Open the dashboard of ${esc(im.name)}">${esc(im.name)}</a>`
        : `<span class="nolink" title="No dashboard was written for this image (display.dashboard is off)">${esc(im.name)}</span>`) },
  { key: "qc", label: "QC", tip: "Quality flags of the image (warnings only; nothing is filtered). Hover the dot for the flags and their thresholds; the chips below the table select the images with a flag",
    v: im => LEVEL_RANK[flagLevel(im)],
    cell: im => `<span class="qcdot ${flagLevel(im)}" title="${esc(im.flags.length ? im.flags.map(f => `${FLAG_LABEL[f.key]}: ${f.text}`).join("\n") : "No flags")}"></span>` },
  { key: "cells", label: "Cells", tip: "Number of cells found in the image", v: im => im.n_cells, cell: im => im.n_cells.toLocaleString("en"), flag: "few_cells" },
  { key: "valid", label: "Valid", tip: "Cells that pass the quality gates (calibration − baseline, baseline deviation): number and percentage of all cells",
    v: im => pct(im.n_valid, im.n_cells), cell: im => `${im.n_valid.toLocaleString("en")} · ${num(pct(im.n_valid, im.n_cells), 0)} %`, flag: "low_valid" },
  { key: "hits", label: "Hits", if: SCREEN, tip: "Number of hits in the image", v: im => im.n_hits, cell: im => im.n_hits, flag: "no_hits" },
  { key: "hitpct", label: "Hit %", if: SCREEN, tip: "Hits as a percentage of the valid cells; the bar compares the images",
    v: im => pct(im.n_hits, im.n_valid), cell: (im, k) => { const p = pct(im.n_hits, im.n_valid);
      return Number.isFinite(p) ? `<span class="bar" style="width:${Math.max(1, 40 * p / maxHitPct)}px;background:${imgColor(k)}"></span>${num(p, 2)}` : "–"; } },
  { key: "baseline", label: "Baseline", tip: `Median baseline (lifetime before the stimulation) of the valid cells${UNIT ? `, in ${UNIT}` : ""}`, v: im => im.baseline, cell: im => num(im.baseline) },
  { key: "response", label: shortMetric(D.response_metric), if: hasStim, tip: `Median ${D.response_metric} of the valid cells: ${metricTip(D.response_metric)}`, v: im => im.response, cell: im => num(im.response) },
  { key: "hitresp", label: "hits: " + shortMetric(D.response_metric), if: SCREEN && hasStim, tip: `Median ${D.response_metric} of the hits only`, v: im => im.hit_response, cell: im => num(im.hit_response) },
  { key: "cal", label: "Cal Δ", if: hasCal, tip: "Median calibration − baseline of the valid cells: shows that the calibration (and the sensor) worked", v: im => im.cal_delta, cell: im => num(im.cal_delta), flag: "no_cal_response" },
  { key: "frames", label: "Frames · Δt", tip: "Number of frames and the time between frames", v: im => im.frames, cell: im => `${im.frames} · ${num(im.frame_interval, 2)} s` },
  { key: "stim", label: "Stim", if: hasStim, tip: "First frame with the stimulation (0-based); auto = detected, set = from the settings; – = none",
    v: im => im.events.stimulation ?? -1, cell: im => im.events.stimulation === null ? "–" : `${im.events.stimulation}<span class="tag">${im.events.detected ? "auto" : "set"}</span>`, flag: ["no_stimulation", "event_offset"] },
  { key: "calf", label: "Cal", if: hasCal, tip: "First frame with the calibration (0-based); – = none",
    v: im => im.events.calibration ?? -1, cell: im => im.events.calibration === null ? "–" : `${im.events.calibration}<span class="tag">${im.events.detected ? "auto" : "set"}</span>`, flag: "no_calibration" },
  { key: "class", label: "Class+", if: IM.some(im => im.class_pos !== null), tip: "Percentage of cells in class 1 of the additional channel (e.g. transfected)", v: im => im.class_pos, cell: im => num(im.class_pos, 1) },
  { key: "area", label: "Tiles · area", if: IM.some(im => im.n_tiles), tip: "Number of tiles of the scan and the scanned area", v: im => im.area_mm2 ?? -1,
    cell: im => (im.n_tiles ? `${im.n_tiles} · ${num(im.area_mm2, 2)} mm²` : "–"), flag: "no_positions" },
].filter(c => c.if === undefined || c.if);

function tableOrder() {
  const col = COLS.find(c => c.key === S.sortCol) || COLS[0], dir = S.sortDir;
  return IM.map(im => im.k).sort((a, b) => {
    const va = col.v(IM[a]), vb = col.v(IM[b]);
    const na = va === null || va === undefined || Number.isNaN(va), nb = vb === null || vb === undefined || Number.isNaN(vb);
    if (na || nb) return na - nb || a - b;
    return (va < vb ? -1 : va > vb ? 1 : 0) * dir || a - b;
  });
}
function drawTable() {
  const order = tableOrder(), all = order.length && order.every(k => S.sel.has(k));
  const head = `<tr><th class="l" title="Select all or none"><input type="checkbox" id="selHead" ${all ? "checked" : ""}></th>` +
    COLS.map(c => `<th class="${c.l ? "l" : ""}" data-k="${c.key}" title="${esc(c.tip)}">${esc(c.label)}${S.sortCol === c.key ? (S.sortDir > 0 ? " ▴" : " ▾") : ""}</th>`).join("") + "</tr>";
  const rows = order.map(k => {
    const im = IM[k];
    const tds = COLS.map(c => {
      const flags = [].concat(c.flag || []).map(f => flagOn(im, f)).filter(Boolean), lvl = flags.some(f => f.level === "bad") ? "bad" : flags.some(f => f.level === "warn") ? "warn" : "";
      return `<td class="${c.l ? "l " : ""}${lvl}"${flags.length ? ` title="${esc(flags.map(f => f.text).join("\n"))}"` : ""}>${c.cell(im, k)}</td>`;
    }).join("");
    return `<tr class="r ${S.sel.has(k) ? "sel" : ""} ${S.hover === k ? "hov" : ""}" data-k="${k}"><td class="l"><input type="checkbox" ${S.sel.has(k) ? "checked" : ""} title="Select this image"> <span class="sw" style="background:${imgColor(k)}"></span></td>${tds}</tr>`;
  }).join("");
  $("imgtbl").innerHTML = `<thead>${head}</thead><tbody>${rows}</tbody>`;
  $("selinfo").textContent = `${S.sel.size} of ${NI} selected`;
  drawQC();
}
function drawTableHov() { document.querySelectorAll("#imgtbl tr.r").forEach(tr => tr.classList.toggle("hov", +tr.dataset.k === S.hover)); }
// one chip per kind of flag that occurs: how many images, the rule on hover, a click selects them
function drawQC() {
  const kinds = new Map();
  for (const im of IM) for (const f of im.flags) { if (!kinds.has(f.key)) kinds.set(f.key, { f, ks: [] }); kinds.get(f.key).ks.push(im.k); }
  $("qc").innerHTML = [...kinds.values()].map(({ f, ks }) => {
    const lvl = ks.some(k => flagOn(IM[k], f.key).level === "bad") ? "bad" : f.level;
    return `<button class="qcchip ${lvl}" data-flag="${f.key}" title="${esc(f.text)}\n\nClick to select these images">${ks.length} image${ks.length > 1 ? "s" : ""}: ${FLAG_LABEL[f.key]}</button>`;
  }).join("");
}
function selectionChanged() { invalidate("table", "resp", "metric", "maps", "hits", "chips", "legend"); }
function initTable() {
  const tbl = $("imgtbl");
  tbl.addEventListener("click", (e) => {
    const th = e.target.closest("th[data-k]");
    if (th) { const k = th.dataset.k; S.sortDir = S.sortCol === k ? -S.sortDir : 1; S.sortCol = k; invalidate("table", "resp", "metric", "maps", "hits", "legend"); return; }
    if (e.target.id === "selHead") { S.sel = e.target.checked ? new Set(IM.map(im => im.k)) : new Set(); selectionChanged(); return; }
    const tr = e.target.closest("tr.r"); if (!tr || e.target.closest("a")) return;
    const k = +tr.dataset.k;
    if (e.target.type === "checkbox" || e.ctrlKey || e.metaKey) { S.sel.has(k) ? S.sel.delete(k) : S.sel.add(k); }
    else if (e.shiftKey && S.last >= 0) { const o = tableOrder(), a = o.indexOf(S.last), b = o.indexOf(k); for (let i = Math.min(a, b); i <= Math.max(a, b); i++) S.sel.add(o[i]); }
    else S.sel = new Set([k]);
    S.last = k; selectionChanged();
  });
  tbl.addEventListener("mouseover", (e) => { const tr = e.target.closest("tr.r"); setHover(tr ? +tr.dataset.k : -1); });
  tbl.addEventListener("mouseleave", () => setHover(-1));
  $("qc").addEventListener("click", (e) => { const b = e.target.closest("[data-flag]"); if (!b) return; S.sel = new Set(IM.filter(im => flagOn(im, b.dataset.flag)).map(im => im.k)); selectionChanged(); });
  $("selAll").onclick = () => { S.sel = new Set(IM.map(im => im.k)); selectionChanged(); };
  $("selNone").onclick = () => { S.sel = new Set(); selectionChanged(); };
}
layer("table", drawTable); layer("tableHov", drawTableHov);
