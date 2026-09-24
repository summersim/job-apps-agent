import sys
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs_agent.models import Posting  # noqa: E402
from jobs_agent.storage import Store  # noqa: E402


@pytest.fixture
def store():
    """A Store isolated in its own throwaway Postgres schema, dropped after
    the test — tests share the Supabase instance used for dev/prod without
    stepping on each other's data. Scoped to a random user id, same as a
    real signed-in request would be.
    """
    schema = f"test_{uuid4().hex}"
    s = Store(user_id=str(uuid4()), schema=schema)
    yield s
    with s.conn.cursor() as cur:
        cur.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
    s.conn.commit()
    s.close()


def make_posting(**overrides) -> Posting:
    """A plausible posting; override whatever the test cares about."""
    fields = dict(
        source="reed",
        source_id="1",
        title="Compliance Analyst",
        employer="Example Bank Ltd",
        location="Central London",
        description="Sanctions screening and due diligence for a law graduate.",
        url="https://example.com/1",
    )
    fields.update(overrides)
    return Posting(**fields)
