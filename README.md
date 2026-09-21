# jobs-agent

Application pipeline for London legal and compliance roles: fetch, score,
deduplicate, draft, and stage into a review queue.

**Nothing here submits an application.** A human approves and submits.

## Setup

```bash
pip install -r requirements.txt

cp .env.example .env    # then fill it in, or export the keys directly
```

| Variable | Needed for | Where |
|---|---|---|
| `REED_API_KEY` | fetching | https://www.reed.co.uk/developers/jobseeker |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | fetching | https://developer.adzuna.com/ |
| `GEMINI_API_KEY` | drafting cover letters | https://aistudio.google.com/apikey |
| `JOBS_AGENT_GEMINI_MODEL` | optional model override | defaults to `gemini-3.6-flash` |

Both job-board API keys are free — Reed's is issued instantly, Adzuna's takes
a few minutes. Either board works on its own; a missing key skips that board
with a warning rather than failing.

```bash
python -m jobs_agent fetch
python -m jobs_agent queue --min-score 40
python -m jobs_agent stats
python -m jobs_agent serve       # web UI over all of the above
```

`.env` is read from the repository root, and the database defaults to
`data/jobs.db` there too, so the commands agree with each other no matter
which directory you run them from. Override the database with `--db`.

## Web UI

`python -m jobs_agent serve` opens a local review UI with two pages:

- **Job Queue** (`/`) — fetch, filter by status/score/location (defaults to
  "Central London" — clear the box for anywhere), and move postings through
  the review workflow below.
- **Profile** (`/documents`) — your name, your CV, an example cover letter,
  and the scoring profile.

Everything on the Profile page lives in the SQLite database: the CV as both
the original file (`files` table, re-downloadable from the page) and its
extracted text, the example letter and your name as text, and the scoring
profile as JSON (all in the `documents` table). Re-uploading or re-saving
overwrites in place; restarting the server keeps everything.

**Review workflow**, backed by the `applications.status` column:

```
new / shortlisted --[Prepare application]--> drafted --[Approve]--> approved --[Mark as submitted]--> submitted
```

"Prepare application" sends the posting plus your CV and example letter to
Gemini, which writes a complete cover letter tailored to that posting in your
voice. The result lands in `drafted`, editable in place, with a feedback box
that redrafts it. A posting can only be marked `submitted` once it is
`approved` — the server rejects the request otherwise. Nothing in this tool
ever calls a job board's apply endpoint; `submitted` just records that a
human did so elsewhere, so it drops out of the queue.

## Layout

```
jobs_agent/
  config.py       environment, paths, search keywords
  models.py       Posting and its deduplication keys
  profile.py      the scoring profile: dataclass, defaults, persistence
  scoring.py      deterministic relevance scoring
  pipeline.py     fetch -> score -> dedupe -> store, shared by CLI and web
  cli.py          argument parsing and console output only
  sources/        one module per job board, over a shared HTTP base
  storage/        schema.sql and the SQLite Store
  extract/        .docx / .pdf -> plain text
  letters/        drafting prompts, and the model call that runs them
  web/            server, route table, API endpoints, and static/ assets
tests/            run with: python -m pytest
data/jobs.db      the database (gitignored)
```

Two rules keep this navigable: `cli.py` and `web/` both depend on
`pipeline.py` and never on each other, and `web/api.py` endpoints are plain
functions of `(store, request)` so they can be tested without a socket.

## Design decisions worth arguing with

**APIs, not scraping.** Reed and Adzuna publish documented UK job APIs.
Scraping LinkedIn or Indeed would breach their terms, risk the account,
break on every layout change, and force regex parsing of salary out of HTML.
Between them these two APIs cover most agency-posted London contract listings.
LinkedIn stays a manual channel.

**Deterministic scoring, not an LLM.** Every score carries its reasons, so when
something irrelevant ranks high you can see which weight caused it and fix it
on the Profile page. That is not true of a model call, and at ingestion volume
the model calls would cost more than they're worth. Save the model for the
letters.

**Aggressive deduplication.** The same contract role is routinely posted by
four agencies under three titles. Identity is built from the normalised title,
location, and a fingerprint of the description body — agencies copy the body
verbatim, which is what makes this work. A looser title-plus-location key
catches reposts with lightly edited bodies.

**Exclusions are hard, not soft.** Seniority markers in the title and
experience requirements in the body drop a posting to score -1 and remove it.
Better to miss a stretch role than to bury the queue in things you can't get.

**Cover letters: full draft, human sign-off.** The model writes the whole
letter, tailored to the posting. It gets the CV as the only source of facts —
the prompt forbids inventing anything beyond it — and an example letter you
wrote yourself as the reference for voice, tone, and structure. Every draft is
read and edited in the queue before it can be `approved`; the letter is never
sent on the model's say-so.

**Approval is a hard gate, enforced server-side.** A posting can reach
`submitted` only by passing through `approved`; the API rejects the
transition otherwise, not just the UI.

## Known limitations

- Reed's and Adzuna's field names have changed before. Verify against their
  current docs on first run; each adapter is a single small module for that
  reason.
- Coverage excludes roles posted only on firm career pages or LinkedIn.
- `title_blockers` includes `counsel`, which will also drop legitimate
  "Legal Counsel Assistant" roles. Edit it on the Profile page if that
  segment matters.
- Freshness scoring assumes the posted date is real. Agencies repost stale
  roles with fresh dates; the dedupe catches most, not all.
- Editing the scoring profile affects the next fetch. Postings already in the
  queue keep the score they were stored with.
- The server binds to `127.0.0.1` and has no authentication — it is a local
  single-user tool, not something to expose.

## Next

Actual submission is still manual by design. A candidate next step is
per-site submission helpers (prefilling a Reed/Adzuna/firm application form),
each reviewed by a human before anything is sent.
