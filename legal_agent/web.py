"""Local web UI for the legal-agent CLI.

Two pages:

  /            job review queue — fetch, filter, shortlist/reject, and run
               the review-and-approve workflow below
  /documents   Profile page — candidate name, CV (uploaded as .docx or .pdf,
               text extracted), and cover-letter template, stored once and
               reused for every draft

Review workflow: "Prepare application" drafts a letter (fixed template +
one AI-generated hook paragraph tailored to that posting — see letters.py)
and sets the posting to "drafted". A human reads it, edits it if they want,
and clicks "Approve". Only once a posting is "approved" can it be marked
"submitted" — the server rejects any attempt to skip that step. Nothing in
this tool ever submits anything itself; "submitted" just records that a
human did so elsewhere, so it stops resurfacing in the queue.

Stdlib only (http.server) beyond what fetch/queue/stats already need.
Drafting additionally needs GEMINI_API_KEY set in the environment.

    python -m legal_agent.cli serve
    python -m legal_agent.cli serve --port 8080 --no-browser
"""

from __future__ import annotations

import asyncio
import base64
import json
import webbrowser
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .cli import KEYWORDS, build_sources
from .cv_extract import CvExtractError, extract_cv_text
from .letters import DraftError, draft_letter, redraft_letter
from .profile import NICOLE
from .scoring import score_all
from .sources import gather_all
from .store import Store

# Full application lifecycle. "approved" requires a non-empty letter;
# "submitted" requires the posting to already be "approved" — enforced in
# do_POST, not just hidden in the UI.
UI_STATUSES = ("new", "shortlisted", "drafted", "approved", "submitted", "rejected")

# The CV is uploaded as .docx or .pdf and its text extracted; cv_filename is
# kept only for display. cover_letter_template holds the candidate's own
# example letter (a voice/structure reference, not a skeleton), edited as
# plain text in the textarea.
CV_DOC_ID = "cv"
CV_FILENAME_DOC_ID = "cv_filename"
CV_EXTENSIONS = (".docx", ".pdf")
NAME_DOC_ID = "candidate_name"
TEXT_DOC_IDS = ("cover_letter_template", NAME_DOC_ID)

BASE_CSS = """
  :root {
    color-scheme: light;
    --bg: #f6f5f2; --panel: #ffffff; --border: #e2ded6; --text: #1f1c17;
    --muted: #6b655a; --accent: #8a1f11; --accent-ink: #ffffff;
    --new: #2f6f4f; --shortlisted: #a8710f; --rejected: #9a2f2f;
    --drafted: #6b4fa0; --approved: #1f6f6a; --submitted: #2f5a99;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .topnav {
    display: flex; align-items: center; gap: 18px; padding: 10px 28px;
    background: var(--text); color: #fff;
  }
  .topnav .brand { font-weight: 600; font-size: 13px; letter-spacing: .02em; margin-right: 8px; }
  .topnav a { color: #d9d5cb; text-decoration: none; font-size: 13px; }
  .topnav a:hover { color: #fff; }
  .topnav a.active { color: #fff; font-weight: 600; }
  header {
    padding: 24px 28px 8px; border-bottom: 1px solid var(--border);
    background: var(--panel);
  }
  h1 { margin: 0 0 2px; font-size: 20px; letter-spacing: -0.01em; }
  .sub { color: var(--muted); font-size: 13px; margin-bottom: 18px; }
  button {
    border: 1px solid var(--border); background: var(--panel); color: var(--text);
    border-radius: 6px; padding: 7px 14px; font-size: 13px; cursor: pointer;
  }
  button:hover { border-color: #c9c3b7; }
  button:disabled { opacity: .5; cursor: default; }
  button.primary { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
  button.primary:hover { opacity: .92; }
  button.success { background: #2f7a45; color: #fff; border-color: #2f7a45; }
  button.success:hover { opacity: .92; }
  #doc-msg { padding: 0 28px; font-size: 13px; color: var(--muted); min-height: 20px; }
  #doc-msg.err { color: var(--rejected); }
  #status-msg {
    display: none;
    padding: 12px 28px; font-size: 13px; line-height: 1.4;
    background: #e5ecf7; color: var(--submitted);
    border-left: 4px solid var(--submitted);
    border-bottom: 1px solid var(--border);
  }
  #status-msg.show { display: block; }
  #status-msg.err {
    background: #f8e6e6; color: var(--rejected);
    border-left-color: var(--rejected);
  }
"""

QUEUE_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Legal &amp; Compliance Job Queue</title>
<style>
__BASE_CSS__
  .stats { display: flex; gap: 8px; flex-wrap: wrap; padding-bottom: 16px; }
  .pill {
    border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px;
    font-size: 12px; color: var(--muted); background: var(--bg);
  }
  .pill b { color: var(--text); }

  .controls {
    display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap;
    padding: 16px 28px; background: var(--panel); border-bottom: 1px solid var(--border);
    position: sticky; top: 0; z-index: 5;
  }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .field label { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
  select, input[type=number], input[type=text] {
    border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px;
    font-size: 13px; background: var(--bg); color: var(--text);
  }
  button.spacer-left { margin-left: auto; }

  main { padding: 4px 28px 40px; max-width: 980px; margin: 0 auto; }
  .empty { color: var(--muted); padding: 40px 0; text-align: center; }

  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 16px; margin: 12px 0; display: flex; gap: 14px; align-items: flex-start;
  }
  .score {
    flex: 0 0 auto; width: 42px; height: 42px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 600; font-size: 14px; background: var(--bg); border: 1px solid var(--border);
  }
  .body { flex: 1; min-width: 0; }
  .body h3 { margin: 0 0 2px; font-size: 15px; }
  .body h3 a { color: var(--text); text-decoration: none; }
  .body h3 a:hover { text-decoration: underline; }
  .meta { color: var(--muted); font-size: 12.5px; margin-bottom: 4px; }
  .reasons { color: var(--muted); font-size: 12px; margin-top: 6px; }
  .status-badge {
    font-size: 11px; text-transform: uppercase; letter-spacing: .03em;
    padding: 2px 8px; border-radius: 999px; margin-left: 8px; vertical-align: middle;
  }
  .status-new { background: #e8f3ec; color: var(--new); }
  .status-shortlisted { background: #fbeed7; color: var(--shortlisted); }
  .status-rejected { background: #f8e6e6; color: var(--rejected); }
  .status-drafted { background: #ece7f5; color: var(--drafted); }
  .status-approved { background: #e2f2f0; color: var(--approved); }
  .status-submitted { background: #e5ecf7; color: var(--submitted); }

  .actions { flex: 0 0 auto; display: flex; flex-direction: column; gap: 6px; width: 150px; }
  .actions button { white-space: nowrap; }

  .letter { margin-top: 10px; border-top: 1px dashed var(--border); padding-top: 10px; }
  .letter summary { cursor: pointer; font-size: 11px; text-transform: uppercase;
    letter-spacing: .04em; color: var(--muted); margin-bottom: 6px; }
  .letter textarea {
    width: 100%; border: 1px solid var(--border); border-radius: 8px; padding: 10px;
    font: 13px/1.5 -apple-system, BlinkMacSystemFont, sans-serif;
    resize: vertical; background: var(--bg); color: var(--text);
  }
  .letter textarea.autoexpand {
    overflow-y: hidden; resize: none; min-height: 120px;
  }
  .letter-actions { margin-top: 8px; display: flex; gap: 8px; align-items: center; }
  .letter-actions .saved { font-size: 12px; color: var(--approved); }
  .feedback-row { margin-top: 12px; border-top: 1px dashed var(--border); padding-top: 10px; }
  .feedback-row textarea {
    width: 100%; border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
    font: 13px/1.4 -apple-system, BlinkMacSystemFont, sans-serif;
    resize: vertical; background: var(--bg); color: var(--text);
  }
  .feedback-row .letter-actions { margin-top: 6px; }
</style>
</head>
<body>
<!--NAV-->
<header>
  <h1>Legal &amp; Compliance Job Queue</h1>
  <div class="sub">Ranked review queue for <!--CANDIDATE_NAME-->. Each letter is AI-drafted from your CV and example letter, then read and approved by you — nothing here is submitted automatically.</div>
  <div class="stats" id="stats"></div>
</header>

<div class="controls">
  <div class="field">
    <label for="f-status">Status</label>
    <select id="f-status">
      <option value="new">new</option>
      <option value="shortlisted">shortlisted</option>
      <option value="drafted">drafted</option>
      <option value="approved">approved</option>
      <option value="submitted">submitted</option>
      <option value="rejected">rejected</option>
    </select>
  </div>
  <div class="field">
    <label for="f-score">Min score</label>
    <input id="f-score" type="number" value="30" step="1" style="width:70px">
  </div>
  <div class="field">
    <label for="f-limit">Limit</label>
    <input id="f-limit" type="number" value="50" step="1" style="width:70px">
  </div>
  <div class="field">
    <label for="f-location">Location</label>
    <input id="f-location" type="text" value="Central London" placeholder="e.g. London" style="width:140px">
  </div>
  <button id="btn-refresh">Refresh queue</button>
  <button id="btn-fetch" class="primary spacer-left">Fetch new listings</button>
</div>

<div id="status-msg"></div>

<main id="results"><div class="empty">Loading…</div></main>

<script>
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

function card(row) {
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
      <div class="score">${row.score}</div>
      <div class="body">
        <h3><a href="${row.url}" target="_blank" rel="noopener">${escapeHtml(row.title)}</a>
          <span class="status-badge status-${status}">${status}</span>
        </h3>
        <div class="meta">${escapeHtml(row.employer || "unknown employer")} · ${escapeHtml(row.location || "?")} · ${row.contract_type || "n/a"}</div>
        <div class="meta">${salary} · posted ${row.posted || "?"} · ${row.source}</div>
        <div class="reasons">${escapeHtml(row.score_reasons || "")}</div>${letterBlock}
      </div>
      <div class="actions">${draftBtn}${submitBtn}${transitions}</div>
    </div>`;
}

async function loadQueue() {
  const status = el("f-status").value;
  const minScore = el("f-score").value || 0;
  const limit = el("f-limit").value || 50;
  const location = el("f-location").value.trim();
  el("results").innerHTML = `<div class="empty">Loading…</div>`;
  const params = new URLSearchParams({ status, min_score: minScore, limit });
  if (location) params.set("location", location);
  const res = await fetch(`/api/queue?${params}`);
  const rows = await res.json();
  if (!rows.length) {
    el("results").innerHTML = `<div class="empty">No postings match this filter.</div>`;
    return;
  }
  el("results").innerHTML = rows.map(card).join("");
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
      setMessage(`Fetched ${data.raw} raw postings, ${data.kept} passed filters — ${data.new} new, ${data.duplicates} duplicates suppressed.`);
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
</script>
</body>
</html>
""".replace("__BASE_CSS__", BASE_CSS)

DOCS_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Profile</title>
<style>
__BASE_CSS__
  main { padding: 20px 28px 60px; max-width: 780px; margin: 0 auto; }
  .doc-label { display: block; font-size: 12px; text-transform: uppercase;
    letter-spacing: .04em; color: var(--muted); margin: 22px 0 6px; }
  .hint { font-size: 12.5px; color: var(--muted); margin-bottom: 8px; }
  .hint code { background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 1px 5px; }
  textarea {
    width: 100%; border: 1px solid var(--border); border-radius: 8px; padding: 12px;
    font: 13.5px/1.5 -apple-system, BlinkMacSystemFont, sans-serif;
    resize: vertical; background: var(--panel); color: var(--text);
  }
  input#name {
    width: 100%; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px;
    font: 13.5px/1.5 -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--panel); color: var(--text);
  }
  .cv-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .cv-name { font-size: 12.5px; color: var(--muted); }
  details.cv-preview { margin-top: 10px; }
  details.cv-preview summary { cursor: pointer; font-size: 11px; text-transform: uppercase;
    letter-spacing: .04em; color: var(--muted); margin-bottom: 6px; }
  #cv-preview {
    background: var(--bg); color: var(--muted);
    font: 12px/1.5 ui-monospace, Menlo, Consolas, monospace;
  }
  .save-row { margin-top: 18px; display: flex; align-items: center; gap: 12px; }
</style>
</head>
<body>
<!--NAV-->
<header>
  <h1>Profile</h1>
  <div class="sub">Stored once, reused for every drafted application. Changes here affect future drafts only — letters already drafted keep what they were drafted with until you redraft them.</div>
</header>
<main>
  <label class="doc-label" for="name">Your name</label>
  <div class="hint">Shown on the Job Queue page and used to personalize this workspace.</div>
  <input id="name" type="text" placeholder="e.g. Jane Smith">

  <label class="doc-label" for="cv-file">CV</label>
  <div class="hint">Upload your CV as a <code>.docx</code> or <code>.pdf</code> file. The original file is stored in the database and its text is extracted for drafting; formatting and layout are dropped from the text.</div>
  <div class="cv-row">
    <input id="cv-file" type="file" accept=".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document">
    <span id="cv-name" class="cv-name"></span>
  </div>
  <details class="cv-preview">
    <summary>Extracted text</summary>
    <textarea id="cv-preview" rows="14" readonly placeholder="No CV uploaded yet."></textarea>
  </details>

  <label class="doc-label" for="template">Example cover letter</label>
  <div class="hint">Paste a cover letter you wrote yourself. It is <em>not</em> sent as-is — the drafter reads it to learn your voice, tone, and structure, then writes a fresh letter tailored to each job.</div>
  <textarea id="template" rows="16" placeholder="Dear Hiring Manager,&#10;&#10;I am writing to apply for…&#10;&#10;Kind regards,&#10;Jane"></textarea>

  <div class="save-row">
    <button id="btn-save" class="primary">Save profile</button>
    <span id="doc-msg"></span>
  </div>
</main>
<script>
const el = (id) => document.getElementById(id);

function bytesToBase64(bytes) {
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

function showCvName(filename) {
  const span = el("cv-name");
  if (filename) {
    span.innerHTML = 'Stored: <a href="/api/cv/file">' + escapeHtml(filename) + "</a>";
  } else {
    span.textContent = "No CV uploaded yet.";
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
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
  const msg = el("doc-msg");
  const lower = file.name.toLowerCase();
  if (!(lower.endsWith(".docx") || lower.endsWith(".pdf"))) {
    msg.textContent = "Please choose a .docx or .pdf file.";
    msg.className = "err";
    return;
  }
  msg.textContent = "Reading " + file.name + "…";
  msg.className = "";
  const bytes = new Uint8Array(await file.arrayBuffer());
  const res = await fetch("/api/cv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, data_b64: bytesToBase64(bytes) }),
  });
  const data = await res.json().catch(() => ({}));
  if (res.ok) {
    msg.textContent = "Uploaded " + data.filename + " — " + data.chars + " characters extracted, original file stored.";
    msg.className = "";
    showCvName(data.filename);
    el("cv-preview").value = data.text;
  } else {
    msg.textContent = data.error || "Could not read that file.";
    msg.className = "err";
  }
  el("cv-file").value = "";
});

el("btn-save").addEventListener("click", async () => {
  const btn = el("btn-save");
  const msg = el("doc-msg");
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
      msg.textContent = "Saved.";
      msg.className = "";
    } else {
      msg.textContent = "Could not save.";
      msg.className = "err";
    }
  } finally {
    btn.disabled = false;
  }
});

load();
</script>
</body>
</html>
""".replace("__BASE_CSS__", BASE_CSS)


def _nav(active: str) -> str:
    def cls(name: str) -> str:
        return ' class="active"' if name == active else ""
    return (
        '<nav class="topnav">'
        '<span class="brand">Legal Agent</span>'
        f'<a href="/"{cls("queue")}>Job Queue</a>'
        f'<a href="/documents"{cls("documents")}>Profile</a>'
        '</nav>'
    )


def _row_to_dict(row) -> dict:
    return {k: row[k] for k in row.keys()}


class Handler(BaseHTTPRequestHandler):
    db_path = "jobs.db"

    def log_message(self, fmt, *args) -> None:  # quiet the default access log
        pass

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        parsed = urlparse(self.path)

        if parsed.path == "/":
            store = Store(self.db_path)
            candidate_name = store.get_document(NAME_DOC_ID).strip() or NICOLE.name
            store.close()
            page = QUEUE_PAGE.replace("<!--NAV-->", _nav("queue"))
            page = page.replace("<!--CANDIDATE_NAME-->", html_escape(candidate_name))
            self._send_html(page)
            return

        if parsed.path == "/documents":
            self._send_html(DOCS_PAGE.replace("<!--NAV-->", _nav("documents")))
            return

        if parsed.path == "/api/cv/file":
            store = Store(self.db_path)
            row = store.get_file(CV_DOC_ID)
            store.close()
            if not row:
                self._send_json({"error": "no CV on file"}, 404)
                return
            ext = row["filename"].lower().rsplit(".", 1)[-1]
            ctype = ("application/pdf" if ext == "pdf" else
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                     if ext == "docx" else "application/octet-stream")
            self._send_bytes(row["data"], ctype, row["filename"])
            return

        if parsed.path == "/api/stats":
            store = Store(self.db_path)
            stats = store.stats()
            store.close()
            self._send_json(stats)
            return

        if parsed.path == "/api/queue":
            qs = parse_qs(parsed.query)
            status = qs.get("status", ["new"])[0]
            min_score = int(qs.get("min_score", ["0"])[0])
            limit = int(qs.get("limit", ["50"])[0])
            location = qs.get("location", [""])[0].strip() or None
            store = Store(self.db_path)
            rows = list(store.queue(min_score=min_score, limit=limit,
                                     status=status, location=location))
            store.close()
            self._send_json([_row_to_dict(r) for r in rows])
            return

        if parsed.path == "/api/documents":
            store = Store(self.db_path)
            docs = {
                "candidate_name": store.get_document(NAME_DOC_ID),
                "cv": store.get_document(CV_DOC_ID),
                "cv_filename": store.get_document(CV_FILENAME_DOC_ID),
                "cover_letter_template": store.get_document("cover_letter_template"),
            }
            store.close()
            self._send_json(docs)
            return

        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}

        if parsed.path == "/api/fetch":
            try:
                sources = build_sources()
            except SystemExit as e:
                self._send_json({"error": str(e)}, 400)
                return
            per_keyword = int(payload.get("per_keyword", 100))
            raw_postings = asyncio.run(
                gather_all(sources, KEYWORDS, per_keyword=per_keyword)
            )
            kept = score_all(raw_postings, NICOLE)
            store = Store(self.db_path)
            new, dup = store.upsert(kept)
            store.close()
            self._send_json({
                "raw": len(raw_postings), "kept": len(kept),
                "new": new, "duplicates": dup,
            })
            return

        if parsed.path == "/api/status":
            key, status = payload.get("key"), payload.get("status")
            if not key or status not in UI_STATUSES:
                self._send_json({"error": "bad key or status"}, 400)
                return
            store = Store(self.db_path)
            app_row = store.get_application(key)
            if not app_row:
                store.close()
                self._send_json({"error": "unknown posting"}, 404)
                return
            if status == "approved" and not (app_row["letter"] or "").strip():
                store.close()
                self._send_json(
                    {"error": "Prepare the application (draft a letter) before approving."}, 400
                )
                return
            if status == "submitted" and app_row["status"] != "approved":
                store.close()
                self._send_json(
                    {"error": "Approve the application before marking it submitted."}, 400
                )
                return
            store.set_status(key, status)
            store.close()
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/draft":
            key = payload.get("key")
            if not key:
                self._send_json({"error": "missing key"}, 400)
                return
            store = Store(self.db_path)
            posting = store.get_posting(key)
            if not posting:
                store.close()
                self._send_json({"error": "unknown posting"}, 404)
                return
            cv = store.get_document("cv")
            template = store.get_document("cover_letter_template")
            if not cv.strip() or not template.strip():
                store.close()
                self._send_json({
                    "error": "Add your CV and an example cover letter on the "
                             "Profile page first."
                }, 400)
                return
            try:
                letter = draft_letter(
                    title=posting["title"], employer=posting["employer"],
                    location=posting["location"], description=posting["description"],
                    cv=cv, template=template,
                )
            except DraftError as e:
                store.close()
                self._send_json({"error": str(e)}, 400)
                return
            store.set_letter(key, letter)
            store.set_status(key, "drafted")
            store.close()
            self._send_json({"ok": True, "letter": letter})
            return

        if parsed.path == "/api/redraft":
            key = payload.get("key")
            feedback = (payload.get("feedback") or "").strip()
            if not key or not feedback:
                self._send_json({"error": "missing key or feedback"}, 400)
                return
            store = Store(self.db_path)
            posting = store.get_posting(key)
            app_row = store.get_application(key)
            if not posting or not app_row:
                store.close()
                self._send_json({"error": "unknown posting"}, 404)
                return
            previous_letter = payload.get("letter")
            if previous_letter is None:
                previous_letter = app_row["letter"] or ""
            if not previous_letter.strip():
                store.close()
                self._send_json(
                    {"error": "Prepare the application (draft a letter) before redrafting with feedback."}, 400
                )
                return
            cv = store.get_document("cv")
            if not cv.strip():
                store.close()
                self._send_json({
                    "error": "Add your CV on the Profile page first."
                }, 400)
                return
            try:
                letter = redraft_letter(
                    title=posting["title"], employer=posting["employer"],
                    location=posting["location"], description=posting["description"],
                    cv=cv, previous_letter=previous_letter, feedback=feedback,
                )
            except DraftError as e:
                store.close()
                self._send_json({"error": str(e)}, 400)
                return
            store.set_letter(key, letter)
            store.close()
            self._send_json({"ok": True, "letter": letter})
            return

        if parsed.path == "/api/letter":
            key, letter = payload.get("key"), payload.get("letter")
            if not key or letter is None:
                self._send_json({"error": "missing key or letter"}, 400)
                return
            store = Store(self.db_path)
            if not store.get_application(key):
                store.close()
                self._send_json({"error": "unknown posting"}, 404)
                return
            store.set_letter(key, letter)
            store.close()
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/cv":
            filename = (payload.get("filename") or "cv").strip()
            if not filename.lower().endswith(CV_EXTENSIONS):
                self._send_json({"error": "Upload a .docx or .pdf file."}, 400)
                return
            try:
                blob = base64.b64decode(payload.get("data_b64") or "", validate=True)
            except (ValueError, TypeError):
                self._send_json({"error": "could not decode the upload"}, 400)
                return
            try:
                text = extract_cv_text(filename, blob)
            except CvExtractError as e:
                self._send_json({"error": f"Could not read that file: {e}"}, 400)
                return
            if not text.strip():
                self._send_json({
                    "error": "No readable text found — if this is a scanned "
                             "or image-only CV, upload a text-based version."
                }, 400)
                return
            store = Store(self.db_path)
            store.set_file(CV_DOC_ID, filename, blob)   # the original document
            store.set_document(CV_DOC_ID, text)         # cached extracted text
            store.set_document(CV_FILENAME_DOC_ID, filename)
            store.close()
            self._send_json({"ok": True, "filename": filename,
                             "chars": len(text), "text": text})
            return

        if parsed.path == "/api/documents":
            store = Store(self.db_path)
            for doc_id in TEXT_DOC_IDS:
                if doc_id in payload:
                    store.set_document(doc_id, payload[doc_id])
            store.close()
            self._send_json({"ok": True})
            return

        self._send_json({"error": "not found"}, 404)


def serve(db_path: str | None = None, port: int = 8765, open_browser: bool = True) -> None:
    from .store import default_db_path

    db_path = db_path or default_db_path()
    Handler.db_path = db_path
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Serving the job queue UI on {url}  (Ctrl+C to stop)", flush=True)
    print(f"Database: {db_path}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
