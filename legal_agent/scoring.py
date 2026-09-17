"""Relevance scoring.

Deliberately deterministic keyword scoring, not an LLM call. Three reasons:
it is free at ingestion volume, it is auditable (every score carries its
reasons, so you can see why a bad match ranked high and fix the weights), and
it is testable. Save the model calls for the cover letters, where judgement
actually matters.
"""

from __future__ import annotations

from .models import Posting
from .profile import Profile


def score(posting: Posting, profile: Profile) -> Posting:
    title = posting.title.lower()
    body = f"{posting.title} {posting.description}".lower()
    points = 0
    reasons: list[str] = []

    # Hard exclusions first — cheap, and they kill most of the noise.
    for blocker in profile.title_blockers:
        if blocker in title:
            posting.score = -1
            posting.score_reasons = [f"excluded: title contains '{blocker.strip()}'"]
            return posting

    for blocker in profile.experience_blockers:
        if blocker in body:
            posting.score = -1
            posting.score_reasons = [f"excluded: requires '{blocker}'"]
            return posting

    # Title match — the dominant signal. Only the best one counts, so a title
    # stuffed with synonyms doesn't inflate.
    title_hits = [(w, t) for t, w in profile.target_titles.items() if t in title]
    if not title_hits:
        posting.score = -1
        posting.score_reasons = ["excluded: no target title match"]
        return posting
    best_w, best_t = max(title_hits)
    points += best_w
    reasons.append(f"title '{best_t}' (+{best_w})")

    # Domain vocabulary, capped so keyword-stuffed adverts don't dominate.
    domain_points = 0
    for term, weight in profile.domain_terms.items():
        if term in body:
            domain_points += weight
    domain_points = min(domain_points, 30)
    if domain_points:
        points += domain_points
        reasons.append(f"domain terms (+{domain_points})")

    # Contract and temp roles hire fast and don't require sponsorship —
    # a genuine advantage here, so bias toward them slightly.
    if posting.contract_type in ("contract", "temp", "contract_type"):
        points += 8
        reasons.append("contract/temp (+8)")

    # Salary: reward roles that clear the level she's aiming for, without
    # excluding unstated salaries, which are the majority.
    if posting.salary_min:
        if posting.salary_min >= 33_400:
            points += 10
            reasons.append("salary >= 33.4k (+10)")
        elif posting.salary_min >= 28_000:
            points += 5
            reasons.append("salary >= 28k (+5)")
        elif posting.salary_min < 22_000:
            points -= 8
            reasons.append("salary < 22k (-8)")

    # Freshness. Agency roles fill in days; a three-week-old post is usually dead.
    if posting.posted:
        from datetime import date
        age = (date.today() - posting.posted).days
        if age <= 3:
            points += 10
            reasons.append("posted <= 3 days (+10)")
        elif age <= 7:
            points += 5
            reasons.append("posted <= 7 days (+5)")
        elif age > 28:
            points -= 10
            reasons.append("posted > 28 days (-10)")

    posting.score = points
    posting.score_reasons = reasons
    return posting


def score_all(postings: list[Posting], profile: Profile) -> list[Posting]:
    scored = [score(p, profile) for p in postings]
    return [p for p in scored if p.score >= 0]
