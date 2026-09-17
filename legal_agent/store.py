"""SQLite store. Deduplicates across sources and across runs."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

from .models import Posting

SCHEMA = """
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

-- Candidate materials: CV text and an example cover letter (used as a voice
-- reference when drafting). One row per doc id ('cv', 'cv_filename',
-- 'cover_letter_template'). Small and few, so no history — UI overwrites in place.
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
"""


def default_db_path() -> str:
    """jobs.db in the project root (the package's parent directory).

    Anchored to the code, not the current working directory, so `serve` and
    `fetch` read and write the same database no matter where they're launched
    from. Override with --db.
    """
    return str(Path(__file__).resolve().parent.parent / "jobs.db")


class Store:
    def __init__(self, path: str | Path | None = None):
        self.conn = sqlite3.connect(str(path or default_db_path()))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert(self, postings: Iterable[Posting]) -> tuple[int, int]:
        """Insert postings not seen before.

        Returns (new, duplicate). A posting is a duplicate if its exact key is
        known, or if its soft_key is known AND the description overlaps enough
        that it is almost certainly the same role reposted.
        """
        new = dup = 0
        now = datetime.utcnow().isoformat()
        cur = self.conn.cursor()

        for p in postings:
            if cur.execute("SELECT 1 FROM postings WHERE key=?", (p.key,)).fetchone():
                dup += 1
                continue

            soft_hits = cur.execute(
                "SELECT description FROM postings WHERE soft_key=?", (p.soft_key,)
            ).fetchall()
            if any(_overlap(p.description, row["description"]) > 0.75 for row in soft_hits):
                dup += 1
                continue

            cur.execute(
                """INSERT INTO postings
                   (key, soft_key, source, source_id, title, employer, location,
                    description, url, posted, salary_min, salary_max,
                    contract_type, via_agency, score, score_reasons, first_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    p.key, p.soft_key, p.source, p.source_id, p.title, p.employer,
                    p.location, p.description, p.url,
                    p.posted.isoformat() if p.posted else None,
                    p.salary_min, p.salary_max, p.contract_type,
                    int(p.via_agency) if p.via_agency is not None else None,
                    p.score, " | ".join(p.score_reasons), now,
                ),
            )
            cur.execute(
                "INSERT OR IGNORE INTO applications (posting_key, status, updated) "
                "VALUES (?, 'new', ?)",
                (p.key, now),
            )
            new += 1

        self.conn.commit()
        return new, dup

    def queue(self, min_score: int = 0, limit: int = 50,
              status: str = "new", location: str | None = None) -> Iterator[sqlite3.Row]:
        sql = """SELECT p.*, a.status, a.letter, a.notes FROM postings p
                 JOIN applications a ON a.posting_key = p.key
                 WHERE a.status = ? AND p.score >= ?"""
        params: list = [status, min_score]
        if location:
            sql += " AND p.location LIKE ?"
            params.append(f"%{location}%")
        sql += " ORDER BY p.score DESC, p.first_seen DESC LIMIT ?"
        params.append(limit)
        yield from self.conn.execute(sql, params)

    def get_posting(self, key: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM postings WHERE key=?", (key,)
        ).fetchone()

    def get_application(self, key: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM applications WHERE posting_key=?", (key,)
        ).fetchone()

    def set_status(self, key: str, status: str, notes: str | None = None) -> None:
        self.conn.execute(
            "UPDATE applications SET status=?, notes=COALESCE(?, notes), updated=? "
            "WHERE posting_key=?",
            (status, notes, datetime.utcnow().isoformat(), key),
        )
        self.conn.commit()

    def set_letter(self, key: str, letter: str) -> None:
        """Save/edit the drafted letter text without touching status."""
        self.conn.execute(
            "UPDATE applications SET letter=?, updated=? WHERE posting_key=?",
            (letter, datetime.utcnow().isoformat(), key),
        )
        self.conn.commit()

    def stats(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) c FROM applications GROUP BY status"
        ).fetchall()
        return {r["status"]: r["c"] for r in rows}

    def get_document(self, doc_id: str) -> str:
        row = self.conn.execute(
            "SELECT content FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
        return row["content"] if row else ""

    def set_document(self, doc_id: str, content: str) -> None:
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO documents (id, content, updated) VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET content=excluded.content, updated=excluded.updated""",
            (doc_id, content, now),
        )
        self.conn.commit()

    def get_file(self, file_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT id, filename, data, updated FROM files WHERE id=?", (file_id,)
        ).fetchone()

    def set_file(self, file_id: str, filename: str, data: bytes) -> None:
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO files (id, filename, data, updated) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 filename=excluded.filename, data=excluded.data, updated=excluded.updated""",
            (file_id, filename, sqlite3.Binary(data), now),
        )
        self.conn.commit()


def _overlap(a: str, b: str) -> float:
    """Jaccard overlap on word sets. Crude, cheap, good enough for reposts."""
    if not a or not b:
        return 0.0
    sa, sb = set(a.lower().split()), set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
