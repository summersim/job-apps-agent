"""Reed adapter. https://www.reed.co.uk/developers/jobseeker"""

from __future__ import annotations

import asyncio

import httpx

from ..models import Posting
from .base import clean, get_with_retry, parse_date


class ReedSource:
    """Reed uses HTTP Basic auth: API key as username, empty password."""

    name = "reed"
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
                r = await get_with_retry(client, self.BASE, params=params,
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
            description=clean(j.get("jobDescription")),
            url=j.get("jobUrl", ""),
            posted=parse_date(j.get("date"), "%d/%m/%Y"),
            salary_min=j.get("minimumSalary"),
            salary_max=j.get("maximumSalary"),
            contract_type=("contract" if j.get("contractType") == "Contract"
                           else "permanent" if j.get("contractType") == "Permanent"
                           else None),
        )
