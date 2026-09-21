"""Candidate scoring profile.

Single source of truth for what counts as a good match. Scoring reads from
here; nothing else should carry candidate facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Profile:
    name: str
    location: str

    # Titles we actively want, strongest signal first. Matched case-insensitively
    # as substrings against the job title.
    target_titles: dict[str, int] = field(default_factory=dict)

    # Domain vocabulary. Matched against title + description. Lower weight than
    # title matches because descriptions are noisy and keyword-stuffed.
    domain_terms: dict[str, int] = field(default_factory=dict)

    # Hard exclusions: if any appears in the TITLE, the posting is dropped.
    # These are seniority markers, not topics.
    title_blockers: list[str] = field(default_factory=list)

    # Experience thresholds that disqualify. Matched against description.
    experience_blockers: list[str] = field(default_factory=list)



DEFAULT_PROFILE = Profile(
    name="Nicole Ng Yuet Thung",
    location="London",
    target_titles={
        # Compliance / financial crime — best fit for the MSc Law and Finance,
        # and the segment that pays above paralegal rates.
        "compliance analyst": 30,
        "compliance officer": 30,
        "compliance associate": 30,
        "compliance assistant": 26,
        "compliance monitoring": 26,
        "regulatory compliance": 28,
        "financial crime": 28,
        "aml analyst": 28,
        "kyc analyst": 26,
        "know your customer": 24,
        "client onboarding": 22,
        "regulatory reporting": 22,
        "risk and compliance": 24,
        # Legal support
        "paralegal": 26,
        "legal assistant": 22,
        "legal analyst": 24,
        "legal counsel assistant": 22,
        "contracts administrator": 18,
        "legal operations": 18,
        "document review": 16,
        # Graduate/entry framing
        "legal intern": 20,
        "graduate compliance": 26,
        "trainee compliance": 26,
    },
    domain_terms={
        "financial regulation": 12,
        "fca": 10,
        "prudential": 8,
        "sanctions": 8,
        "onboarding": 6,
        "due diligence": 8,
        "corporate finance": 8,
        "capital markets": 6,
        "insolvency": 6,
        "litigation": 5,
        "contract review": 6,
        "legal research": 8,
        "drafting": 6,
        "banking": 5,
        "asset management": 5,
        "fintech": 5,
        "bar": 4,
        "llb": 6,
        "law graduate": 10,
        "no experience": 8,
        "entry level": 8,
        "graduate": 6,
    },
    title_blockers=[
        "head of",
        "director",
        "vp ",
        "vice president",
        "senior",
        "lead ",
        "principal",
        "manager",
        "partner",
        "chief",
        "counsel",  # "General Counsel", "Senior Counsel" — qualified roles
    ],
    experience_blockers=[
        "3+ years",
        "4+ years",
        "5+ years",
        "6+ years",
        "7+ years",
        "10+ years",
        "three years",
        "four years",
        "five years",
        "minimum of 3 years",
        "minimum of 5 years",
        "qualified solicitor",
        "must be sra",
        "nq solicitor",
    ],
)
