#!/usr/bin/env python3
"""Read-only per-source data-quality report for stored job listings.

This is the measurement step of the listing-data remediation plan. It reads the
SQLite database in ``mode=ro`` and reports, per source:

* completeness of the fields users see (title, company, location, description,
  posted date, salary amount, application URL);
* quality-flag counts (currency without an amount, application URL equal to the
  detail page, site-wide/navigation application URLs, ``VALID`` rows missing a
  canonical/source URL);
* application-URL repetition, which exposes one link being stored for every
  row;
* duplicate-fingerprint rate.

It performs no network access and never writes to the database. Link health is
a separate, opt-in network check.

Usage::

    python scripts/data_quality_report.py --db work_bot_hunter.db
    python scripts/data_quality_report.py --db work_bot_hunter.db --stdout
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.sources.urls import canonicalize_url, is_site_wide_url  # noqa: E402


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


def _connect_ro(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise SystemExit(f"database not found: {path}")
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _pct(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


def _canonical(value: str | None) -> str:
    return canonicalize_url(value or "")


def _same_url(a: str | None, b: str | None) -> bool:
    ca, cb = _canonical(a), _canonical(b)
    return bool(ca and cb and ca == cb)


def _report(conn: sqlite3.Connection) -> dict:
    job_cols = _columns(conn, "jobs")
    if not job_cols:
        raise SystemExit("no 'jobs' table found")

    source_cols = _columns(conn, "sources")
    sources = {
        row["id"]: {
            "name": row["name"],
            "enabled": bool(row["enabled"]) if "enabled" in row.keys() else None,
        }
        for row in conn.execute("SELECT * FROM sources")
    }

    wanted = (
        "id", "source_id", "title", "company", "location", "description",
        "posted_at", "closing_at", "salary_min", "salary_max", "salary_currency",
        "application_url", "source_url", "canonical_url", "final_url",
        "url_status", "fingerprint", "status", "remote_type",
    )
    selected = [c for c in wanted if c in job_cols]
    rows = [dict(row) for row in conn.execute(f"SELECT {', '.join(selected)} FROM jobs")]

    per_source: dict[str, dict] = {}
    fingerprints_by_source: dict[str, list[str]] = {}

    for row in rows:
        source_id = row.get("source_id")
        source_name = sources.get(source_id, {}).get("name") or f"source-{source_id}"
        bucket = per_source.setdefault(
            source_name,
            {
                "total": 0,
                "by_status": Counter(),
                "by_url_status": Counter(),
                "complete": Counter(),
                "flags": Counter(),
                "application_urls": Counter(),
                "application_url_rows": 0,
            },
        )
        bucket["total"] += 1
        bucket["by_status"][row.get("status") or "unknown"] += 1
        bucket["by_url_status"][row.get("url_status") or "unknown"] += 1

        for field in ("title", "company", "location", "description", "posted_at"):
            if row.get(field):
                bucket["complete"][field] += 1

        if row.get("salary_min") is not None or row.get("salary_max") is not None:
            bucket["complete"]["salary_amount"] += 1
        if row.get("salary_currency"):
            bucket["complete"]["salary_currency"] += 1
        if row.get("application_url"):
            bucket["complete"]["application_url"] += 1

        if row.get("salary_currency") and (
            row.get("salary_min") is None and row.get("salary_max") is None
        ):
            bucket["flags"]["currency_without_amount"] += 1

        app_url = row.get("application_url") or ""
        if app_url:
            bucket["application_urls"][app_url] += 1
            bucket["application_url_rows"] += 1
            if is_site_wide_url(app_url):
                bucket["flags"]["site_wide_application_url"] += 1
            if any(
                _same_url(app_url, row.get(key))
                for key in ("source_url", "canonical_url", "final_url")
            ):
                bucket["flags"]["application_url_equals_detail"] += 1

        if row.get("url_status") == "VALID" and not (
            row.get("source_url") and row.get("canonical_url")
        ):
            bucket["flags"]["valid_without_required_urls"] += 1

        if row.get("location") == "Nairobi":
            bucket["flags"]["location_default_nairobi"] += 1

        fingerprint = row.get("fingerprint")
        if fingerprint:
            fingerprints_by_source.setdefault(source_name, []).append(fingerprint)

    total_jobs = len(rows)
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": str(getattr(conn, "database", "")),
        "totals": {
            "jobs": total_jobs,
            "by_status": dict(Counter(row.get("status") or "unknown" for row in rows)),
        },
        "sources": {},
    }

    for source_name, bucket in sorted(per_source.items()):
        total = bucket["total"]
        completeness = {
            field: _pct(bucket["complete"][field], total)
            for field in (
                "title", "company", "location", "description", "posted_at",
                "salary_amount", "salary_currency", "application_url",
            )
        }
        top_repeated = [
            {"url": url, "rows": count}
            for url, count in bucket["application_urls"].most_common(5)
            if count > 1
        ]
        fingerprints = fingerprints_by_source.get(source_name, [])
        distinct = len(set(fingerprints))
        duplicate_rows = len(fingerprints) - distinct

        report["sources"][source_name] = {
            "total": total,
            "by_status": dict(bucket["by_status"]),
            "by_url_status": dict(bucket["by_url_status"]),
            "completeness": completeness,
            "quality_flags": dict(bucket["flags"]),
            "application_urls": {
                "rows_with_value": bucket["application_url_rows"],
                "distinct": len(bucket["application_urls"]),
                "top_repeated": top_repeated,
            },
            "duplicates": {
                "fingerprinted_rows": len(fingerprints),
                "distinct_fingerprints": distinct,
                "duplicate_rows": duplicate_rows,
                "rate": _pct(duplicate_rows, len(fingerprints)),
            },
        }

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="work_bot_hunter.db")
    parser.add_argument(
        "--out",
        default="",
        help="output JSON path (default: data/quality/<db-stem>_<UTC timestamp>.json)",
    )
    parser.add_argument("--stdout", action="store_true", help="print JSON to stdout")
    args = parser.parse_args()

    path = _db_path(args.db)
    conn = _connect_ro(path)
    report = _report(conn)
    conn.close()
    report["database"] = str(path)

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.stdout:
        print(payload)
    else:
        out = Path(args.out) if args.out else (
            Path("data") / "quality"
            / f"{path.stem}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
        print(f"wrote {out}")

    print(
        f"jobs={report['totals']['jobs']} "
        f"status={report['totals']['by_status']} "
        f"sources={len(report['sources'])}"
    )
    for name, data in report["sources"].items():
        flags = data["quality_flags"]
        print(
            f"  {name}: rows={data['total']} "
            f"desc={data['completeness']['description']:.0%} "
            f"posted={data['completeness']['posted_at']:.0%} "
            f"app_url={data['completeness']['application_url']:.0%} "
            f"site_wide_app={flags.get('site_wide_application_url', 0)} "
            f"currency_no_amount={flags.get('currency_without_amount', 0)} "
            f"dup_rate={data['duplicates']['rate']:.1%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
