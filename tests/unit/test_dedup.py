"""Tests for deduplication."""

import asyncio

from backend.models.database import Database, Job, Source
from backend.services.deduplicator import JobDeduplicator


def test_fingerprint_match():
    a = {"fingerprint": "abc123", "title": "Python Dev", "company": "Acme", "location": "Nairobi"}
    b = {"fingerprint": "abc123", "title": "Python Dev", "company": "Acme", "location": "Nairobi"}
    assert JobDeduplicator._fingerprint_match(a, b) is True


def test_fingerprint_mismatch():
    a = {"fingerprint": "abc123"}
    b = {"fingerprint": "xyz789"}
    assert JobDeduplicator._fingerprint_match(a, b) is False


def test_fingerprint_missing():
    a = {"title": "Python Dev"}
    b = {"title": "Python Dev"}
    assert JobDeduplicator._fingerprint_match(a, b) is False


def test_similarity_score_identical():
    a = {"title": "Senior Python Developer", "company": "Safaricom", "location": "Nairobi"}
    b = {"title": "Senior Python Developer", "company": "Safaricom", "location": "Nairobi"}
    score = JobDeduplicator._similarity_score(a, b)
    assert score >= 95


def test_similarity_score_different():
    a = {"title": "Senior Python Developer", "company": "Safaricom", "location": "Nairobi"}
    b = {"title": "Junior Java Developer", "company": "Google", "location": "Lagos"}
    score = JobDeduplicator._similarity_score(a, b)
    assert score < 50


# --- Phase 4: identity precedence + safe batch dedup ------------------------


def test_identity_keys_precedence():
    job = {
        "source": "greenhouse",
        "source_job_id": "42",
        "fingerprint": "fp1",
        "canonical_url": "https://job-boards.greenhouse.io/acme/jobs/42",
    }
    keys = JobDeduplicator.identity_keys(job)
    assert keys[0] == "source:greenhouse:42"
    assert "fp:fp1" in keys
    assert "url:https://job-boards.greenhouse.io/acme/jobs/42" in keys


def test_identity_keys_empty_for_barren_job():
    assert JobDeduplicator.identity_keys({}) == []


def test_deduplicate_batch_collapses_by_fingerprint():
    jobs = [
        {"title": "A", "company": "C", "fingerprint": "fp1", "source": "greenhouse", "sources": []},
        {"title": "A", "company": "C", "fingerprint": "fp1", "source": "ashby", "sources": []},
    ]
    out = JobDeduplicator.deduplicate_batch(jobs)
    assert len(out) == 1
    assert "ashby" in out[0]["sources"]


def test_deduplicate_batch_fuzzy_fallback():
    jobs = [
        {"title": "Senior Python Developer", "company": "Safaricom", "location": "Nairobi", "source": "a"},
        {"title": "Senior Python Developer", "company": "Safaricom", "location": "Nairobi", "source": "b"},
    ]
    out = JobDeduplicator.deduplicate_batch(jobs)
    assert len(out) == 1


def test_deduplicate_batch_keeps_distinct_jobs():
    jobs = [
        {"title": "Senior Python Developer", "company": "Safaricom", "location": "Nairobi"},
        {"title": "Junior Java Developer", "company": "Google", "location": "Lagos"},
    ]
    assert len(JobDeduplicator.deduplicate_batch(jobs)) == 2


def test_find_duplicates_uses_orm(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'dedup.db'}")

    async def go():
        await db.init_db()
        async with db.async_session_factory() as session:
            source = Source(name="greenhouse", url="https://example.invalid")
            session.add(source)
            await session.flush()
            session.add(
                Job(
                    source_id=source.id,
                    source_job_id="42",
                    title="Backend Engineer",
                    company="Acme",
                    fingerprint="fp1",
                    canonical_url="https://job-boards.greenhouse.io/acme/jobs/42",
                    source_url="https://job-boards.greenhouse.io/acme/jobs/42",
                    url_status="VALID",
                )
            )
            await session.commit()

            dedup = JobDeduplicator(session)
            assert len(await dedup.find_duplicates({"fingerprint": "fp1"})) == 1
            assert len(await dedup.find_duplicates(
                {"canonical_url": "https://job-boards.greenhouse.io/acme/jobs/42"}
            )) == 1
            assert await dedup.is_duplicate({"fingerprint": "fp1"}) is True
            assert await dedup.find_duplicates(
                {"fingerprint": "other", "canonical_url": "https://x/y"}
            ) == []
        await db.close()

    asyncio.run(go())

