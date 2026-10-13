#!/usr/bin/env python3
"""Read-only audit of stored job URLs (Phase 4, part 4).

Produces a JSON report describing, for every job row, whether its stored URL is
a plausible individual posting and - where it is not - a *proposed* (never
applied) repair action with a rollback note.

Guarantees:

* The SQLite database is opened in ``mode=ro`` URI mode. This script never
  writes to the database and never opens it writable.
* Nothing is guessed. When a correct URL cannot be derived from data already
  stored (for example a Greenhouse board slug that was never persisted), the
  row is flagged ``manual_review`` rather than auto-repaired.
* Both the current schema and the historical legacy schema are supported; the
  schema is detected from ``PRAGMA table_info(jobs)``.

Output: ``data/audit/<db-stem>_<UTC-timestamp>.json`` (gitignored) and a short
summary on stdout.

Usage::

    python scripts/audit_job_urls.py --db work_bot_hunter.db
    python scripts/audit_job_urls.py --db work_hunter.db --stdout
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

#: allow running from a checkout without installation
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.scrapers.ashby import is_ashby_detail_url  # noqa: E402
from backend.scrapers.greenhouse import is_greenhouse_detail_url  # noqa: E402
from backend.sources.urls import classify_url  # noqa: E402

#: current-schema URL-ish columns, in candidate precedence order
_CURRENT_URL_FIELDS = ("source_url", "canonical_url", "original_url", "final_url", "application_url")
#: legacy-schema URL-ish columns
_LEGACY_URL_FIELDS = ("url", "link", "application_url")

_KNOWN_ATS_HOSTS = (
    "greenhouse.io", "ashbyhq.com", "lever.co", "workable.com", "myworkdayjobs.com",
    "smartrecruiters.com", "icims.com", "jobvite.com", "workday.com", "bamboohr.com",
)

#: navigation/search/category paths that are never individual job postings
_NON_JOB_PATH = re.compile(
    r"/(search|results|browse|category|categories|tag|tags|directory|companies|"
    r"jobs?|careers?|positions?)/?$"
    r"|/(search|results|browse|category|categories)(/|\?|$)",
    re.IGNORECASE,
)


def _norm_db_path(db: str) -> Path:
    """Accept a bare path or an SQLAlchemy sqlite URL and return a filesystem path."""
    for prefix in ("sqlite+aiosqlite:///", "sqlite+aiosqlite://", "sqlite:///", "sqlite://"):
        if db.startswith(prefix):
            db = db[len(prefix):]
            break
    return Path(db).expanduser()


def _connect_ro(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise SystemExit(f"database not found: {path}")
    uri = f"file:{path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _detect_schema(conn: sqlite3.Connection) -> tuple[str, tuple[str, ...]]:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    if not cols:
        raise SystemExit("no 'jobs' table found")
    if {"source_url", "canonical_url"} & cols:
        return "current", tuple(c for c in _CURRENT_URL_FIELDS if c in cols)
    return "legacy", tuple(c for c in _LEGACY_URL_FIELDS if c in cols)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _is_known_ats_host(host: str) -> bool:
    return any(host == h or host.endswith("." + h) for h in _KNOWN_ATS_HOSTS) or host.endswith("greenhouse.io")


def _classify(url: str) -> str:
    if is_greenhouse_detail_url(url) or is_ashby_detail_url(url):
        return "job_detail"
    kind = classify_url(url)
    return getattr(kind, "value", str(kind))


def _gh_jid(url: str) -> str:
    try:
        qs = parse_qs(urlparse(url).query)
    except ValueError:
        return ""
    for key in ("gh_jid", "gh_src"):
        if key in qs and qs[key]:
            return qs[key][0]
    return ""


def _analyse(urls: dict[str, str], *, source: str, source_job_id: str,
             has_source_url: bool = True) -> dict:
    """Return a finding dict; never mutates or repairs anything.

    ``urls`` maps each stored URL-bearing column to its value. The primary URL
    used for classification is ``source_url`` when present, else the first
    populated field in column precedence order.
    """
    source_url = (urls.get("source_url") or "").strip()
    primary = source_url or next((v for v in urls.values() if v), "")
    issues: list[str] = []

    if has_source_url and not source_url and primary:
        issues.append("missing_source_url")

    if not primary:
        return {
            "urls": urls, "current_url": "", "host": "",
            "classification": "missing", "issues": issues + ["no stored URL"],
            "issue": "no stored URL",
            "proposed_action": "re-scrape", "proposed_url": None,
            "confidence": "medium",
            "reason": "row has no URL; re-run the source with corrected URL construction",
            "rollback": "no change applied; re-scrape the source",
        }

    host = _host(primary)
    classification = _classify(primary)
    path = urlparse(primary).path or "/"
    gh_jid = _gh_jid(primary)

    # valid individual posting in the canonical column -> nothing to do
    if classification == "job_detail" and not issues:
        return {
            "urls": urls, "current_url": primary, "host": host,
            "classification": classification, "issues": [],
            "issue": None, "proposed_action": "none", "proposed_url": primary,
            "confidence": "high", "reason": "already an individual job posting",
            "rollback": "n/a",
        }

    # A Greenhouse identity param proves *a* posting exists, but the board slug
    # is not stored, so a correct URL cannot be derived without guessing.
    if gh_jid:
        issues.append("gh_jid_without_board_slug")
        return {
            "urls": urls, "current_url": primary, "host": host,
            "classification": classification, "issues": issues,
            "issue": "greenhouse posting id present, board slug missing",
            "proposed_action": "manual_review", "proposed_url": None,
            "confidence": "low",
            "reason": (
                f"gh_jid={gh_jid} present but board slug was never persisted; "
                "reconstructing a board URL would require guessing"
            ),
            "rollback": "no change applied; re-scrape the source to repopulate URLs",
        }

    # source_url missing while a usable posting lives in another column
    if classification == "job_detail" and issues == ["missing_source_url"]:
        issues.append("detail_url_not_in_source_url")
        return {
            "urls": urls, "current_url": primary, "host": host,
            "classification": classification, "issues": issues,
            "issue": "individual posting stored outside source_url on a non-policy domain",
            "proposed_action": "manual_review", "proposed_url": None,
            "confidence": "low",
            "reason": (
                "only a non-source field holds the posting URL and its host is not an "
                "allowed source domain; promoting it cannot be validated automatically"
            ),
            "rollback": "no change applied; re-scrape the source to repopulate source_url",
        }

    if _NON_JOB_PATH.search(path):
        issue = "search_or_category_url"
    elif _is_known_ats_host(host):
        issue = "ats_board_url_without_posting"
    else:
        issue = "unclassified_url"
    issues.append(issue)

    if issue == "search_or_category_url":
        return {
            "urls": urls, "current_url": primary, "host": host,
            "classification": classification, "issues": issues, "issue": issue,
            "proposed_action": "re-scrape", "proposed_url": None,
            "confidence": "medium",
            "reason": "stored URL is a search/category page, not an individual posting",
            "rollback": "no change applied; re-run the source with corrected URL construction",
        }

    return {
        "urls": urls, "current_url": primary, "host": host,
        "classification": classification, "issues": issues, "issue": issue,
        "proposed_action": "manual_review", "proposed_url": None,
        "confidence": "low",
        "reason": "URL is not recognisable as an individual posting",
        "rollback": "no change applied",
    }


def audit(db_path: Path) -> dict:
    conn = _connect_ro(db_path)
    try:
        schema, fields = _detect_schema(conn)
        select_cols = ["id"]
        all_cols = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        for col in ("source", "source_id", "source_job_id", "title", "company", "url_status", *fields):
            if col in all_cols and col not in select_cols:
                select_cols.append(col)
        query = f"SELECT {', '.join(select_cols)} FROM jobs"
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()

    findings: list[dict] = []
    has_source_url = "source_url" in fields
    for row in rows:
        data = dict(row)
        source = str(data.get("source") or data.get("source_id") or "")
        source_job_id = str(data.get("source_job_id") or "")
        urls = {f: (data.get(f) or "") for f in fields}
        finding = {"id": data.get("id"), "source": source,
                   "title": data.get("title", ""), "company": data.get("company", ""),
                   "url_status": data.get("url_status")}
        finding.update(_analyse(urls, source=source, source_job_id=source_job_id,
                                has_source_url=has_source_url))
        findings.append(finding)

    action_counts = Counter(f["proposed_action"] for f in findings)
    source_counts = Counter(f["source"] or "(unknown)" for f in findings)
    issue_counts = Counter(i for f in findings for i in f["issues"])

    return {
        "database": str(db_path.resolve()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "schema": schema,
        "columns_used": list(fields),
        "total_jobs": len(findings),
        "actions": dict(action_counts),
        "by_source": dict(source_counts),
        "by_issue": dict(issue_counts),
        "findings": findings,
        "repair_plan": [f for f in findings if f["proposed_action"] not in ("none",)],
        "notes": [
            "Read-only audit; no database writes performed.",
            "proposed_url is null whenever a correct URL cannot be derived from "
            "stored data without guessing (e.g. missing Greenhouse board slug).",
            "Any application of these repairs requires explicit approval and a "
            "recorded rollback; use re-scraping rather than guessed rewrites.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="path to SQLite DB (default: settings.database_url)")
    parser.add_argument("--out-dir", default="data/audit", help="directory for the JSON report")
    parser.add_argument("--stdout", action="store_true", help="also print the full JSON report")
    args = parser.parse_args(argv)

    if args.db:
        db_path = _norm_db_path(args.db)
    else:
        from backend.config import get_settings

        db_path = _norm_db_path(get_settings().database_url)

    report = audit(db_path)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_file = out_dir / f"{db_path.stem}_{stamp}.json"
    out_file.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"database : {report['database']}")
    print(f"schema   : {report['schema']}   total jobs: {report['total_jobs']}")
    print(f"actions  : {report['actions']}")
    print(f"issues   : {report['by_issue']}")
    print(f"report   : {out_file}")
    if args.stdout:
        print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
