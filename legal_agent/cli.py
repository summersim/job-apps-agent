"""CLI.

    python -m legal_agent.cli fetch      # pull, score, dedupe, store
    python -m legal_agent.cli queue      # show the review queue
    python -m legal_agent.cli stats
    python -m legal_agent.cli serve      # local web UI over the above

Nothing in this tool submits an application. It ranks and stages; a human
approves and submits.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .profile import NICOLE
from .scoring import score_all
from .sources import AdzunaSource, ReedSource, gather_all
from .store import Store, default_db_path

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


def build_sources():
    sources = []
    reed_key = os.getenv("REED_API_KEY")
    if reed_key:
        sources.append(ReedSource(reed_key))
    else:
        print("  ! REED_API_KEY not set — skipping Reed", file=sys.stderr)

    adzuna_id, adzuna_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if adzuna_id and adzuna_key:
        sources.append(AdzunaSource(adzuna_id, adzuna_key))
    else:
        print("  ! ADZUNA_APP_ID/KEY not set — skipping Adzuna", file=sys.stderr)

    if not sources:
        sys.exit("No sources configured. Set the API keys and retry.")
    return sources


async def cmd_fetch(args) -> None:
    store = Store(args.db)
    sources = build_sources()

    print(f"Fetching {len(KEYWORDS)} keywords across {len(sources)} source(s)...")
    raw = await gather_all(sources, KEYWORDS, per_keyword=args.per_keyword)
    print(f"  {len(raw)} raw postings")

    kept = score_all(raw, NICOLE)
    print(f"  {len(kept)} passed filters ({len(raw) - len(kept)} excluded)")

    new, dup = store.upsert(kept)
    print(f"  {new} new, {dup} duplicates suppressed")
    store.close()


def cmd_queue(args) -> None:
    store = Store(args.db)
    rows = list(store.queue(min_score=args.min_score, limit=args.limit,
                            status=args.status, location=args.location))
    if not rows:
        print("Queue empty.")
        return
    for r in rows:
        print(f"\n[{r['score']:>3}] {r['title']}")
        print(f"      {r['employer']}  ·  {r['location']}  ·  {r['contract_type'] or 'n/a'}")
        sal = (f"£{r['salary_min']:,.0f}" if r["salary_min"] else "not stated")
        print(f"      salary {sal}  ·  posted {r['posted'] or '?'}  ·  {r['source']}")
        print(f"      {r['score_reasons']}")
        print(f"      {r['url']}")
    print(f"\n{len(rows)} shown.")
    store.close()


def cmd_stats(args) -> None:
    store = Store(args.db)
    for status, count in sorted(store.stats().items()):
        print(f"{status:>12}  {count}")
    store.close()


def cmd_serve(args) -> None:
    from .web import serve
    serve(db_path=args.db, port=args.port, open_browser=not args.no_browser)


def main() -> None:
    ap = argparse.ArgumentParser(prog="legal_agent")
    ap.add_argument("--db", default=default_db_path(),
                    help="SQLite path (default: jobs.db in the project root)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch")
    f.add_argument("--per-keyword", type=int, default=200)

    q = sub.add_parser("queue")
    q.add_argument("--min-score", type=int, default=30)
    q.add_argument("--limit", type=int, default=25)
    q.add_argument("--status", default="new")
    q.add_argument("--location", default="Central London",
                   help="substring match against posting location "
                        "(default: 'Central London'; pass '' for anywhere)")

    sub.add_parser("stats")

    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true",
                    help="don't auto-open the UI in a browser tab")

    args = ap.parse_args()
    if args.cmd == "fetch":
        asyncio.run(cmd_fetch(args))
    elif args.cmd == "queue":
        cmd_queue(args)
    elif args.cmd == "serve":
        cmd_serve(args)
    else:
        cmd_stats(args)


if __name__ == "__main__":
    main()
