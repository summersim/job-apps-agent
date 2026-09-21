"""The fetch pipeline: pull, score, deduplicate, store.

The CLI's ``fetch`` command and the web UI's "Fetch new listings" button ran
separate copies of this sequence, which is how they drifted apart on the
default page size. Both now call :func:`fetch_and_store`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .config import KEYWORDS
from .profile import DEFAULT_PROFILE
from .scoring import score_all
from .sources import build_sources, gather_all
from .storage import Store


@dataclass
class FetchResult:
    raw: int          # postings returned by the boards
    kept: int         # survivors of scoring's hard exclusions
    new: int          # rows actually inserted
    duplicates: int   # suppressed as already known
    warnings: list[str]   # boards skipped for missing credentials

    @property
    def excluded(self) -> int:
        return self.raw - self.kept

    def as_dict(self) -> dict:
        return {
            "raw": self.raw, "kept": self.kept, "new": self.new,
            "duplicates": self.duplicates, "warnings": self.warnings,
        }


async def fetch_and_store(store: Store, *, per_keyword: int = 200,
                          keywords: list[str] | None = None) -> FetchResult:
    """Fetch every keyword from every configured board and stage the results.

    Raises :class:`~jobs_agent.sources.NoSourcesConfigured` when no board has
    credentials — callers decide whether that's an exit or an HTTP 400.
    """
    sources, warnings = build_sources()

    raw = await gather_all(sources, keywords or KEYWORDS, per_keyword=per_keyword)
    kept = score_all(raw, DEFAULT_PROFILE)
    new, dup = store.upsert(kept)

    return FetchResult(raw=len(raw), kept=len(kept), new=new,
                       duplicates=dup, warnings=warnings)


def fetch_and_store_sync(store: Store, *, per_keyword: int = 200,
                         keywords: list[str] | None = None) -> FetchResult:
    """Blocking wrapper, for the synchronous HTTP handler."""
    return asyncio.run(
        fetch_and_store(store, per_keyword=per_keyword, keywords=keywords)
    )
