"""Job board adapters.

Both Reed and Adzuna publish free, documented APIs for UK listings. We use
those rather than scraping: no browser automation, no ToS breach, no account
ban risk, and structured salary and contract-type fields instead of regex over
HTML.

Reed:   https://www.reed.co.uk/developers/jobseeker
Adzuna: https://developer.adzuna.com/

Verify parameter names against those docs before first run — both APIs have
changed field names in the past.
"""

from __future__ import annotations

import asyncio
import html
import random
import re
from datetime import datetime, date
from typing import Optional

import httpx

from .models import Posting

_TAGS = re.compile(r"<[^>]+>")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return html.unescape(_TAGS.sub(" ", text)).strip()


async def _get_with_retry(client: httpx.AsyncClient, url: str, *,
                          max_retries: int = 5, **kwargs) -> httpx.Response:
    """GET with exponential backoff on 429, honoring Retry-After when present."""
    for attempt in range(max_retries + 1):
        r = await client.get(url, **kwargs)
        if r.status_code == 429 and attempt < max_retries:
            retry_after = r.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else min(2 ** attempt, 30)
            await asyncio.sleep(delay + random.uniform(0, 0.5))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()  # pragma: no cover - loop always returns or raises above
    return r


def _parse_date(value: str | None, fmt: str) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[: len(fmt.replace("%", "")) + 6], fmt).date()
    except (ValueError, TypeError):
        return None


class ReedSource:
    """Reed uses HTTP Basic auth: API key as username, empty password."""

    BASE = "https://www.reed.co.uk/api/1.0/search"
    PAGE = 100  # Reed's maximum resultsToTake

    def __init__(self, api_key: str, location: str = "London",
                 distance_miles: int = 15, max_concurrency: int = 2):
        self.auth = (api_key, "")
        self.location = location
        self.distance = distance_miles
        self._sem = asyncio.Semaphore(max_concurrency)

    async def fetch(self, client: httpx.AsyncClient, keyword: str,
                    max_results: int = 300) -> list[Posting]:
        out: list[Posting] = []
        skip = 0
        while len(out) < max_results:
            params = {
                "keywords": keyword,
                "locationName": self.location,
                "distanceFromLocation": self.distance,
                "resultsToTake": self.PAGE,
                "resultsToSkip": skip,
            }
            async with self._sem:
                r = await _get_with_retry(client, self.BASE, params=params,
                                          auth=self.auth, timeout=30)
            payload = r.json()
            results = payload.get("results", [])
            if not results:
                break
            out.extend(self._to_posting(j) for j in results)
            skip += self.PAGE
            if skip >= payload.get("totalResults", 0):
                break
            await asyncio.sleep(0.3)  # be polite
        return out[:max_results]

    @staticmethod
    def _to_posting(j: dict) -> Posting:
        return Posting(
            source="reed",
            source_id=str(j.get("jobId")),
            title=j.get("jobTitle", ""),
            employer=j.get("employerName", ""),
            location=j.get("locationName", ""),
            description=_clean(j.get("jobDescription")),
            url=j.get("jobUrl", ""),
            posted=_parse_date(j.get("date"), "%d/%m/%Y"),
            salary_min=j.get("minimumSalary"),
            salary_max=j.get("maximumSalary"),
            contract_type=("contract" if j.get("contractType") == "Contract"
                           else "permanent" if j.get("contractType") == "Permanent"
                           else None),
        )


class AdzunaSource:
    BASE = "https://api.adzuna.com/v1/api/jobs/gb/search"
    PAGE = 50

    def __init__(self, app_id: str, app_key: str, location: str = "London",
                 max_days_old: int = 21, max_concurrency: int = 2):
        self.app_id = app_id
        self.app_key = app_key
        self.location = location
        self.max_days_old = max_days_old
        self._sem = asyncio.Semaphore(max_concurrency)

    async def fetch(self, client: httpx.AsyncClient, keyword: str,
                    max_results: int = 300) -> list[Posting]:
        out: list[Posting] = []
        page = 1
        while len(out) < max_results:
            params = {
                "app_id": self.app_id,
                "app_key": self.app_key,
                "what": keyword,
                "where": self.location,
                "results_per_page": self.PAGE,
                "max_days_old": self.max_days_old,
                "content-type": "application/json",
            }
            async with self._sem:
                r = await _get_with_retry(client, f"{self.BASE}/{page}",
                                          params=params, timeout=30)
            results = r.json().get("results", [])
            if not results:
                break
            out.extend(self._to_posting(j) for j in results)
            page += 1
            await asyncio.sleep(0.3)
        return out[:max_results]

    @staticmethod
    def _to_posting(j: dict) -> Posting:
        ct = (j.get("contract_type") or "").lower() or None
        return Posting(
            source="adzuna",
            source_id=str(j.get("id")),
            title=j.get("title", ""),
            employer=(j.get("company") or {}).get("display_name", ""),
            location=(j.get("location") or {}).get("display_name", ""),
            description=_clean(j.get("description")),
            url=j.get("redirect_url", ""),
            posted=_parse_date(j.get("created"), "%Y-%m-%dT%H:%M:%S"),
            salary_min=j.get("salary_min"),
            salary_max=j.get("salary_max"),
            contract_type=ct,
        )


async def gather_all(sources: list, keywords: list[str],
                     per_keyword: int = 200) -> list[Posting]:
    """Fan out every keyword across every source concurrently."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [
            src.fetch(client, kw, per_keyword)
            for src in sources
            for kw in keywords
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    postings: list[Posting] = []
    for res in results:
        if isinstance(res, Exception):
            print(f"  ! source error: {type(res).__name__}: {res}")
            continue
        postings.extend(res)
    return postings
