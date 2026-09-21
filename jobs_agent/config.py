"""Shared configuration: environment, paths, and search terms.

Everything here is imported by both the CLI and the web server, so neither
has to import the other. Nothing in this module imports from the rest of the
package — it sits at the bottom of the dependency graph.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Repository root — the package's parent directory. Paths are anchored to
#: the code rather than the current working directory so `fetch` and `serve`
#: agree on where the database lives no matter where they're launched from.
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"


def gemini_model() -> str:
    """Model used for drafting. Flash handles a one-page letter well and keeps
    the per-application cost negligible; override with JOBS_AGENT_GEMINI_MODEL.

    Read on each call rather than at import time, so it picks up whatever
    ``load_dotenv`` put in the environment regardless of import order.
    """
    return os.getenv("JOBS_AGENT_GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


#: Search terms fanned out across every configured job board.
KEYWORDS = [
    "compliance analyst",
    "compliance officer",
    "financial crime analyst",
    "AML analyst",
    "KYC analyst",
    "regulatory compliance",
    "client onboarding analyst",
    "paralegal",
    "legal assistant",
    "legal analyst",
    "graduate compliance",
]


def default_db_path() -> str:
    """``data/jobs.db`` in the repository root. Override with ``--db``.

    Creating the directory is :class:`~jobs_agent.storage.Store`'s job, so
    that merely asking for the path (``--help``) touches nothing on disk.
    """
    return str(DATA_DIR / "jobs.db")


def load_dotenv(path: str | Path | None = None) -> None:
    """Read KEY=VALUE lines from a .env file into ``os.environ``.

    Minimal on purpose — no python-dotenv dependency. Handles comments, blank
    lines, an optional leading ``export``, and single/double-quoted values.
    Anything it can't parse is skipped silently. Real environment variables
    always win, so exporting a key overrides the file.
    """
    p = Path(path) if path is not None else ROOT / ".env"
    if not p.is_file():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)
