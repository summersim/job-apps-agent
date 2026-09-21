const el = (id) => document.getElementById(id);
const STATUS_LABEL = {
  new: "New", shortlisted: "Shortlisted", drafted: "Drafted",
  approved: "Approved", submitted: "Submitted", rejected: "Rejected",
};
// Status transitions offered per current status, as [newStatus, buttonLabel].
// "submitted" only ever appears from "approved" — the server enforces this
// too, so it isn't just a UI nicety.
const TRANSITIONS = {
  new:         [["shortlisted", "Shortlist"], ["rejected", "Reject"]],
  shortlisted: [["new", "Back to New"], ["rejected", "Reject"]],
  drafted:     [["approved", "Approve"], ["new", "Back to New"], ["rejected", "Reject"]],
  approved:    [["submitted", "Mark as submitted"], ["drafted", "Back to Drafted"], ["rejected", "Reject"]],
  submitted:   [["approved", "Reopen"]],
  rejected:    [["new", "Reset to New"]],
};
const DRAFTABLE = new Set(["new", "shortlisted", "drafted"]);
const HAS_LETTER_BOX = new Set(["drafted", "approved", "submitted"]);

function setMessage(text, isErr) {
  const m = el("status-msg");
  m.textContent = text || "";
  m.classList.toggle("show", !!text);
  m.classList.toggle("err", !!isErr);
}

async function loadStats() {
  const res = await fetch("/api/stats");
  const stats = await res.json();
  el("stats").innerHTML = Object.keys(stats).sort().map(
    (k) => `<span class="pill"><b>${stats[k]}</b> ${k}</span>`
  ).join("") || `<span class="pill">no postings yet</span>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function card(row, rank) {
  const salary = row.salary_min
    ? `£${Math.round(row.salary_min).toLocaleString()}${row.salary_max ? "–£" + Math.round(row.salary_max).toLocaleString() : "+"}`
    : "not stated";
  const status = row.status;
  const transitions = (TRANSITIONS[status] || [])
    .map(([s, label]) => `<button data-key="${row.key}" data-status="${s}">${label}</button>`)
    .join("");
  const draftBtn = DRAFTABLE.has(status)
    ? `<button data-draft-key="${row.key}">${status === "drafted" ? "Redraft" : "Prepare application"}</button>`
    : "";
  const submitBtn = status === "approved"
    ? `<button data-submit-key="${row.key}" data-url="${escapeHtml(row.url)}" class="success">Submit application</button>`
    : "";
  const letterBlock = HAS_LETTER_BOX.has(status) ? `
        <details class="letter" ${status === "drafted" ? "open" : ""}>
          <summary>Cover letter</summary>
          <textarea data-letter-key="${row.key}" rows="10" class="${status === "drafted" ? "autoexpand" : ""}">${escapeHtml(row.letter || "")}</textarea>
          <div class="letter-actions">
            <button data-save-key="${row.key}">Save edits</button>
            <span class="saved" data-saved-for="${row.key}" hidden>Saved.</span>
          </div>
          <div class="feedback-row">
            <textarea data-feedback-key="${row.key}" rows="2" placeholder="What should change? e.g. &quot;shorten the second paragraph&quot; or &quot;lead with the clerkship instead&quot;"></textarea>
            <div class="letter-actions">
              <button data-redraft-key="${row.key}">Redraft with feedback</button>
            </div>
          </div>
        </details>` : "";
  return `
    <div class="card" data-row="${row.key}">
      <div class="rank">${rank}</div>
      <div class="body">
        <h3><a href="${row.url}" target="_blank" rel="noopener">${escapeHtml(row.title)}</a>
          <span class="status-badge status-${status}">${status}</span>
        </h3>
        <div class="meta">${escapeHtml(row.employer || "unknown employer")} · ${escapeHtml(row.location || "?")} · ${row.contract_type || "n/a"}</div>
        <div class="meta">${salary} · posted ${row.posted || "?"} · ${row.source}</div>${letterBlock}
      </div>
      <div class="actions">${draftBtn}${submitBtn}${transitions}</div>
    </div>`;
}

async function loadQueue() {
  const status = el("f-status").value;
  const limit = el("f-limit").value || 50;
  const location = el("f-location").value.trim();
  el("results").innerHTML = `<div class="empty">Loading…</div>`;
  const params = new URLSearchParams({ status, limit });
  if (location) params.set("location", location);
  const res = await fetch(`/api/queue?${params}`);
  const rows = await res.json();
  if (!rows.length) {
    el("results").innerHTML = `<div class="empty">No postings match this filter.</div>`;
    return;
  }
  el("results").innerHTML = rows.map((row, i) => card(row, i + 1)).join("");
  el("results").querySelectorAll("textarea.autoexpand").forEach(autoExpand);
}

function autoExpand(ta) {
  const max = Math.max(window.innerHeight - 220, 200);
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, max) + "px";
}

el("results").addEventListener("input", (ev) => {
  if (ev.target.matches("textarea.autoexpand")) autoExpand(ev.target);
});

el("results").addEventListener("click", async (ev) => {
  const statusBtn = ev.target.closest("button[data-key]");
  const draftBtn = ev.target.closest("button[data-draft-key]");
  const saveBtn = ev.target.closest("button[data-save-key]");
  const redraftBtn = ev.target.closest("button[data-redraft-key]");
  const submitBtn = ev.target.closest("button[data-submit-key]");

  if (statusBtn) {
    statusBtn.disabled = true;
    const res = await fetch("/api/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: statusBtn.dataset.key, status: statusBtn.dataset.status }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setMessage("");
      await Promise.all([loadQueue(), loadStats()]);
    } else {
      setMessage(data.error || "Could not update status.", true);
      statusBtn.disabled = false;
    }
    return;
  }

  if (draftBtn) {
    draftBtn.disabled = true;
    const key = draftBtn.dataset.draftKey;
    setMessage("Drafting a tailored cover letter…");
    const res = await fetch("/api/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setMessage("Draft ready — review the letter below.");
      await Promise.all([loadQueue(), loadStats()]);
    } else {
      setMessage(data.error || "Could not draft a letter.", true);
      draftBtn.disabled = false;
    }
    return;
  }

  if (redraftBtn) {
    const key = redraftBtn.dataset.redraftKey;
    const feedbackEl = document.querySelector(`textarea[data-feedback-key="${key}"]`);
    const feedback = feedbackEl.value.trim();
    if (!feedback) {
      setMessage("Add feedback before redrafting.", true);
      return;
    }
    redraftBtn.disabled = true;
    const letterEl = document.querySelector(`textarea[data-letter-key="${key}"]`);
    setMessage("Redrafting with your feedback…");
    const res = await fetch("/api/redraft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, feedback, letter: letterEl.value }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setMessage("Redraft ready — review the letter below.");
      await Promise.all([loadQueue(), loadStats()]);
    } else {
      setMessage(data.error || "Could not redraft the letter.", true);
      redraftBtn.disabled = false;
    }
    return;
  }

  if (submitBtn) {
    const key = submitBtn.dataset.submitKey;
    const url = submitBtn.dataset.url;
    const letterEl = document.querySelector(`textarea[data-letter-key="${key}"]`);
    const letter = letterEl ? letterEl.value : "";
    try {
      await navigator.clipboard.writeText(letter);
      setMessage("Cover letter copied to clipboard — paste it into the application form on the listing page that just opened.");
    } catch (e) {
      setMessage("Could not copy the letter automatically — opening the listing; copy it from the textarea above.", true);
    }
    window.open(url, "_blank", "noopener");
    return;
  }

  if (saveBtn) {
    saveBtn.disabled = true;
    const key = saveBtn.dataset.saveKey;
    const textarea = document.querySelector(`textarea[data-letter-key="${key}"]`);
    const res = await fetch("/api/letter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, letter: textarea.value }),
    });
    saveBtn.disabled = false;
    const savedTag = document.querySelector(`[data-saved-for="${key}"]`);
    if (res.ok) {
      savedTag.hidden = false;
      setTimeout(() => { savedTag.hidden = true; }, 2000);
    } else {
      setMessage("Could not save edits.", true);
    }
    return;
  }
});

el("btn-refresh").addEventListener("click", () => { setMessage(""); loadQueue(); loadStats(); });
el("f-location").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") { setMessage(""); loadQueue(); }
});
el("f-status").addEventListener("change", () => { setMessage(""); loadQueue(); });

el("btn-fetch").addEventListener("click", async () => {
  const btn = el("btn-fetch");
  btn.disabled = true;
  setMessage("Fetching from Reed and Adzuna — this can take a minute…");
  try {
    const res = await fetch("/api/fetch", { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      setMessage(data.error || "Fetch failed.", true);
    } else {
      const skipped = (data.warnings || []).length
        ? ` Skipped: ${data.warnings.join("; ")}.`
        : "";
      setMessage(`Fetched ${data.raw} raw postings, ${data.kept} passed filters — ${data.new} new, ${data.duplicates} duplicates suppressed.${skipped}`);
      await Promise.all([loadQueue(), loadStats()]);
    }
  } catch (e) {
    setMessage("Fetch failed: " + e, true);
  } finally {
    btn.disabled = false;
  }
});

loadStats();
loadQueue();
