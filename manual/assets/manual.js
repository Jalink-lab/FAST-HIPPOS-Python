// The filter of the settings reference: shows the settings whose name, key or text contain all typed words
// (Material loads pages without a full reload, so this hooks into its document$ stream)
function fhFilter() {
  const box = document.getElementById("fh-filter");
  if (!box) return;
  const run = () => {
    const words = box.value.toLowerCase().split(/\s+/).filter(Boolean);
    document.querySelectorAll("table.fh-settings").forEach(t => {
      let shown = 0;
      t.querySelectorAll("tbody tr").forEach(tr => {
        const ok = words.every(w => tr.dataset.search.includes(w));
        tr.classList.toggle("fh-hidden", !ok); shown += ok;
      });
      t.classList.toggle("fh-hidden", !shown);
      const h = t.previousElementSibling; if (h && h.classList.contains("fh-group")) h.classList.toggle("fh-hidden", !shown);
    });
    document.querySelectorAll(".md-typeset h2").forEach(h2 => {  // a card heading without visible settings
      let el = h2.nextElementSibling, any = false;
      while (el && el.tagName !== "H2") { if (el.matches("table.fh-settings:not(.fh-hidden)")) any = true; el = el.nextElementSibling; }
      h2.classList.toggle("fh-hidden", !any && words.length > 0);
    });
  };
  box.addEventListener("input", run);
}
if (window.document$) document$.subscribe(fhFilter); else document.addEventListener("DOMContentLoaded", fhFilter);
