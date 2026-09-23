"""Postgres store. Deduplicates across sources and across runs."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

import psycopg
from psycopg import sql
from psycopg.rows import DictRow, dict_row

from ..config import database_url
from ..models import Posting

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Document ids used across the app. Kept here beside the schema comment that
# describes them, so adding one means touching a single place.
DOC_CV = "cv"
DOC_CV_FILENAME = "cv_filename"
DOC_TEMPLATE = "cover_letter_template"
DOC_CANDIDATE_NAME = "candidate_name"
DOC_SCORING_PROFILE = "scoring_profile"


class Store:
    def __init__(self, dsn: str | None = None, schema: str | None = None):
        """Connect to Postgres. ``schema`` isolates the tables under their
        own schema (rather than ``public``) instead of a separate database —
        used by tests to run in isolation against the same Supabase instance.
        """
        self.conn = psycopg.connect(dsn or database_url(), row_factory=dict_row)
        with self.conn.cursor() as cur:
            if schema:
                cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}")
                            .format(sql.Identifier(schema)))
                cur.execute(sql.SQL("SET search_path TO {}")
                            .format(sql.Identifier(schema)))
            for statement in SCHEMA_PATH.read_text().split(";"):
                statement = statement.strip()
                if statement:
                    cur.execute(statement)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- postings ---------------------------------------------------------

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
            if cur.execute("SELECT 1 FROM postings WHERE key=%s", (p.key,)).fetchone():
                dup += 1
                continue

            soft_hits = cur.execute(
                "SELECT description FROM postings WHERE soft_key=%s", (p.soft_key,)
            ).fetchall()
            if any(_overlap(p.description, row["description"]) > 0.75 for row in soft_hits):
                dup += 1
                continue

            cur.execute(
                """INSERT INTO postings
                   (key, soft_key, source, source_id, title, employer, location,
                    description, url, posted, salary_min, salary_max,
                    contract_type, via_agency, score, score_reasons, first_seen)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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
                "INSERT INTO applications (posting_key, status, updated) "
                "VALUES (%s, 'new', %s) ON CONFLICT (posting_key) DO NOTHING",
                (p.key, now),
            )
            new += 1

        self.conn.commit()
        return new, dup

    def queue(self, min_score: int = 0, limit: int = 50,
              status: str = "new", location: str | None = None) -> Iterator[DictRow]:
        query = """SELECT p.*, a.status, a.letter, a.notes, a.updated FROM postings p
                 JOIN applications a ON a.posting_key = p.key
                 WHERE a.status = %s AND p.score >= %s"""
        params: list = [status, min_score]
        if location:
            query += " AND p.location LIKE %s"
            params.append(f"%{location}%")
        query += " ORDER BY p.score DESC, p.first_seen DESC LIMIT %s"
        params.append(limit)
        yield from self.conn.execute(query, params)

    def get_posting(self, key: str) -> DictRow | None:
        return self.conn.execute(
            "SELECT * FROM postings WHERE key=%s", (key,)
        ).fetchone()

    def stats(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) c FROM applications GROUP BY status"
        ).fetchall()
        return {r["status"]: r["c"] for r in rows}

    # -- applications -----------------------------------------------------

    def get_application(self, key: str) -> DictRow | None:
        return self.conn.execute(
            "SELECT * FROM applications WHERE posting_key=%s", (key,)
        ).fetchone()

    def set_status(self, key: str, status: str, notes: str | None = None) -> None:
        self.conn.execute(
            "UPDATE applications SET status=%s, notes=COALESCE(%s, notes), updated=%s "
            "WHERE posting_key=%s",
            (status, notes, datetime.utcnow().isoformat(), key),
        )
        self.conn.commit()

    def set_letter(self, key: str, letter: str) -> None:
        """Save/edit the drafted letter text without touching status."""
        self.conn.execute(
            "UPDATE applications SET letter=%s, updated=%s WHERE posting_key=%s",
            (letter, datetime.utcnow().isoformat(), key),
        )
        self.conn.commit()

    # -- documents and files ----------------------------------------------

    def get_document(self, doc_id: str) -> str:
        row = self.conn.execute(
            "SELECT content FROM documents WHERE id=%s", (doc_id,)
        ).fetchone()
        return row["content"] if row else ""

    def set_document(self, doc_id: str, content: str) -> None:
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO documents (id, content, updated) VALUES (%s, %s, %s)
               ON CONFLICT(id) DO UPDATE SET content=excluded.content, updated=excluded.updated""",
            (doc_id, content, now),
        )
        self.conn.commit()

    def get_file(self, file_id: str) -> DictRow | None:
        return self.conn.execute(
            "SELECT id, filename, data, updated FROM files WHERE id=%s", (file_id,)
        ).fetchone()

    def set_file(self, file_id: str, filename: str, data: bytes) -> None:
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO files (id, filename, data, updated) VALUES (%s, %s, %s, %s)
               ON CONFLICT(id) DO UPDATE SET
                 filename=excluded.filename, data=excluded.data, updated=excluded.updated""",
            (file_id, filename, data, now),
        )
        self.conn.commit()


@contextmanager
def open_store(dsn: str | None = None, schema: str | None = None) -> Iterator[Store]:
    """``with open_store(dsn) as store:`` — closes on every exit path.

    The request handlers return early a dozen different ways; relying on each
    of them to remember ``store.close()`` was a connection leak waiting to
    happen.
    """
    store = Store(dsn, schema=schema)
    try:
        yield store
    finally:
        store.close()


def _overlap(a: str, b: str) -> float:
    """Jaccard overlap on word sets. Crude, cheap, good enough for reposts."""
    if not a or not b:
        return 0.0
    sa, sb = set(a.lower().split()), set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
