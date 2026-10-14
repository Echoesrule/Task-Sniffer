"""Backfill derived skills columns for already-persisted jobs.

The skills pipeline (``backend.skills``) only runs at ingestion time. Jobs
persisted before it existed (or before a re-scrape refreshes them) have empty
``skills``/``skills_required``/``skills_preferred``/``skills_detail``. This
script recomputes them deterministically from the stored title + description
and writes them back. It performs no network access and does not touch URLs.

Idempotent: re-running produces the same values.

Usage:
    python scripts/backfill_skills.py [--db work_bot_hunter.db] [--all]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.skills import analyze_skills  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="work_bot_hunter.db")
    parser.add_argument(
        "--all",
        action="store_true",
        help="recompute for every job, not only rows with empty skills",
    )
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 1

    con = sqlite3.connect(args.db)
    cur = con.cursor()

    where = "" if args.all else "WHERE skills IS NULL OR skills = '[]'"
    rows = cur.execute(
        f"SELECT id, title, description, skills FROM jobs {where}"
    ).fetchall()

    total = len(rows)
    updated = 0
    extracted = 0
    hits = 0

    for job_id, title, description, skills in rows:
        analysis = analyze_skills(title or "", description or "")
        provided = []
        if skills:
            try:
                provided = json.loads(skills) or []
            except (json.JSONDecodeError, TypeError):
                provided = []
        merged = sorted(set(analysis.skills) | set(provided))

        cur.execute(
            "UPDATE jobs SET skills = ?, skills_required = ?, "
            "skills_preferred = ?, skills_detail = ? WHERE id = ?",
            (
                json.dumps(merged),
                json.dumps(analysis.required),
                json.dumps(analysis.preferred),
                json.dumps(analysis.detail),
                job_id,
            ),
        )
        updated += 1
        if merged:
            extracted += 1
        if analysis.detail:
            hits += len(analysis.detail)

    con.commit()

    remaining = cur.execute(
        "SELECT COUNT(*) FROM jobs WHERE skills IS NULL OR skills = '[]'"
    ).fetchone()[0]
    con.close()

    print(
        f"scanned={total} updated={updated} "
        f"with_skills={extracted} detail_rows={hits} remaining_empty={remaining}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
