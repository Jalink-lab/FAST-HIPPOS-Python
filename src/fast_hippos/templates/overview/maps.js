// ---------------------------------------------------------------- hit positions: one map per image
// Stage positions in m (the frame of the .rgn files); x to the right and y downwards, so that a map looks like its image.
const mapGeo = new Map();  // k -> {x0, y0, s, w, h} of the drawn map (for hover)
function extentOf(im) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  const add = (x, y) => { if (!Number.isFinite(x) || !Number.isFinite(y)) return; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); };
  for (const [tx, ty, tw, th] of im.tiles) { add(tx, ty); add(tx + tw, ty + th); }
  for (const h of im.hits) add(h.x, h.y);
  if (!Number.isFinite(x0)) return null;
  const pad = Math.max(x1 - x0, y1 - y0, 1e-5) * 0.04; return [x0 - pad, y0 - pad, x1 + pad, y1 + pad];
}
function drawMaps() {
  const box = $("maps"), ks = selected().filter(k => IM[k].hits.length || IM[k].n_tiles);
  if (!hasPositions) { $("mapsPanel").style.display = "none"; return; }
  $("mapsPanel").style.display = "";
  if (!ks.length) { box.innerHTML = `<div class="mapsmsg">${selected().length ? "The selected images have no hits" : "Select images in the table"}</div>`; return; }
  box.innerHTML = ks.map(k => { const im = IM[k];
    return `<div class="mapcard" data-k="${k}"><div class="mh"><span class="sw" style="background:${imgColor(k)}"></span><span class="n" title="${esc(im.name)}">${esc(im.name)}</span><span class="muted">${im.screened === false ? "not screened" : `${im.n_hits} hit${im.n_hits === 1 ? "" : "s"}`}</span>` +
      (im.href ? `<a href="${esc(encPath(im.href))}" target="_blank" title="Open the dashboard of this image">↗</a>` : "") + "</div>" +
      (im.has_positions ? `<canvas data-k="${k}"></canvas>` : `<div class="empty">No stage positions for this image: its hits cannot be visited</div>`) + "</div>"; }).join("");
  const ext = new Map(ks.map(k => [k, extentOf(IM[k])]));
  const span = S.sameScale ? Math.max(...[...ext.values()].filter(Boolean).map(e => Math.max(e[2] - e[0], e[3] - e[1]))) : null;
  for (const c of box.querySelectorAll("canvas")) drawMap(c, +c.dataset.k, ext.get(+c.dataset.k), span);
}
function drawMap(c, k, e, span) {
  const im = IM[k], r = c.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  c.width = Math.round(r.width * dpr); c.height = Math.round(r.height * dpr);
  const ctx = c.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, r.width, r.height);
  if (!e) return;
  const w = r.width, h = r.height, ex = span ?? (e[2] - e[0]), ey = span ?? (e[3] - e[1]), s = Math.min((w - 16) / ex, (h - 24) / ey);
  const ox = (w - (e[2] - e[0]) * s) / 2, oy = (h - 14 - (e[3] - e[1]) * s) / 2;
  const X = (x) => ox + (x - e[0]) * s, Y = (y) => oy + (y - e[1]) * s;
  mapGeo.set(k, { X, Y });
  ctx.strokeStyle = css("--line"); ctx.lineWidth = 1;
  for (const [tx, ty, tw, th] of im.tiles) ctx.strokeRect(X(tx), Y(ty), tw * s, th * s);
  // the visiting order of the run's .rgn files: the stops of this image within one file are connected; where the
  // route visits other images in between (neighbouring images of a scan), the line is dashed
  const route = im.hits.filter(h => h.chunk !== null && h.x !== null).sort((a, b) => a.chunk - b.chunk || a.visit - b.visit);
  const fade = S.hover >= 0 && S.hover !== k ? 0.4 : 1;
  ctx.strokeStyle = withAlpha(imgColor(k), 0.85 * fade); ctx.lineWidth = 1.2;
  for (const direct of [true, false]) {
    ctx.setLineDash(direct ? [] : [3, 3]); ctx.beginPath();
    for (let i = 1; i < route.length; i++) {
      const p = route[i], q = route[i - 1];
      if (q.chunk === p.chunk && (p.visit === q.visit + 1) === direct) { ctx.moveTo(X(q.x), Y(q.y)); ctx.lineTo(X(p.x), Y(p.y)); }
    }
    ctx.stroke();
  }
  ctx.setLineDash([]);
  if (route.length) { ctx.fillStyle = imgColor(k); ctx.beginPath(); ctx.arc(X(route[0].x), Y(route[0].y), 3.5, 0, 7); ctx.fill(); }
  ctx.fillStyle = withAlpha(css("--hit"), fade);
  for (const p of im.hits) { if (p.x === null) continue; ctx.beginPath(); ctx.arc(X(p.x), Y(p.y), 1.8, 0, 7); ctx.fill(); }
  // scale bar
  const target = 70 / s, mag = Math.pow(10, Math.floor(Math.log10(target))), len = [1, 2, 5, 10].map(m => m * mag).filter(v => v <= target).pop() || mag;
  ctx.fillStyle = css("--muted"); ctx.fillRect(8, h - 10, len * s, 3); ctx.font = "10px system-ui"; ctx.textBaseline = "bottom";
  ctx.fillText(len >= 1e-3 ? `${+(len * 1e3).toPrecision(3)} mm` : `${+(len * 1e6).toPrecision(3)} µm`, 8, h - 12);
}
function mapPick(e) {
  const c = e.target.closest("canvas[data-k]"); if (!c) return null;
  const k = +c.dataset.k, g = mapGeo.get(k); if (!g) return null;
  const [px, py] = localXY(e, c); let best = null, bd = 49;
  for (const h of IM[k].hits) { if (h.x === null) continue; const d = (g.X(h.x) - px) ** 2 + (g.Y(h.y) - py) ** 2; if (d < bd) { bd = d; best = h; } }
  return { k, hit: best };
}
function initMaps() {
  const box = $("maps");
  box.addEventListener("mousemove", (e) => {
    const p = mapPick(e); const card = e.target.closest(".mapcard"); setHover(card ? +card.dataset.k : -1);
    if (!p || !p.hit) { showTip(null); return; }
    const h = p.hit, im = IM[p.k];
    showTip(`<b>${esc(im.name)} · cell ${h.cell}</b><br>rank ${h.rank ?? "–"} in the run` + (h.chunk ? ` · .rgn file ${h.chunk}, stop ${h.visit}` : "") +
      `<br>x ${fmt(h.x * 1e3, 3)} mm · y ${fmt(h.y * 1e3, 3)} mm${im.href ? '<br><span class="muted">click to open in the dashboard</span>' : ""}`, e);
  });
  box.addEventListener("mouseleave", () => { showTip(null); setHover(-1); });
  box.addEventListener("click", (e) => { const p = mapPick(e); if (p && p.hit) openCell(IM[p.k], p.hit.cell); });
  $("sameScale").onchange = () => { S.sameScale = $("sameScale").checked; invalidate("maps"); };
}

// ---------------------------------------------------------------- hits of the selected images
const HIT_SORT = { col: "rank", dir: 1 };
function hitRows() {
  const rows = [];
  for (const k of selected()) { const im = IM[k]; for (const h of im.hits) { const i = im.rowOfCell.get(h.cell); rows.push({ k, im, h, i }); } }
  const v = (r) => (HIT_SORT.col === "image" ? r.im.name : HIT_SORT.col === "sample" ? r.im.sample : HIT_SORT.col in r.h ? r.h[HIT_SORT.col] : r.i !== undefined && r.im.C[HIT_SORT.col] ? r.im.C[HIT_SORT.col][r.i] : NaN);
  return rows.sort((a, b) => { const va = v(a), vb = v(b), na = va === null || Number.isNaN(va), nb = vb === null || Number.isNaN(vb);
    if (na || nb) return na - nb; return (va < vb ? -1 : va > vb ? 1 : 0) * HIT_SORT.dir; });
}
function drawHits() {
  if (!SCREEN) { $("hitsPanel").style.display = "none"; return; }
  const rows = hitRows(), metrics = [...new Set(D.criteria.map(c => c.metric).filter(m => METRIC_KEYS.includes(m)))];
  $("hitsinfo").textContent = `${rows.length} hit${rows.length === 1 ? "" : "s"} in the selected images`;
  $("hitsToggle").textContent = S.hitsOpen ? "▾" : "▸"; $("hitstbl").classList.toggle("closed", !S.hitsOpen);
  if (!S.hitsOpen) return;
  const cols = [...(EXP ? [["sample", "Sample", "The sample (run) of the hit"]] : []), ["image", "Image", "The image of the hit"],
    ["rank", "Rank", EXP ? "Rank of the hit in the hit list of its sample (run)" : "Rank of the hit in the hit list of the run"], ["chunk", ".rgn file", "Number of the .rgn file (chunk) of the run that holds this hit"],
    ["visit", "Stop", "Place in the visiting order of that .rgn file"], ["cell", "Cell", "Cell number in its image"], ["x", "x (mm)", "Stage x"], ["y", "y (mm)", "Stage y"],
    ...metrics.map(m => [m, m, metricTip(m)])];
  const head = "<tr>" + cols.map(([k, l, t]) => `<th class="${k === "image" || k === "sample" ? "l" : ""}" data-k="${k}" title="${esc(t)}">${esc(l)}${HIT_SORT.col === k ? (HIT_SORT.dir > 0 ? " ▴" : " ▾") : ""}</th>`).join("") + "</tr>";
  const body = rows.slice(0, 5000).map(r => `<tr data-k="${r.k}" data-c="${r.h.cell}">${EXP ? `<td class="l">${esc(r.im.sample)}</td>` : ""}<td class="l"><span class="sw" style="background:${imgColor(r.k)}"></span> ${esc(r.im.name)}</td><td>${r.h.rank ?? "–"}</td><td>${r.h.chunk ?? "–"}</td><td>${r.h.visit ?? "–"}</td><td>${r.h.cell}</td>` +
    `<td>${r.h.x === null ? "–" : fmt(r.h.x * 1e3, 3)}</td><td>${r.h.y === null ? "–" : fmt(r.h.y * 1e3, 3)}</td>` + metrics.map(m => `<td>${r.i !== undefined && r.im.C[m] ? fmt(r.im.C[m][r.i]) : "–"}</td>`).join("") + "</tr>").join("");
  $("hitstbl").innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}
function initHits() {
  $("hitsToggle").onclick = () => { S.hitsOpen = !S.hitsOpen; invalidate("hits"); };
  $("hitstbl").addEventListener("click", (e) => {
    const th = e.target.closest("th[data-k]"); if (th) { HIT_SORT.dir = HIT_SORT.col === th.dataset.k ? -HIT_SORT.dir : 1; HIT_SORT.col = th.dataset.k; invalidate("hits"); return; }
    const tr = e.target.closest("tr[data-k]"); if (tr) openCell(IM[+tr.dataset.k], +tr.dataset.c);
  });
}
layer("maps", drawMaps); layer("hits", drawHits);
