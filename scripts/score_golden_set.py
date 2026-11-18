#!/usr/bin/env python3
"""Score a labeled golden set against stored job data (Phase 2 gates).

Reads a CSV or JSONL produced by ``generate_golden_set.py`` and filled with
human labels, joins each row to the current database by ``job_id``, and
computes field-level exact match / presence / precision metrics.

Labeling conventions (per row):
- ``*_correct``: ``yes``, ``no``, ``na`` (not applicable), or blank to skip.
- ``label_title``/``label_company``/``label_location``: expected value. If the
  corresponding ``*_correct`` is blank, the scorer compares the label to the
  stored value (case/whitespace-normalized). If both label and ``*_correct``
  are blank, the row is excluded from that metric.
- ``label_description_present``: ``yes`` (source provides it), ``no`` (source
  provides but we missed it), ``na``/blank (not provided / skip).
- ``label_posted_at_provided``: ``yes``/``no``/``na``/blank.
- ``label_application_url_correct``: ``yes``/``no``/``na``/blank. Precision is
  computed over rows with a stored application URL and a yes/no label.

Usage::

    python scripts/score_golden_set.py --labels data/golden/set.csv --db work_bot_hunter.db
    python scripts/score_golden_set.py --labels data/golden/set.csv --check-links
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

GATES = {
    "title_exact_match": 0.95,
    "company_exact_match": 0.90,
    "location_exact_match": 0.90,
    "description_present": 0.90,
    "posted_date_present": 0.90,
    "application_url_precision": 0.95,
    "dead_link_rate_max": 0.05,
    "duplicate_rate_max": 0.02,
}


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


def _norm(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    return re.sub(r"\s+", " ", text)


def _read_labels(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".jsonl":
        rows = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _fetch_jobs(conn: sqlite3.Connection) -> dict[str, dict]:
    sql = """
        SELECT j.id, s.name AS source, j.status, j.title, j.company, j.location,
               j.description, j.posted_at, j.closing_at, j.salary_min, j.salary_max,
               j.application_url, j.source_url, j.canonical_url, j.fingerprint
        FROM jobs j JOIN sources s ON s.id = j.source_id
    """
    return {row["id"]: dict(row) for row in conn.execute(sql)}


def _yn(value: Any) -> str:
    return str(value or "").strip().lower()


def _correct(label_row: dict, correct_field: str, label_field: str, stored_value: Any) -> str | None:
    flag = _yn(label_row.get(correct_field))
    if flag in ("yes", "y", "true", "1"):
        return "yes"
    if flag in ("no", "n", "false", "0"):
        return "no"
    if flag in ("na", "n/a", "skip"):
        return "na"
    expected = str(label_row.get(label_field) or "").strip()
    if expected:
        return "yes" if _norm(expected) == _norm(stored_value) else "no"
    return None


def _pct(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return num / den


def _fmt(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate:.1%}"


def _check_links(urls: list[str], timeout: float = 8.0) -> tuple[int, int]:
    """Return (checked, dead). Best-effort, no redirects policy beyond defaults."""
    try:
        import httpx
    except Exception:
        return 0, 0
    checked = dead = 0
    headers = {"User-Agent": "TaskSniffer-golden-set-check/1.0"}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        for url in urls:
            try:
                resp = client.head(url)
                if resp.status_code in (405, 403):
                    resp = client.get(url)
                checked += 1
                if resp.status_code >= 400:
                    dead += 1
            except Exception:
                checked += 1
                dead += 1
    return checked, dead


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, help="labeled CSV or JSONL file")
    parser.add_argument("--db", default="work_bot_hunter.db")
    parser.add_argument("--check-links", action="store_true", help="live-check stored source URLs")
    parser.add_argument("--out", default="", help="optional JSON summary output path")
    args = parser.parse_args()

    labels = _read_labels(Path(args.labels))
    conn = _connect_ro(_db_path(args.db))
    jobs = _fetch_jobs(conn)

    metrics: dict[str, dict[str, int]] = defaultdict(lambda: {"yes": 0, "no": 0, "na": 0, "skipped": 0})
    by_source: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"yes": 0, "no": 0, "na": 0, "skipped": 0})
    )
    missing_jobs = 0
    stored_app_urls: list[str] = []
    checked_source_urls: list[str] = []

    for row in labels:
        job_id = str(row.get("job_id") or row.get("id") or "").strip()
        job = jobs.get(job_id)
        if not job:
            missing_jobs += 1
            continue
        source = str(job.get("source") or row.get("source") or "unknown")

        # exact-match fields
        for metric, correct_field, label_field, stored_key in [
            ("title_exact_match", "title_correct", "label_title", "title"),
            ("company_exact_match", "company_correct", "label_company", "company"),
            ("location_exact_match", "location_correct", "label_location", "location"),
        ]:
            verdict = _correct(row, correct_field, label_field, job.get(stored_key))
            bucket = verdict if verdict else "skipped"
            metrics[metric][bucket] += 1
            by_source[source][metric][bucket] += 1

        # description present (where source provides it)
        dp = _yn(row.get("label_description_present"))
        if dp in ("yes", "y", "true", "1"):
            stored_present = bool((job.get("description") or "").strip())
            verdict = "yes" if stored_present else "no"
        elif dp in ("no", "n", "false", "0"):
            verdict = "no"
        elif dp in ("na", "n/a", "skip"):
            verdict = "na"
        else:
            verdict = "skipped"
        metrics["description_present"][verdict] += 1
        by_source[source]["description_present"][verdict] += 1

        # posted date present (where source provides it)
        pp = _yn(row.get("label_posted_at_provided"))
        if pp in ("yes", "y", "true", "1"):
            verdict = "yes" if job.get("posted_at") else "no"
        elif pp in ("no", "n", "false", "0"):
            verdict = "no"
        elif pp in ("na", "n/a", "skip"):
            verdict = "na"
        else:
            verdict = "skipped"
        metrics["posted_date_present"][verdict] += 1
        by_source[source]["posted_date_present"][verdict] += 1

        # application URL precision (among stored non-empty)
        stored_app = (job.get("application_url") or "").strip()
        if stored_app:
            stored_app_urls.append(stored_app)
            ac = _yn(row.get("label_application_url_correct"))
            if ac in ("yes", "y", "true", "1"):
                verdict = "yes"
            elif ac in ("no", "n", "false", "0"):
                verdict = "no"
            elif ac in ("na", "n/a", "skip"):
                verdict = "na"
            else:
                expected = str(row.get("label_application_url") or "").strip()
                if expected:
                    verdict = "yes" if _norm(expected) == _norm(stored_app) else "no"
                else:
                    verdict = "skipped"
            metrics["application_url_precision"][verdict] += 1
            by_source[source]["application_url_precision"][verdict] += 1

        if args.check_links:
            url = (job.get("source_url") or job.get("canonical_url") or "").strip()
            if url:
                checked_source_urls.append(url)

    # duplicate rate from current DB (visible rows)
    dup = conn.execute(
        """
        SELECT
          SUM(CASE WHEN fingerprint IS NOT NULL AND fingerprint != '' THEN 1 ELSE 0 END) AS fp_rows,
          COUNT(DISTINCT CASE WHEN fingerprint IS NOT NULL AND fingerprint != '' THEN fingerprint END) AS distinct_fp
        FROM jobs WHERE status != 'quarantined'
        """
    ).fetchone()
    fp_rows = int(dup["fp_rows"] or 0)
    distinct_fp = int(dup["distinct_fp"] or 0)
    duplicate_rows = fp_rows - distinct_fp
    duplicate_rate = _pct(duplicate_rows, fp_rows)

    # salary coverage from current DB (visible rows)
    sal = conn.execute(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN salary_min IS NOT NULL OR salary_max IS NOT NULL THEN 1 ELSE 0 END) AS with_salary FROM jobs WHERE status != 'quarantined'"
    ).fetchone()
    salary_cov = _pct(int(sal["with_salary"] or 0), int(sal["total"] or 0))

    dead_checked = dead_count = 0
    if args.check_links:
        # de-duplicate URLs
        dead_checked, dead_count = _check_links(sorted(set(checked_source_urls)))
    dead_rate = _pct(dead_count, dead_checked)

    conn.close()

    def rate_for(name: str) -> float | None:
        m = metrics[name]
        den = m["yes"] + m["no"]
        return _pct(m["yes"], den)

    summary = {
        "labels_total": len(labels),
        "jobs_missing_from_db": missing_jobs,
        "metrics": {},
        "by_source": {},
        "duplicate_rate_visible": duplicate_rate,
        "salary_coverage_visible": salary_cov,
        "dead_link_rate": dead_rate,
        "dead_link_checked": dead_checked,
        "dead_link_dead": dead_count,
    }

    for name in [
        "title_exact_match",
        "company_exact_match",
        "location_exact_match",
        "description_present",
        "posted_date_present",
        "application_url_precision",
    ]:
        m = metrics[name]
        summary["metrics"][name] = {
            "rate": rate_for(name),
            "yes": m["yes"],
            "no": m["no"],
            "na": m["na"],
            "skipped": m["skipped"],
            "denominator": m["yes"] + m["no"],
        }

    for source, sm in sorted(by_source.items()):
        summary["by_source"][source] = {}
        for name, m in sm.items():
            den = m["yes"] + m["no"]
            summary["by_source"][source][name] = {"rate": _pct(m["yes"], den), "yes": m["yes"], "no": m["no"], "na": m["na"], "skipped": m["skipped"]}

    # gate evaluation
    gates = []
    gate_checks = [
        ("title_exact_match", rate_for("title_exact_match"), GATES["title_exact_match"], ">="),
        ("company_exact_match", rate_for("company_exact_match"), GATES["company_exact_match"], ">="),
        ("location_exact_match", rate_for("location_exact_match"), GATES["location_exact_match"], ">="),
        ("description_present", rate_for("description_present"), GATES["description_present"], ">="),
        ("posted_date_present", rate_for("posted_date_present"), GATES["posted_date_present"], ">="),
        ("application_url_precision", rate_for("application_url_precision"), GATES["application_url_precision"], ">="),
        ("dead_link_rate", dead_rate, GATES["dead_link_rate_max"], "<="),
        ("duplicate_rate", duplicate_rate, GATES["duplicate_rate_max"], "<="),
    ]
    for name, value, target, op in gate_checks:
        if value is None:
            status = "n/a"
        elif op == ">=":
            status = "pass" if value >= target else "fail"
        else:
            status = "pass" if value <= target else "fail"
        gates.append({"gate": name, "value": value, "target": target, "op": op, "status": status})
    summary["gates"] = gates

    # pretty print
    print(f"labels={len(labels)} missing_jobs={missing_jobs}")
    print("\nMetrics:")
    for name in [
        "title_exact_match",
        "company_exact_match",
        "location_exact_match",
        "description_present",
        "posted_date_present",
        "application_url_precision",
    ]:
        m = summary["metrics"][name]
        print(f"  {name:24s} {_fmt(m['rate']):>6s}  (yes={m['yes']} no={m['no']} na={m['na']} skipped={m['skipped']})")
    print(f"  {'duplicate_rate_visible':24s} {_fmt(duplicate_rate):>6s}  (dup_rows={duplicate_rows} fp_rows={fp_rows})")
    print(f"  {'salary_coverage_visible':24s} {_fmt(salary_cov):>6s}  (reported)")
    if args.check_links:
        print(f"  {'dead_link_rate':24s} {_fmt(dead_rate):>6s}  (dead={dead_count} checked={dead_checked})")
    else:
        print(f"  {'dead_link_rate':24s}    n/a  (run with --check-links)")

    print("\nGates:")
    for g in gates:
        tgt = f"{g['op']} {g['target']:.0%}" if g['target'] < 1 else f"{g['op']} {g['target']:.1%}"
        print(f"  [{g['status']:4s}] {g['gate']:24s} {_fmt(g['value']):>6s}  target {tgt}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(f"\nwrote {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
