const el = (id) => document.getElementById(id);

function bytesToBase64(bytes) {
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function showCvName(filename) {
  const span = el("cv-name");
  if (filename) {
    span.innerHTML = 'Stored: <a href="/api/cv/file">' + escapeHtml(filename) + "</a>";
  } else {
    span.textContent = "No CV uploaded yet.";
  }
}

function setMsg(id, text, isErr) {
  const m = el(id);
  m.textContent = text || "";
  m.className = isErr ? "err" : "";
}


async function load() {
  const res = await fetch("/api/documents");
  const data = await res.json();
  el("name").value = data.candidate_name || "";
  el("template").value = data.cover_letter_template || "";
  el("cv-preview").value = data.cv || "";
  showCvName(data.cv_filename);
}

el("cv-file").addEventListener("change", async () => {
  const file = el("cv-file").files[0];
  if (!file) return;
  const lower = file.name.toLowerCase();
  if (!(lower.endsWith(".docx") || lower.endsWith(".pdf"))) {
    setMsg("doc-msg", "Please choose a .docx or .pdf file.", true);
    return;
  }
  setMsg("doc-msg", "Reading " + file.name + "…");
  const bytes = new Uint8Array(await file.arrayBuffer());
  const res = await fetch("/api/cv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, data_b64: bytesToBase64(bytes) }),
  });
  const data = await res.json().catch(() => ({}));
  if (res.ok) {
    setMsg("doc-msg", "Uploaded " + data.filename + " — " + data.chars + " characters extracted, original file stored.");
    showCvName(data.filename);
    el("cv-preview").value = data.text;
  } else {
    setMsg("doc-msg", data.error || "Could not read that file.", true);
  }
  el("cv-file").value = "";
});

load();
