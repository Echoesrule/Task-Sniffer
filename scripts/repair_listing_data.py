#!/usr/bin/env python3
"""Repair known data-quality defects in already-persisted job rows.

The deterministic ingestion fixes only affect new/re-scraped rows. This script
repairs the existing baseline without inventing data:

* clears ``application_url`` values that are site-wide/navigation destinations
  (for example ``https://jobicy.com/submit-guest-post``) or that merely point
  back at the job-detail page;
* clears ``salary_currency`` when neither ``salary_min`` nor ``salary_max`` is
  present (a currency alone is not salary data);
* optionally clears known fabricated ``location`` defaults for explicitly named
  sources;
* marks rows from disabled (not currently crawlable) sources with
  ``status = 'quarantined'`` so they are excluded from normal listings, stats,
  alerts, and reports. A successful re-scrape un-quarantines a row.

Dry-run by default. Pass ``--apply`` to write.

Usage::

    python scripts/repair_listing_data.py --db work_bot_hunter.db
    python scripts/repair_listing_data.py --db work_bot_hunter.db --apply
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.sources.urls import canonicalize_url, is_site_wide_url  # noqa: E402

_QUARANTINE_STATUS = "quarantined"


def _db_path(db: str) -> Path:
    for prefix in (
        "sqlite+aiosqlite:///",
        "sqlite+aiosqlite://",
        "sqlite:///",
        "sqlite://",
    ):
        if db.startswith(prefix):
            db = db[len(prefix):]
            break
    return Path(db).expanduser()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _canonical(value: str | None) -> str:
    return canonicalize_url(value or "")


def _same_url(a: str | None, b: str | None) -> bool:
    ca, cb = _canonical(a), _canonical(b)
    return bool(ca and cb and ca == cb)


def build_plan(
    conn: sqlite3.Connection,
    *,
    quarantine_disabled: bool = True,
    only_sources: set[str] | None = None,
    clear_nairobi: bool = False,
    location_sources: set[str] | None = None,
) -> dict:
    """Compute (but do not apply) the repair actions for a database."""
    only_sources = only_sources or set()
    location_sources = location_sources or set()

    job_cols = _columns(conn, "jobs")
    source_cols = _columns(conn, "sources")
    if not job_cols:
        raise SystemExit("no 'jobs' table found")

    sources = {
        row["id"]: {
            "name": row["name"],
            "enabled": bool(row["enabled"]) if "enabled" in source_cols else True,
        }
        for row in conn.execute("SELECT * FROM sources")
    }

    selected = [
        c for c in (
            "id", "source_id", "status", "application_url", "source_url",
            "canonical_url", "final_url", "salary_min", "salary_max",
            "salary_currency", "location",
        )
        if c in job_cols
    ]
    rows = [dict(row) for row in conn.execute(f"SELECT {', '.join(selected)} FROM jobs")]

    plan = {
        "rows_scanned": len(rows),
        "application_url_fixes": [],
        "application_url_reasons": Counter(),
        "currency_fixes": [],
        "location_fixes": [],
        "quarantine_fixes": [],
        "quarantine_sources": Counter(),
    }

    for row in rows:
        job_id = row["id"]
        source = sources.get(row.get("source_id"), {})
        source_name = source.get("name") or f"source-{row.get('source_id')}"

        app_url = row.get("application_url") or ""
        if app_url:
            if is_site_wide_url(app_url):
                plan["application_url_fixes"].append(job_id)
                plan["application_url_reasons"]["site_wide"] += 1
            elif any(
                _same_url(app_url, row.get(key))
                for key in ("source_url", "canonical_url", "final_url")
            ):
                plan["application_url_fixes"].append(job_id)
                plan["application_url_reasons"]["equals_detail"] += 1

        if row.get("salary_currency") and (
            row.get("salary_min") is None and row.get("salary_max") is None
        ):
            plan["currency_fixes"].append(job_id)

        if (
            clear_nairobi
            and row.get("location") == "Nairobi"
            and source_name in location_sources
        ):
            plan["location_fixes"].append(job_id)

        if quarantine_disabled and source.get("enabled") is False:
            if only_sources and source_name not in only_sources:
                continue
            if row.get("status") != _QUARANTINE_STATUS:
                plan["quarantine_fixes"].append(job_id)
                plan["quarantine_sources"][source_name] += 1

    return plan


def apply_plan(conn: sqlite3.Connection, plan: dict) -> None:
    """Apply a plan returned by :func:`build_plan` in one transaction."""
    with conn:
        if plan["application_url_fixes"]:
            conn.executemany(
                "UPDATE jobs SET application_url = NULL WHERE id = ?",
                [(job_id,) for job_id in plan["application_url_fixes"]],
            )
        if plan["currency_fixes"]:
            conn.executemany(
                "UPDATE jobs SET salary_currency = NULL WHERE id = ?",
                [(job_id,) for job_id in plan["currency_fixes"]],
            )
        if plan["location_fixes"]:
            conn.executemany(
                "UPDATE jobs SET location = NULL WHERE id = ?",
                [(job_id,) for job_id in plan["location_fixes"]],
            )
        if plan["quarantine_fixes"]:
            conn.executemany(
                "UPDATE jobs SET status = ? WHERE id = ?",
                [(_QUARANTINE_STATUS, job_id) for job_id in plan["quarantine_fixes"]],
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="work_bot_hunter.db")
    parser.add_argument("--apply", action="store_true", help="write changes")
    parser.add_argument(
        "--no-quarantine",
        action="store_true",
        help="do not quarantine rows from disabled sources",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="only quarantine this source (repeatable); default: all disabled",
    )
    parser.add_argument(
        "--clear-nairobi-location",
        action="store_true",
        help="clear location='Nairobi' for sources named with --location-source",
    )
    parser.add_argument(
        "--location-source",
        action="append",
        default=[],
        help="source whose 'Nairobi' location is known to be a fabricated default",
    )
    args = parser.parse_args()

    path = _db_path(args.db)
    if not path.exists():
        print(f"database not found: {path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    plan = build_plan(
        conn,
        quarantine_disabled=not args.no_quarantine,
        only_sources=set(args.source),
        clear_nairobi=args.clear_nairobi_location,
        location_sources=set(args.location_source),
    )

    print(f"database: {path}")
    print(f"rows scanned: {plan['rows_scanned']}")
    print(
        f"application_url to clear: {len(plan['application_url_fixes'])} "
        f"{dict(plan['application_url_reasons'])}"
    )
    print(f"salary_currency without amount to clear: {len(plan['currency_fixes'])}")
    if args.clear_nairobi_location:
        print(f"fabricated 'Nairobi' locations to clear: {len(plan['location_fixes'])}")
    print(
        f"rows to quarantine: {len(plan['quarantine_fixes'])} "
        f"{dict(plan['quarantine_sources'])}"
    )

    if not args.apply:
        print("dry run; pass --apply to write changes")
        conn.close()
        return 0

    apply_plan(conn, plan)
    conn.close()
    print("applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
