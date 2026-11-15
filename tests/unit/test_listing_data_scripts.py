"""Tests for the listing data-quality report and repair scripts."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import data_quality_report as report_script  # noqa: E402
import repair_listing_data as repair  # noqa: E402


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE sources (id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER)"
    )
    conn.execute(
        """CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            source_id INTEGER,
            title TEXT,
            company TEXT,
            location TEXT,
            description TEXT,
            posted_at TEXT,
            closing_at TEXT,
            salary_min INTEGER,
            salary_max INTEGER,
            salary_currency TEXT,
            application_url TEXT,
            source_url TEXT,
            canonical_url TEXT,
            final_url TEXT,
            url_status TEXT,
            fingerprint TEXT,
            status TEXT,
            remote_type TEXT
        )"""
    )
    conn.executemany(
        "INSERT INTO sources (id, name, enabled) VALUES (?, ?, ?)",
        [(1, "jobicy", 1), (2, "myjobmag", 0)],
    )
    conn.executemany(
        "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "good", 1, "Backend Engineer", "Acme", "Germany",
                "Python role", "2026-11-15", None, 100, 200, "EUR",
                "https://jobicy.com/apply/1", "https://jobicy.com/jobs/1",
                "https://jobicy.com/jobs/1", "https://jobicy.com/jobs/1",
                "VALID", "fp1", "discovered", "remote",
            ),
            (
                "bad-app", 1, "Engineer", "Acme", "Germany",
                "Python role", None, None, None, None, None,
                "https://jobicy.com/submit-guest-post",
                "https://jobicy.com/jobs/2", "https://jobicy.com/jobs/2",
                "https://jobicy.com/jobs/2", "VALID", "fp2", "discovered", None,
            ),
            (
                "bad-currency", 2, "Lecturer", "", "Nairobi",
                "", None, None, None, None, "KES", None,
                "https://myjobmag.co.ke/job/3", "https://myjobmag.co.ke/job/3",
                "https://myjobmag.co.ke/job/3", "NEEDS_REVIEW", "fp3",
                "discovered", None,
            ),
        ],
    )
    conn.commit()
    conn.close()


def test_quality_report_flags_bad_application_url_and_currency(tmp_path):
    db = tmp_path / "quality.db"
    _make_db(db)

    conn = report_script._connect_ro(db)
    try:
        report = report_script._report(conn)
    finally:
        conn.close()

    assert report["totals"]["jobs"] == 3
    jobicy = report["sources"]["jobicy"]
    assert jobicy["quality_flags"]["site_wide_application_url"] == 1
    assert jobicy["application_urls"]["top_repeated"] == []

    myjobmag = report["sources"]["myjobmag"]
    assert myjobmag["quality_flags"]["currency_without_amount"] == 1
    assert myjobmag["quality_flags"]["location_default_nairobi"] == 1
    assert myjobmag["completeness"]["description"] == 0.0


def test_repair_plan_and_apply_fix_existing_rows(tmp_path):
    db = tmp_path / "repair.db"
    _make_db(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    plan = repair.build_plan(conn)
    assert plan["application_url_fixes"] == ["bad-app"]
    assert plan["currency_fixes"] == ["bad-currency"]
    assert plan["quarantine_fixes"] == ["bad-currency"]
    assert plan["quarantine_sources"] == {"myjobmag": 1}

    # build_plan is read-only
    before = conn.execute(
        "SELECT application_url, salary_currency, status FROM jobs WHERE id='bad-app'"
    ).fetchone()
    assert before["application_url"] == "https://jobicy.com/submit-guest-post"

    repair.apply_plan(conn, plan)
    rows = {
        row["id"]: dict(row)
        for row in conn.execute(
            "SELECT id, application_url, salary_currency, status, location FROM jobs"
        )
    }
    conn.close()

    assert rows["bad-app"]["application_url"] is None
    assert rows["bad-currency"]["salary_currency"] is None
    assert rows["bad-currency"]["status"] == "quarantined"
    assert rows["bad-currency"]["location"] == "Nairobi"  # opt-in only
    assert rows["good"]["status"] == "discovered"


def test_repair_plan_can_clear_known_fabricated_location(tmp_path):
    db = tmp_path / "location.db"
    _make_db(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    plan = repair.build_plan(
        conn, clear_nairobi=True, location_sources={"myjobmag"}
    )
    repair.apply_plan(conn, plan)
    location = conn.execute(
        "SELECT location FROM jobs WHERE id='bad-currency'"
    ).fetchone()["location"]
    conn.close()

    assert location is None


def test_repair_plan_skips_quarantine_when_disabled(tmp_path):
    db = tmp_path / "noquarantine.db"
    _make_db(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    plan = repair.build_plan(conn, quarantine_disabled=False)
    conn.close()

    assert plan["quarantine_fixes"] == []
