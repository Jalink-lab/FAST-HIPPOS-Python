// ---------------------------------------------------------------- shared by the dashboard and the run Overview
// Helpers that do not depend on the data of a page (templates/common, loaded before the page's own scripts).
const $ = (id) => document.getElementById(id);
function b64bytes(s) { const b = atob(s); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }
function b64f32(s) { return s ? new Float32Array(b64bytes(s).buffer) : null; }
function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
const fmt = (v, d = 3) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  if (!Number.isFinite(v)) return v > 0 ? "∞" : "−∞";
  if (a >= 1e7 || (a < 1e-4 && v !== 0)) return v.toExponential(2);
  return a >= 1000 ? v.toFixed(Math.min(d, 1)) : (+v).toFixed(d);
};
// ---------------------------------------------------------------- redraw scheduling
// Each panel registers named layers; invalidate() marks them, one animation frame redraws them in order. A layer
// that marks a later layer (the image marks its outlines) gets it drawn in the same frame, so that they move together.
const LAYERS = [];  // [name, fn]
function layer(name, fn) { LAYERS.push([name, fn]); }
const dirty = new Set();
let rafPending = false;
function invalidate(...names) { names.forEach(n => dirty.add(n)); if (!rafPending) { rafPending = true; requestAnimationFrame(flush); } }
function flush() {
  rafPending = false;
  for (const [name, fn] of LAYERS) if (dirty.delete(name)) { try { fn(); } catch (e) { console.error(name, e); } }
}
const ALL = () => LAYERS.map(l => l[0]);
function hexToRgb(h) { const c = document.createElement("canvas").getContext("2d"); c.fillStyle = h; const s = c.fillStyle; return s.startsWith("#") ? [parseInt(s.slice(1, 3), 16), parseInt(s.slice(3, 5), 16), parseInt(s.slice(5, 7), 16)] : [255, 255, 255]; }
function withAlpha(color, a) { const [r, g, b] = hexToRgb(color); return `rgba(${r},${g},${b},${a})`; }

// Hover texts (title attributes) are drawn by the browser, which makes them very wide; break them into lines of
// about 60 characters when the mouse comes over them (works for titles set later too; already short lines stay).
function wrapTitle(t, n = 60) {
  return t.split("\n").map(line => {
    if (line.length <= n) return line;
    const out = []; let cur = "";
    for (const w of line.split(" ")) { if (cur && cur.length + 1 + w.length > n) { out.push(cur); cur = w; } else cur = cur ? cur + " " + w : w; }
    return out.concat(cur ? [cur] : []).join("\n");
  }).join("\n");
}
document.addEventListener("mouseover", (e) => {
  for (let el = e.target; el && el.nodeType === 1; el = el.parentNode) {
    if (el.title) { const w = wrapTitle(el.title); if (w !== el.title) el.title = w; return; }
  }
}, true);

// ---------------------------------------------------------------- downloads and Leica .rgn files
function download(name, text, type) { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); }
function uuid() { return crypto.randomUUID ? crypto.randomUUID() : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === "x" ? r : (r & 3 | 8)).toString(16); }); }
function rgnXml(items, name) {
  let body = "", stack = "";
  items.forEach(([x, y, tag], n) => { const id = uuid();
    body += `<Item${n}>\n<Number>${n + 1}</Number>\n<Tag>${tag}</Tag>\n<Identifier>${id}</Identifier>\n<Type>Point</Type>\n<Fill>R:1,G:0,B:0,A:0</Fill>\n<Font />\n<Verticies>\n<Items>\n<Item0>\n<X>${x.toFixed(10)}</X>\n<Y>${y.toFixed(10)}</Y>\n</Item0>\n</Items>\n</Verticies>\n<DecoratorColors>\n<Items />\n</DecoratorColors>\n<ExtendedProperties>\n<Items />\n</ExtendedProperties>\n</Item${n}>\n`;
    stack += `<Entry Identifier="${id}" Begin="0.0000000000" End="0.0000000000" SectionCount="0" ReferenceX="0.0000000000" ReferenceY="0.0000000000" FocusStabilizerOffset="0.0000000000" FocusStabilizerOffsetFixed="false" StackValid="false" Marked="false" />\n`; });
  return `<StageOverviewRegions>\n<Regions>\n<ShapeList>\n<Items>\n<Item0>\n<Name>${name}</Name>\n<Identifier>${uuid()}</Identifier>\n<Type>CompoundShape</Type>\n<Font />\n<Verticies>\n<Items />\n</Verticies>\n<DecoratorColors>\n<Items />\n</DecoratorColors>\n<ExtendedProperties>\n<Items />\n</ExtendedProperties>\n<Children>\n<Items>\n${body}</Items>\n</Children>\n</Item0>\n</Items>\n<FillMaskMode>None</FillMaskMode>\n<VertexUnitMode>Pixels</VertexUnitMode>\n</ShapeList>\n</Regions>\n<StackList>\n${stack}</StackList>\n</StageOverviewRegions>\n`;
}
