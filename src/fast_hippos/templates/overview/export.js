// ---------------------------------------------------------------- exports (downloads; they also work when the page is opened as a file)
const runName = safeName(D.title);
function needSelection() { const ks = selected(); if (!ks.length) alert("Select one or more images in the table first."); return ks; }
// hits with stage positions, in the visiting order of the run (its .rgn files), else by rank
function routeOrder(im) { return (im.has_positions ? im.hits : []).filter(h => h.x !== null).sort((a, b) => (a.chunk ?? 1e9) - (b.chunk ?? 1e9) || (a.visit ?? 0) - (b.visit ?? 0) || (a.rank ?? 0) - (b.rank ?? 0)); }
function downloadChunks(base, items, label) {  // split as the run does: files of at most max_hits_per_rgn positions
  const size = Math.max(1, D.max_hits_per_rgn || items.length), parts = [];
  for (let a = 0; a < items.length; a += size) parts.push(items.slice(a, a + size));
  parts.forEach((p, i) => { const a = i * size + 1, b = a + p.length - 1, name = parts.length > 1 ? `${base}_${a}-${b}.rgn` : `${base}.rgn`;
    setTimeout(() => download(name, rgnXml(p, label), "application/xml"), 350 * i); });
  return parts.length;
}
function exportRgnImages() {
  const ks = needSelection(); if (!ks.length) return;
  let n = 0, files = 0, skipped = [];
  ks.forEach((k, j) => { const im = IM[k], hits = routeOrder(im); if (!hits.length) { skipped.push(im.name); return; }
    setTimeout(() => { files += downloadChunks(`HITS_${runName}_${safeName(im.name)}`, hits.map(h => [h.x, h.y, `Cell_${h.cell}`]), "hits"); }, 400 * n++); });
  if (skipped.length) setTimeout(() => alert(`No .rgn file for (no hits, or no stage positions): ${skipped.join(", ")}`), 400 * n + 100);
}
function exportRgnSelection() {
  const ks = needSelection(); if (!ks.length) return;
  const items = [], skipped = ks.filter(k => IM[k].hits.length && !IM[k].has_positions).map(k => IM[k].name);
  for (const k of ks) if (IM[k].has_positions) for (const h of IM[k].hits) if (h.x !== null) items.push([h.x, h.y, `${safeName(IM[k].name)}_Cell_${h.cell}`, h.rank ?? 1e9]);
  if (!items.length) { alert("The selected images have no hits with stage positions."); return; }
  if (skipped.length && !confirm(`These images have no stage positions, so their hits are left out:\n${skipped.join("\n")}\n\nContinue?`)) return;
  items.sort((a, b) => a[3] - b[3]);
  let ordered = items;
  if (D.optimize_path && items.length > 2) {  // one route through all of them, starting at the first tile of the first selected image
    const t = IM[ks[0]].tiles[0], start = t ? [t[0] + t[2] / 2, t[1] + t[3] / 2] : null;
    const order = FHScreen.optimizePath(items.map(p => [p[0], p[1]]), 3000, start); ordered = order.map(i => items[i]);
  }
  downloadChunks(`HITS_${runName}_selection`, ordered.map(p => [p[0], p[1], p[2]]), "hits");
}
function exportHitsTsv() {
  const ks = needSelection(); if (!ks.length) return;
  const metrics = METRIC_KEYS, lines = [[...(EXP ? ["sample", "label"] : []), "image", "rank", "rgn_file", "stop", "cell", "x_m", "y_m", ...metrics].join("\t")];
  for (const k of ks) { const im = IM[k]; for (const h of im.hits) { const i = im.rowOfCell.get(h.cell);
    lines.push([...(EXP ? [im.sample, im.label || ""] : []), im.name, h.rank, h.chunk, h.visit, h.cell, h.x, h.y, ...metrics.map(m => (i !== undefined && im.C[m] ? im.C[m][i] : ""))].map(tsvCell).join("\t")); } }
  download(`${runName}_hits_selected_images.tsv`, lines.join("\n"), "text/tab-separated-values");
}
function exportImagesTsv() {
  const cols = COLS.filter(c => c.key !== "qc"), lines = [[...cols.map(c => c.label), "valid_cells", "qc_flags", "source"].join("\t")];
  const text = (html) => { const d = document.createElement("div"); d.innerHTML = html; return d.textContent; };
  for (const k of tableOrder()) { const im = IM[k]; lines.push([...cols.map(c => text(String(c.cell(im, k)))), im.n_valid, im.flags.map(f => f.key).join(","), im.source].map(tsvCell).join("\t")); }
  download(`${runName}_images.tsv`, lines.join("\n"), "text/tab-separated-values");
}
function exportCellsTsv() {
  const ks = needSelection(); if (!ks.length) return;
  const keys = [...new Set(ks.flatMap(k => Object.keys(IM[k].C)))], lines = [[...(EXP ? ["sample", "label"] : []), "image", ...keys].join("\t")];
  for (const k of ks) { const im = IM[k]; for (let i = 0; i < im.n_shown; i++) lines.push([...(EXP ? [im.sample, im.label || ""] : []), im.name, ...keys.map(c => (im.C[c] ? im.C[c][i] : ""))].map(tsvCell).join("\t")); }
  download(`${runName}_cells_selected_images.tsv`, lines.join("\n"), "text/tab-separated-values");
}
function initExports() {
  const menus = [["filesBtn", "filesMenu"], ["exportBtn", "exportMenu"]];
  for (const [b, m] of menus) $(b).onclick = (e) => { e.stopPropagation(); for (const [, o] of menus) if (o !== m) $(o).classList.remove("open"); $(m).classList.toggle("open"); };
  document.addEventListener("click", () => menus.forEach(([, m]) => $(m).classList.remove("open")));
  const act = { rgnImages: exportRgnImages, rgnSelection: exportRgnSelection, hitsTsv: exportHitsTsv, imagesTsv: exportImagesTsv, cellsTsv: exportCellsTsv };
  $("exportMenu").addEventListener("click", (e) => { const b = e.target.closest("[data-x]"); if (b) act[b.dataset.x](); });
  if (!SCREEN) $("exportMenu").querySelectorAll('[data-x^="rgn"], [data-x="hitsTsv"]').forEach(b => b.remove());
  if (EXP) { // the samples are different specimens: one route through several of them makes no sense
    const b = $("exportMenu").querySelector('[data-x="rgnSelection"]'); if (b) b.remove();
    $("filesBtn").textContent = "Samples ▾"; $("filesBtn").title = "The overviews of the samples (runs) in this experiment folder, and the files of the experiment";
  }
  // the files of the run, grouped
  const groups = [["Tables", /\.tsv$/i], ["Stage positions (.rgn)", /\.rgn$/i], ["Plots", /\.png$/i], ["Stitched images", /\.tif$/i], ["Logs and settings", /\.(txt|json|toml)$/i]];
  const samples = EXP ? '<div class="grp">Samples</div>' + RUNS.map(r => `<a href="${esc(encPath(r.href))}" target="_blank" title="The overview of this run">${esc(r.name)}${r.label ? ` <span class="muted">· ${esc(r.label)}</span>` : ""}</a>`).join("") : "";
  $("filesMenu").innerHTML = samples + groups.map(([g, re]) => { const fs = D.files.filter(f => re.test(f)); return fs.length ? `<div class="grp">${g}</div>` + fs.map(f => `<a href="${encodeURIComponent(f)}" target="_blank">${esc(f)}</a>`).join("") : ""; }).join("") || samples || '<div class="grp">No files</div>';
}
