const el = (id) => document.getElementById(id);

// Scoring-profile textareas, keyed by the field name the API expects.
const PROFILE_FIELDS = {
  target_titles: "target-titles",
  domain_terms: "domain-terms",
  title_blockers: "title-blockers",
  experience_blockers: "experience-blockers",
};

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

function fillProfile(profile) {
  for (const [field, elementId] of Object.entries(PROFILE_FIELDS)) {
    el(elementId).value = profile[field] || "";
  }
}

function readProfile() {
  const out = {};
  for (const [field, elementId] of Object.entries(PROFILE_FIELDS)) {
    out[field] = el(elementId).value;
  }
  return out;
}

async function load() {
  const [docsRes, profileRes] = await Promise.all([
    fetch("/api/documents"),
    fetch("/api/profile"),
  ]);
  const data = await docsRes.json();
  el("name").value = data.candidate_name || "";
  el("template").value = data.cover_letter_template || "";
  el("cv-preview").value = data.cv || "";
  showCvName(data.cv_filename);
  fillProfile(await profileRes.json());
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

el("btn-save").addEventListener("click", async () => {
  const btn = el("btn-save");
  btn.disabled = true;
  try {
    const res = await fetch("/api/documents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        candidate_name: el("name").value,
        cover_letter_template: el("template").value,
      }),
    });
    if (res.ok) {
      setMsg("doc-msg", "Saved.");
    } else {
      setMsg("doc-msg", "Could not save.", true);
    }
  } finally {
    btn.disabled = false;
  }
});

el("btn-save-profile").addEventListener("click", async () => {
  const btn = el("btn-save-profile");
  btn.disabled = true;
  setMsg("profile-msg", "Saving…");
  try {
    const res = await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readProfile()),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      // The server echoes the reformatted profile, so what you see is
      // exactly what was stored — including terms it normalised.
      fillProfile(data.profile);
      setMsg("profile-msg", "Saved.");
    } else {
      setMsg("profile-msg", data.error || "Could not save the scoring profile.", true);
    }
  } finally {
    btn.disabled = false;
  }
});

el("btn-reset-profile").addEventListener("click", async () => {
  if (!confirm("Discard your scoring profile and restore the defaults?")) return;
  const btn = el("btn-reset-profile");
  btn.disabled = true;
  try {
    const res = await fetch("/api/profile/reset", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      fillProfile(data.profile);
      setMsg("profile-msg", "Restored the defaults.");
    } else {
      setMsg("profile-msg", data.error || "Could not reset.", true);
    }
  } finally {
    btn.disabled = false;
  }
});

load();
