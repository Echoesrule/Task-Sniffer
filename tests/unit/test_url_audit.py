"""Phase 4: read-only historical URL audit (spec part 4)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import audit_job_urls as audit  # noqa: E402


def _make_current_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE jobs (
            id INTEGER PRIMARY KEY,
            source TEXT,
            source_job_id TEXT,
            title TEXT,
            company TEXT,
            url_status TEXT,
            source_url TEXT,
            canonical_url TEXT,
            original_url TEXT,
            final_url TEXT,
            application_url TEXT
        )"""
    )
    # good: canonical greenhouse posting
    conn.execute(
        "INSERT INTO jobs VALUES (1,'greenhouse','1','A','Acme','VALID',"
        "'https://job-boards.greenhouse.io/acme/jobs/1',"
        "'https://job-boards.greenhouse.io/acme/jobs/1',"
        "'https://job-boards.greenhouse.io/acme/jobs/1',"
        "'https://job-boards.greenhouse.io/acme/jobs/1',NULL)"
    )
    # bad: no source_url, only a company application URL; board slug unknown
    conn.execute(
        "INSERT INTO jobs VALUES (2,'greenhouse','7995153','B','Airbnb','NEEDS_REVIEW',"
        "NULL,NULL,NULL,NULL,'https://careers.airbnb.com/positions/7995153')"
    )
    conn.commit()
    conn.close()


def _make_legacy_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY, source TEXT, title TEXT, company TEXT, url TEXT)"
    )
    conn.execute("INSERT INTO jobs VALUES (1,'greenhouse','A','Acme','https://job-boards.greenhouse.io/acme/jobs/1')")
    conn.execute("INSERT INTO jobs VALUES (2,'greenhouse','B','Stripe','https://stripe.com/jobs/search?gh_jid=42')")
    conn.commit()
    conn.close()


def test_detect_schema_current(tmp_path):
    db = tmp_path / "current.db"
    _make_current_db(db)
    conn = audit._connect_ro(db)
    try:
        schema, fields = audit._detect_schema(conn)
    finally:
        conn.close()
    assert schema == "current"
    assert "source_url" in fields


def test_detect_schema_legacy(tmp_path):
    db = tmp_path / "legacy.db"
    _make_legacy_db(db)
    conn = audit._connect_ro(db)
    try:
        schema, fields = audit._detect_schema(conn)
    finally:
        conn.close()
    assert schema == "legacy"
    assert "url" in fields


def test_audit_current_db_is_read_only_and_flags_missing_source_url(tmp_path):
    db = tmp_path / "current.db"
    _make_current_db(db)
    before = db.stat().st_mtime

    report = audit.audit(db)

    assert report["read_only"] is True
    assert report["total_jobs"] == 2
    assert db.stat().st_mtime == before  # no writes

    by_id = {f["id"]: f for f in report["findings"]}
    assert by_id[1]["proposed_action"] == "none"
    assert by_id[2]["proposed_action"] == "manual_review"
    assert "missing_source_url" in by_id[2]["issues"]
    assert by_id[2]["proposed_url"] is None
    assert report["actions"]["manual_review"] == 1


def test_audit_legacy_db_flags_gh_jid_without_board_slug(tmp_path):
    db = tmp_path / "legacy.db"
    _make_legacy_db(db)

    report = audit.audit(db)

    assert report["schema"] == "legacy"
    by_id = {f["id"]: f for f in report["findings"]}
    assert by_id[1]["proposed_action"] == "none"
    assert by_id[2]["proposed_action"] == "manual_review"
    assert "gh_jid_without_board_slug" in by_id[2]["issues"]


def test_analyse_never_proposes_a_guessed_url():
    urls = {"application_url": "https://careers.airbnb.com/positions/7995153"}
    finding = audit._analyse(urls, source="greenhouse", source_job_id="7995153")
    assert finding["proposed_url"] is None
    assert finding["proposed_action"] in {"manual_review", "re-scrape"}
