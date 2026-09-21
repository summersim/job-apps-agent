"""Normalised posting model shared across sources."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

_WS = re.compile(r"\s+")
_NONWORD = re.compile(r"[^a-z0-9 ]")

# Agency boilerplate that appears in employer names and wrecks naive dedupe.
_EMPLOYER_NOISE = re.compile(
    r"\b(ltd|limited|llp|plc|recruitment|recruiting|resourcing|search|"
    r"selection|associates|group|consultancy|consulting|uk|international)\b"
)


def _norm(text: str) -> str:
    text = _NONWORD.sub(" ", (text or "").lower())
    return _WS.sub(" ", text).strip()


@dataclass
class Posting:
    source: str                  # "reed" | "adzuna"
    source_id: str               # id within that source
    title: str
    employer: str
    location: str
    description: str
    url: str
    posted: Optional[date] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    contract_type: Optional[str] = None   # "permanent" | "contract" | "temp" | None
    via_agency: Optional[bool] = None

    # populated by scoring
    score: int = 0
    score_reasons: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Stable identity for deduplication.

        The same role is routinely posted by four agencies under three job
        titles. Employer name is unreliable (agencies substitute their own),
        so identity is built from the normalised title, the location, and a
        fingerprint of the description body, which agencies copy verbatim.
        """
        title = _norm(self.title)
        employer = _EMPLOYER_NOISE.sub("", _norm(self.employer)).strip()
        loc = _norm(self.location)
        body = _norm(self.description)[:400]
        raw = f"{title}|{employer}|{loc}|{body}"
        return hashlib.sha1(raw.encode()).hexdigest()

    @property
    def soft_key(self) -> str:
        """Looser identity: catches the same role reposted with a tweaked body."""
        title = _norm(self.title)
        loc = _norm(self.location)
        return hashlib.sha1(f"{title}|{loc}".encode()).hexdigest()

    @property
    def salary_display(self) -> str:
        if self.salary_min and self.salary_max:
            return f"£{self.salary_min:,.0f}–£{self.salary_max:,.0f}"
        if self.salary_min:
            return f"£{self.salary_min:,.0f}+"
        return "not stated"


@dataclass
class Application:
    """Review-queue state for a posting. Nothing is ever auto-submitted."""

    posting_key: str
    status: str = "new"     # new | shortlisted | drafted | approved | submitted | rejected
    letter: Optional[str] = None
    notes: Optional[str] = None
    updated: datetime = field(default_factory=datetime.utcnow)
