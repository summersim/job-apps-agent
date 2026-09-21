CREATE TABLE IF NOT EXISTS postings (
    key           TEXT PRIMARY KEY,
    soft_key      TEXT NOT NULL,
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    title         TEXT NOT NULL,
    employer      TEXT,
    location      TEXT,
    description   TEXT,
    url           TEXT,
    posted        TEXT,
    salary_min    REAL,
    salary_max    REAL,
    contract_type TEXT,
    via_agency    INTEGER,
    score         INTEGER DEFAULT 0,
    score_reasons TEXT,
    first_seen    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_postings_soft ON postings(soft_key);
CREATE INDEX IF NOT EXISTS idx_postings_score ON postings(score DESC);

CREATE TABLE IF NOT EXISTS applications (
    posting_key TEXT PRIMARY KEY REFERENCES postings(key),
    status      TEXT NOT NULL DEFAULT 'new',
    letter      TEXT,
    notes       TEXT,
    updated     TEXT NOT NULL
);

-- Candidate materials and settings, one row per document id: 'cv' (extracted
-- text), 'cv_filename', 'cover_letter_template', 'candidate_name', and
-- 'scoring_profile' (the JSON-encoded Profile). Small and few, so no history
-- — the UI overwrites in place.
CREATE TABLE IF NOT EXISTS documents (
    id      TEXT PRIMARY KEY,
    content TEXT NOT NULL DEFAULT '',
    updated TEXT NOT NULL
);

-- The original uploaded CV file, kept verbatim so the document itself
-- persists (re-downloadable, re-extractable), not just the text pulled from
-- it. One row, id 'cv'.
CREATE TABLE IF NOT EXISTS files (
    id       TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    data     BLOB NOT NULL,
    updated  TEXT NOT NULL
);
