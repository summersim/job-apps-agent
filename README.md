# legal-apply-agent

Application pipeline for London legal and compliance roles. Ingestion core only
at this stage — cover letters come next.

**Nothing here submits an application.** It fetches, deduplicates, scores, and
stages roles into a review queue. A human approves and submits.

## Setup

```bash
pip install -r requirements.txt

export REED_API_KEY=...          # https://www.reed.co.uk/developers/jobseeker
export ADZUNA_APP_ID=...         # https://developer.adzuna.com/
export ADZUNA_APP_KEY=...
export GEMINI_API_KEY=...        # only needed for drafting cover letters

python -m legal_agent.cli fetch
python -m legal_agent.cli queue --min-score 40
python -m legal_agent.cli stats
python -m legal_agent.cli serve  # web UI over all of the above
```

Both job-board API keys are free. Reed's is issued instantly; Adzuna's takes a
few minutes.

## Web UI

`python -m legal_agent.cli serve` opens a local review UI with two pages:

- **Job Queue** (`/`) — fetch, filter by status/score/location (defaults to
  "Central London" — clear the box for anywhere), and move postings through
  the review workflow below.
- **CV & Cover Letter** (`/documents`) — upload your CV as a `.docx` or `.pdf`
  (text is extracted on upload; a scanned/image-only PDF won't work) and paste
  an example cover letter you wrote yourself. The drafter reads the example to
  match your voice and structure when it writes a fresh letter per application.

  All of it lives in the SQLite database (`jobs.db` in the project root, or
  `--db`): the CV as both the original file (`files` table, re-downloadable
  from the page) and its extracted text, and the example letter as text
  (`documents` table). Re-uploading or re-saving overwrites in place;
  restarting the server keeps everything.

**Review workflow**, backed by the `applications.status` column:

```
new / shortlisted --[Prepare application]--> drafted --[Approve]--> approved --[Mark as submitted]--> submitted
```

"Prepare application" sends the posting plus your CV and example letter to
Gemini, which writes a complete cover letter tailored to that posting in your
voice (see "Design decisions" below). The result lands in `drafted`, editable
in place. A posting can only be marked `submitted` once it is `approved` —
the server rejects the request otherwise. Nothing in this tool ever calls a
job board's apply endpoint; `submitted` just records that a human did so
elsewhere, so it drops out of the queue.

## Design decisions worth arguing with

**APIs, not scraping.** Reed and Adzuna publish documented UK job APIs.
Scraping LinkedIn or Indeed would breach their terms, risk Nicole's account,
break on every layout change, and force regex parsing of salary out of HTML.
Between them these two APIs cover most agency-posted London contract listings.
LinkedIn stays a manual channel.

**Deterministic scoring, not an LLM.** Every score carries its reasons, so when
something irrelevant ranks high you can see which weight caused it and fix it.
That is not true of a model call, and at ingestion volume the model calls would
cost more than they're worth. Save the model for the letters.

**Aggressive deduplication.** The same contract role is routinely posted by
four agencies under three titles. Identity is built from the normalised title,
location, and a fingerprint of the description body — agencies copy the body
verbatim, which is what makes this work. A looser title-plus-location key
catches reposts with lightly edited bodies.

**Exclusions are hard, not soft.** Seniority markers in the title and
experience requirements in the body drop a posting to score -1 and remove it.
Better to miss a stretch role than to bury the queue in things she can't get.

**Cover letters: full draft, human sign-off.** For each application the model
writes the whole letter, tailored to the posting. It is given Nicole's CV as
the only source of facts — the prompt forbids inventing anything beyond it —
and an example letter she wrote herself as the reference for voice, tone, and
structure. This is a real generation step, so every draft is read and edited
in the queue before it can be `approved`; the letter is never sent on the
model's say-so.

**Approval is a hard gate, enforced server-side.** A posting can reach
`submitted` only by passing through `approved` first; the API rejects the
transition otherwise, not just the UI. Submission itself still isn't
automated — see "Nothing here submits an application" above.

## Known limitations

- Reed's and Adzuna's field names have changed before. Verify against their
  current docs on first run; the adapters are small and isolated for that reason.
- Coverage excludes roles posted only on firm career pages or LinkedIn.
- `title_blockers` includes `counsel`, which will also drop legitimate
  "Legal Counsel Assistant" roles. Tighten it if that segment matters.
- Freshness scoring assumes the posted date is real. Agencies repost stale
  roles with fresh dates; the dedupe catches most, not all.

## Next

Actual submission is still manual by design — see "Nothing here submits an
application" above. A candidate next step is per-site submission helpers
(prefilling a Reed/Adzuna/firm application form), each reviewed by a human
before anything is sent.
