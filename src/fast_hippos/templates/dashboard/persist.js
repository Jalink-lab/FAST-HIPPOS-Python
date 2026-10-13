// ---------------------------------------------------------------- remember the display settings of this dashboard
// Display choices are kept per dashboard (localStorage: also when it is opened again later); the view (frame, zoom,
// selection, scroll position) only across a reload of the tab, e.g. after 'Apply to run' (sessionStorage).
const PERSIST_KEY = "fast-hippos:" + location.pathname;
const DISPLAY_KEYS = ["lut", "dmin", "dmax", "bright", "isrc", "outl", "tsrc", "show", "tcol", "tmode", "sorted", "rows",
  "sortCol", "sortDir", "sx", "sy", "slogx", "slogy", "sclass", "tool", "showRoute", "scalebar", "fillMetric"];
function readStore(store) { try { return JSON.parse(store.getItem(PERSIST_KEY) || "null"); } catch { return null; } }
function writeStore(store, value) { try { store.setItem(PERSIST_KEY, JSON.stringify(value)); } catch { /* storage unavailable */ } }

// applied before the panels are built, so that they start with the remembered values
(function restoreDisplay() {
  const saved = readStore(localStorage); if (!saved) return;
  for (const k of DISPLAY_KEYS) if (k in saved && typeof saved[k] === typeof S[k]) S[k] = saved[k];
  if (!(S.dmax > S.dmin)) { S.dmin = D.display.min; S.dmax = D.display.max; }
  if (S.fillMetric && !(S.fillMetric in C)) S.fillMetric = "";
  if (!["hit", "cell"].includes(S.tcol)) S.tcol = D.screening.enabled ? "hit" : "cell";  // 'gray' no longer exists
  if (saved.theme) document.documentElement.dataset.theme = saved.theme;
})();

function saveState() {
  const display = { theme: document.documentElement.dataset.theme || "" };
  for (const k of DISPLAY_KEYS) display[k] = S[k];
  writeStore(localStorage, display);
  writeStore(sessionStorage, { frame: S.frame, sel: [...S.sel], view: { s: view.s, tx: view.tx, ty: view.ty, auto: view.auto },
    kzoom: S.kzoom, kstart: S.kstart, scroll: window.scrollY, screenClosed: $("scrbody").classList.contains("closed") });
}
addEventListener("pagehide", saveState);
addEventListener("beforeunload", saveState);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") saveState(); });

// after the panels are built: controls that do not read their value from S, and the view of a reloaded tab
function restoreSession() {
  const setIf = (id, prop, v) => { const el = $(id); if (el) el[prop] = v; };
  for (const id of ["sx", "sy"]) {  // an axis that no longer exists falls back to the default
    if (![...$(id).options].some(o => o.value === S[id])) S[id] = id === "sx" ? "mean_intensity" : "@value";
    $(id).value = S[id];
  }
  setIf("slogx", "checked", S.slogx); setIf("slogy", "checked", S.slogy); setIf("sclass", "checked", !!S.sclass);
  setIf("isrc", "value", S.isrc); setIf("bright", "value", Math.log10(S.bright)); setIf("vfill", "value", S.fillMetric);
  setIf("ksort", "checked", S.sorted); setIf("vroute", "checked", S.showRoute); setIf("vroute2", "checked", S.showRoute);
  setIf("dmin", "value", +(+S.dmin).toPrecision(4)); setIf("dmax", "value", +(+S.dmax).toPrecision(4));
  hitRGB = hexToRgb(css("--hit"));
  if (S.fillMetric) fillsChanged();
  const s = readStore(sessionStorage); if (!s) return;
  if (Number.isInteger(s.frame)) setFrame(s.frame);
  if (s.kzoom >= 1) { S.kzoom = s.kzoom; S.kstart = s.kstart || 0; syncKymoZoom(); invalidate("kymo", "kymoOvl"); }
  if (Array.isArray(s.sel)) selectMany(s.sel.filter(i => Number.isInteger(i) && i >= 0 && i < N), false);
  if (s.view && !s.view.auto) { Object.assign(view, { s: s.view.s, tx: s.view.tx, ty: s.view.ty, auto: false, fitted: true }); invalidate("viewer"); }
  if (typeof s.screenClosed === "boolean" && s.screenClosed !== $("scrbody").classList.contains("closed")) $("scrtoggle").click();
  if (s.scroll) requestAnimationFrame(() => requestAnimationFrame(() => scrollTo(0, s.scroll)));
}
