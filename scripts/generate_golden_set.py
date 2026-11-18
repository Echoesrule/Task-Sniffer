#!/usr/bin/env python3
"""Generate a golden-set labeling sheet from stored job listings.

Creates a CSV (default) or JSONL file with stored listing fields plus blank
label columns for manual verification. Intended for Phase 2 accuracy gates.

The tool is read-only against the database.

Usage::

    python scripts/generate_golden_set.py --db work_bot_hunter.db --out data/golden/set.csv
    python scripts/generate_golden_set.py --db work_bot_hunter.db --size 150 --stratify source
    python scripts/generate_golden_set.py --db work_bot_hunter.db --include-quarantined
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


STORED_FIELDS = [
    "job_id",
    "source",
    "status",
    "url_status",
    "source_url",
    "canonical_url",
    "stored_title",
    "stored_company",
    "stored_location",
    "stored_description",
    "stored_posted_at",
    "stored_closing_at",
    "stored_salary_min",
    "stored_salary_max",
    "stored_salary_currency",
    "stored_salary_period",
    "stored_employment_type",
    "stored_remote",
    "stored_remote_type",
    "stored_application_url",
]

LABEL_FIELDS = [
    "label_title",
    "label_company",
    "label_location",
    "label_description_present",  # yes/no/na
    "label_posted_at",  # YYYY-MM-DD, empty, or na
    "label_posted_at_provided",  # yes/no/unknown
    "label_application_url",  # expected URL, empty, or na
    "label_application_url_correct",  # yes/no/na (when stored present)
    "title_correct",  # yes/no
    "company_correct",  # yes/no
    "location_correct",  # yes/no/na
    "notes",
]


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


def _fetch_rows(conn: sqlite3.Connection, include_quarantined: bool) -> list[dict]:
    where = "" if include_quarantined else "WHERE j.status != 'quarantined'"
    sql = f"""
        SELECT j.id AS job_id, s.name AS source, j.status, j.url_status,
               j.source_url, j.canonical_url, j.title, j.company, j.location,
               j.description, j.posted_at, j.closing_at, j.salary_min, j.salary_max,
               j.salary_currency, j.salary_period, j.employment_type, j.remote,
               j.remote_type, j.application_url
        FROM jobs j
        JOIN sources s ON s.id = j.source_id
        {where}
        ORDER BY s.name, j.created_at DESC
    """
    out = []
    for row in conn.execute(sql):
        d = dict(row)
        desc = (d.pop("description") or "").strip()
        # keep a readable snippet; full text is large but useful for labeling
        d["stored_description"] = " ".join(desc.split())
        d["stored_title"] = d.pop("title") or ""
        d["stored_company"] = d.pop("company") or ""
        d["stored_location"] = d.pop("location") or ""
        d["stored_posted_at"] = d.pop("posted_at") or ""
        d["stored_closing_at"] = d.pop("closing_at") or ""
        d["stored_salary_min"] = d.pop("salary_min")
        d["stored_salary_max"] = d.pop("salary_max")
        d["stored_salary_currency"] = d.pop("salary_currency") or ""
        d["stored_salary_period"] = d.pop("salary_period") or ""
        d["stored_employment_type"] = d.pop("employment_type") or ""
        d["stored_remote"] = d.pop("remote")
        d["stored_remote_type"] = d.pop("remote_type") or ""
        d["stored_application_url"] = d.pop("application_url") or ""
        d["source_url"] = d.get("source_url") or ""
        d["canonical_url"] = d.get("canonical_url") or ""
        d["url_status"] = d.get("url_status") or ""
        out.append(d)
    return out


def _sample(rows: list[dict], size: int, stratify: str, seed: int) -> list[dict]:
    if not rows:
        return []
    rng = random.Random(seed)
    if size <= 0 or size >= len(rows):
        picked = list(rows)
        rng.shuffle(picked)
        return picked

    if stratify == "none":
        return rng.sample(rows, size)

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = str(row.get(stratify, "unknown"))
        groups[key].append(row)

    keys = sorted(groups)
    for key in keys:
        rng.shuffle(groups[key])

    # proportional allocation with at-least-one where possible
    total = len(rows)
    alloc: dict[str, int] = {}
    remaining = size
    for key in keys:
        n = max(1, round(size * len(groups[key]) / total)) if size >= len(keys) else 0
        n = min(n, len(groups[key]))
        alloc[key] = n
        remaining -= n
    # adjust to exact size
    while remaining > 0:
        progressed = False
        for key in keys:
            if remaining <= 0:
                break
            if alloc[key] < len(groups[key]):
                alloc[key] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            break
    while remaining < 0:
        for key in sorted(keys, key=lambda k: alloc[k], reverse=True):
            if remaining >= 0:
                break
            if alloc[key] > 0:
                alloc[key] -= 1
                remaining += 1

    picked: list[dict] = []
    for key in keys:
        picked.extend(groups[key][: alloc.get(key, 0)])
    rng.shuffle(picked)
    return picked[:size]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="work_bot_hunter.db")
    parser.add_argument("--out", default="", help="output path (.csv or .jsonl)")
    parser.add_argument("--size", type=int, default=150, help="sample size (0 = all)")
    parser.add_argument(
        "--stratify",
        choices=["source", "status", "none"],
        default="source",
        help="stratification key",
    )
    parser.add_argument("--seed", type=int, default=42, help="sampling seed")
    parser.add_argument(
        "--include-quarantined",
        action="store_true",
        help="include quarantined rows in the sampling pool",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "jsonl"],
        default="",
        help="output format (inferred from --out extension by default)",
    )
    args = parser.parse_args()

    path = _db_path(args.db)
    conn = _connect_ro(path)
    rows = _fetch_rows(conn, args.include_quarantined)
    conn.close()
    sampled = _sample(rows, args.size, args.stratify, args.seed)

    if not args.out:
        ext = "csv" if args.format in ("", "csv") else "jsonl"
        out = Path("data") / "golden" / f"golden_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.{ext}"
    else:
        out = Path(args.out)
    fmt = args.format or ("jsonl" if out.suffix.lower() == ".jsonl" else "csv")
    out.parent.mkdir(parents=True, exist_ok=True)

    headers = STORED_FIELDS + LABEL_FIELDS
    for row in sampled:
        for field in LABEL_FIELDS:
            row.setdefault(field, "")

    if fmt == "jsonl":
        with out.open("w", encoding="utf-8") as fh:
            for row in sampled:
                fh.write(json.dumps({k: row.get(k, "") for k in headers}, ensure_ascii=False) + "\n")
    else:
        with out.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=headers)
            writer.writeheader()
            for row in sampled:
                writer.writerow({k: row.get(k, "") for k in headers})

    by_source: dict[str, int] = defaultdict(int)
    for row in sampled:
        by_source[str(row.get("source", "unknown"))] += 1
    print(f"wrote {out} ({len(sampled)} rows, format={fmt}, stratify={args.stratify})")
    print(f"by_source={dict(sorted(by_source.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
