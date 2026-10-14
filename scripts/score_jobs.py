"""Seed the default candidate profile and (re)compute match scores for jobs.

Wires the previously-uninvoked :class:`JobScorer` to the persisted corpus:
it ensures a candidate profile exists, then scores every job against it and
writes ``match_score`` / ``match_breakdown`` / ``classification``.

Usage:
    python scripts/score_jobs.py [--db work_bot_hunter.db] [--only-empty]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.matching.scoring import (  # noqa: E402
    apply_score,
    candidate_to_scoring_dict,
    ensure_default_candidate,
    score_job,
)
from backend.models.database import Database, Job  # noqa: E402


async def _run(db_url: str, only_empty: bool) -> tuple[str, str, int]:
    db = Database(db_url)
    await db.init_db()
    try:
        async with db.async_session_factory() as session:
            candidate = await ensure_default_candidate(session)
            candidate_dict = candidate_to_scoring_dict(candidate)

            stmt = select(Job)
            if only_empty:
                stmt = stmt.where((Job.match_score == 0.0) | (Job.match_score.is_(None)))
            jobs = (await session.execute(stmt)).scalars().all()

            for job in jobs:
                apply_score(job, score_job(job, candidate_dict))
            await session.commit()
            return candidate.name, candidate.email, len(jobs)
    finally:
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="override database URL")
    parser.add_argument(
        "--only-empty",
        action="store_true",
        help="only score jobs with a zero/missing match score",
    )
    args = parser.parse_args()

    db_url = args.db or get_settings().database_url
    name, email, scored = asyncio.run(_run(db_url, args.only_empty))
    print(f"candidate={name} <{email}> scored_jobs={scored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
