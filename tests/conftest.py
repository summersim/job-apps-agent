import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs_agent.models import Posting  # noqa: E402
from jobs_agent.storage import Store  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
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
