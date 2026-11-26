// ---------------------------------------------------------------- questions and messages in the page
// The browser's own alert/confirm/prompt boxes put the page's address on top ("127.0.0.1:8765 says"); these are drawn
// by the page itself, with the FAST-HIPPOS name and icon. Shared by the window (gui.html), dashboards and overviews.
// They do not stop the code as the browser's boxes do: await them.
//   await fhAlert(text)                      -> undefined
//   await fhConfirm(text, { ok, cancel })    -> true / false (Esc or Cancel: false)
//   await fhPrompt(text, value, { ok })      -> the text typed, or null
// The text is plain: blank lines separate paragraphs, lines that start with • or … (after spaces) are a list.
const fhDialog = (() => {
  let queue = Promise.resolve();  // one at a time: a second question waits for the first
  const html = (s) => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function body(text) {
    const out = []; let para = [], list = [];
    const endPara = () => { if (para.length) out.push(`<p>${para.map(html).join("<br>")}</p>`); para = []; };
    const endList = () => { if (list.length) out.push(`<ul>${list.map(l => `<li${l.more ? ' class="more"' : ""}>${html(l.t)}</li>`).join("")}</ul>`); list = []; };
    for (const line of String(text ?? "").split("\n")) {
      const m = line.match(/^\s*([•…])\s?(.*)$/);
      if (m) { endPara(); list.push(m[1] === "…" ? { t: "… " + m[2], more: true } : { t: m[2] }); }
      else if (!line.trim()) { endPara(); endList(); }
      else { endList(); para.push(line.trim()); }
    }
    endPara(); endList();
    return out.join("");
  }
  function show({ text, buttons, input = null }) {
    return new Promise((resolve) => {
      const icon = (document.querySelector('link[rel="icon"]') || {}).href;
      const d = document.createElement("dialog");
      d.className = "fh-dialog";
      d.innerHTML = `<div class="fh-dlg-head">${icon ? `<img src="${html(icon)}" alt="">` : ""}<span>FAST-HIPPOS</span></div>`
        + `<div class="fh-dlg-body">${body(text)}</div>`
        + (input !== null ? `<input class="fh-dlg-input" type="text" spellcheck="false">` : "")
        + `<div class="fh-dlg-btns">${buttons.map((b, i) => `<button type="button" data-i="${i}"${b.primary ? ' class="primary"' : ""}>${html(b.label)}</button>`).join("")}</div>`;
      const field = d.querySelector(".fh-dlg-input");
      if (field) field.value = input;
      let done = false;
      const finish = (v) => { if (done) return; done = true; d.close(); d.remove(); resolve(v); };
      const cancelValue = buttons.find(b => b.cancel)?.value;
      d.addEventListener("cancel", (e) => { e.preventDefault(); finish(cancelValue); });  // Esc
      d.querySelectorAll(".fh-dlg-btns button").forEach(b => b.onclick = () => {
        const btn = buttons[+b.dataset.i];
        finish(field && !btn.cancel ? field.value : btn.value);
      });
      if (field) field.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); finish(field.value); } });
      document.body.appendChild(d);
      d.showModal();
      if (field) { field.focus(); field.select(); }
      else (d.querySelector("button.primary") || d.querySelector("button")).focus();
    });
  }
  return (opts) => (queue = queue.then(() => show(opts), () => show(opts)));
})();
function fhAlert(text, { ok = "OK" } = {}) {
  return fhDialog({ text, buttons: [{ label: ok, value: undefined, primary: true, cancel: true }] });
}
function fhConfirm(text, { ok = "Continue", cancel = "Cancel" } = {}) {
  return fhDialog({ text, buttons: [{ label: cancel, value: false, cancel: true }, { label: ok, value: true, primary: true }] });
}
function fhPrompt(text, value = "", { ok = "OK", cancel = "Cancel" } = {}) {
  return fhDialog({ text, input: value, buttons: [{ label: cancel, value: null, cancel: true }, { label: ok, primary: true }] });
}
