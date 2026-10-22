"""Recompute match scores for an explicitly selected candidate.

Wires the previously-uninvoked :class:`JobScorer` to the persisted corpus:
it ensures a candidate profile exists, then scores every job against it and
writes candidate-specific rows in ``candidate_job_scores``.

Usage:
    python scripts/score_jobs.py --candidate-id <id> [--db <url>] [--only-empty]
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
    candidate_to_scoring_dict,
    score_job,
    store_score,
)
from backend.models.database import Candidate, CandidateJobScore, Database, Job  # noqa: E402


async def _run(db_url: str, candidate_id: str, only_empty: bool) -> tuple[str, str, int]:
    db = Database(db_url)
    await db.init_db()
    try:
        async with db.async_session_factory() as session:
            candidate = await session.get(Candidate, candidate_id)
            if candidate is None:
                raise ValueError(f"Candidate {candidate_id!r} was not found")
            candidate_dict = candidate_to_scoring_dict(candidate)
            existing_scores = {
                score.job_id: score
                for score in (await session.execute(
                    select(CandidateJobScore).where(CandidateJobScore.candidate_id == candidate.id)
                )).scalars().all()
            }

            stmt = select(Job)
            if only_empty:
                existing = select(CandidateJobScore.job_id).where(
                    CandidateJobScore.candidate_id == candidate.id
                )
                stmt = stmt.where(Job.id.not_in(existing))
            jobs = (await session.execute(stmt)).scalars().all()

            for job in jobs:
                store_score(session, candidate, job, score_job(job, candidate_dict), existing_scores.get(job.id))
            await session.commit()
            return candidate.name, candidate.email, len(jobs)
    finally:
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="override database URL")
    parser.add_argument("--candidate-id", required=True, help="candidate whose scores should be recalculated")
    parser.add_argument(
        "--only-empty",
        action="store_true",
        help="only score jobs with a zero/missing match score",
    )
    args = parser.parse_args()

    db_url = args.db or get_settings().database_url
    name, email, scored = asyncio.run(_run(db_url, args.candidate_id, args.only_empty))
    print(f"candidate={name} <{email}> scored_jobs={scored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
