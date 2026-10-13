"""Deduplication helpers (Phase 4 repair).

The ingestion engine performs its own dedup in
:meth:`backend.services.ingestion.IngestionEngine._persist_job`, in a fixed
precedence order:

    1. same source + ``source_job_id``             (exact re-scrape)
    2. cross-source ``fingerprint``                (normalized identity)
    3. exact ``canonical_url`` / ``original_url``  (conservative URL identity)

This module exposes the same precedence as reusable, testable helpers plus a
side-effect-free batch deduplicator.

The previous implementation issued raw SQL strings against a SQLAlchemy
``AsyncSession`` and called a non-existent ``execute_one`` method, referenced
columns (``sources``, ``superseded_by``, ``skills``, ``updated_at``) that do not
exist on the current ``Job`` model, and was unused by the pipeline. It has been
repaired to operate on the current ORM schema. Merging is non-destructive: no
row is deleted and provenance is preserved.
"""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Job

#: fuzzy title/company/location similarity above which two jobs are considered
#: duplicates when no exact identity key matches.
SIMILARITY_THRESHOLD = 80.0


class JobDeduplicator:
    """Find and merge duplicate jobs across sources."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    # ------------------------------------------------------------------
    # identity precedence (shared with the engine)
    # ------------------------------------------------------------------

    @staticmethod
    def identity_keys(job: dict[str, Any]) -> list[str]:
        """Return ordered, exact-match identity keys for a normalized job.

        Order mirrors the engine: source-scoped id, then fingerprint, then the
        canonical/original URL. Only exact matches are produced here; fuzzy
        matching is applied separately and deliberately lower-confidence.
        """
        keys: list[str] = []
        source = job.get("source")
        source_job_id = job.get("source_job_id")
        if source and source_job_id:
            keys.append(f"source:{source}:{source_job_id}")
        fingerprint = job.get("fingerprint")
        if fingerprint:
            keys.append(f"fp:{fingerprint}")
        url = job.get("canonical_url") or job.get("source_url")
        if url:
            keys.append(f"url:{url}")
        return keys

    async def find_duplicates(self, job: dict[str, Any]) -> list[Job]:
        """Return existing ``Job`` rows that likely duplicate ``job``.

        Exact identities (fingerprint, exact URL, source-scoped id) are checked
        first; fuzzy similarity is only used to rank the exact candidates and
        never to broaden the candidate set by itself.
        """
        candidates: dict[str, Job] = {}

        fingerprint = job.get("fingerprint")
        if fingerprint:
            rows = (
                await self._db.execute(select(Job).where(Job.fingerprint == fingerprint))
            ).scalars().all()
            for row in rows:
                candidates[row.id] = row

        url = job.get("canonical_url") or job.get("source_url")
        if url:
            rows = (
                await self._db.execute(
                    select(Job).where(
                        or_(Job.canonical_url == url, Job.original_url == url)
                    )
                )
            ).scalars().all()
            for row in rows:
                candidates[row.id] = row

        source_id = job.get("source_id")
        source_job_id = job.get("source_job_id")
        if source_id and source_job_id:
            rows = (
                await self._db.execute(
                    select(Job).where(
                        Job.source_id == source_id,
                        Job.source_job_id == source_job_id,
                    )
                )
            ).scalars().all()
            for row in rows:
                candidates[row.id] = row

        scored: list[tuple[float, Job]] = []
        for row in candidates.values():
            scored.append((self._similarity_score(job, self._as_dict(row)), row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [row for _score, row in scored]

    async def is_duplicate(self, job: dict[str, Any]) -> bool:
        """Return True if the job already exists in the database."""
        return bool(await self.find_duplicates(job))

    async def merge_sources(self, canonical: Job, duplicate: Job) -> Job:
        """Merge ``duplicate`` into ``canonical`` without deleting either row.

        Provenance is unioned and empty descriptive/salary fields on the
        canonical row are filled from the duplicate. This is reversible and
        never destroys the duplicate record.
        """
        if canonical is None or duplicate is None or canonical.id == duplicate.id:
            return canonical

        provenances = canonical.provenances_list
        seen = {p.get("source") for p in provenances}
        for prov in duplicate.provenances_list:
            if prov.get("source") not in seen:
                provenances.append(prov)
                seen.add(prov.get("source"))
        if duplicate.source is not None and duplicate.source.name not in seen:
            provenances.append({
                "source": duplicate.source.name,
                "source_url": duplicate.source_url or "",
                "seen_at": "",
            })
        canonical.provenances_list = provenances

        for field in ("description", "salary_min", "salary_max", "salary_currency"):
            if not getattr(canonical, field, None) and getattr(duplicate, field, None):
                setattr(canonical, field, getattr(duplicate, field))
        return canonical

    @classmethod
    def deduplicate_batch(
        cls, jobs: list[dict[str, Any]], *, threshold: float = SIMILARITY_THRESHOLD
    ) -> list[dict[str, Any]]:
        """Collapse a batch of job dicts, returning unique ones (pure function).

        Exact identity keys win; fuzzy similarity is only consulted when no
        exact key matches. Duplicates have their ``sources`` unioned onto the
        surviving record. No database access.
        """
        unique: list[dict[str, Any]] = []
        seen: dict[str, dict[str, Any]] = {}

        for job in jobs:
            keys = cls.identity_keys(job)
            match = next((seen[k] for k in keys if k in seen), None)
            if match is None:
                match = next(
                    (u for u in unique if cls._similarity_score(u, job) >= threshold),
                    None,
                )

            if match is not None:
                cls._union_sources(match, job)
                for key in keys:
                    seen.setdefault(key, match)
                continue

            unique.append(job)
            for key in keys:
                seen[key] = job

        return unique

    # ------------------------------------------------------------------
    # static helpers (preserved: public behaviour relied upon by tests)
    # ------------------------------------------------------------------

    @staticmethod
    def _fingerprint_match(a: dict[str, Any], b: dict[str, Any]) -> bool:
        fp_a = a.get("fingerprint", "")
        fp_b = b.get("fingerprint", "")
        if fp_a and fp_b and fp_a == fp_b:
            return True
        if fp_a and fp_b:
            return False
        return False

    @staticmethod
    def _similarity_score(a: dict[str, Any], b: dict[str, Any]) -> float:
        parts_a = [
            a.get("title", ""),
            a.get("company", ""),
            a.get("location", ""),
        ]
        parts_b = [
            b.get("title", ""),
            b.get("company", ""),
            b.get("location", ""),
        ]

        scores: list[float] = []
        for text_a, text_b in zip(parts_a, parts_b):
            if text_a and text_b:
                scores.append(fuzz.ratio(text_a.lower(), text_b.lower()))

        combined_a = " ".join(parts_a).lower()
        combined_b = " ".join(parts_b).lower()
        if combined_a and combined_b:
            scores.append(fuzz.token_sort_ratio(combined_a, combined_b))

        title_a = a.get("title", "").lower()
        title_b = b.get("title", "").lower()
        if title_a and title_b:
            scores.append(fuzz.partial_ratio(title_a, title_b) * 0.8)
            scores.append(fuzz.token_set_ratio(title_a, title_b) * 0.9)

        if not scores:
            return 0.0

        return sum(scores) / len(scores)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    @staticmethod
    def _as_dict(job: Job) -> dict[str, Any]:
        return {
            "title": job.title or "",
            "company": job.company or "",
            "location": job.location or "",
        }

    @staticmethod
    def _union_sources(target: dict[str, Any], other: dict[str, Any]) -> None:
        sources = target.get("sources", [])
        if isinstance(sources, str):
            sources = [s.strip() for s in sources.split(",") if s.strip()]
        new_source = other.get("source", "")
        if new_source and new_source not in sources:
            sources.append(new_source)
        target["sources"] = sources
