from __future__ import annotations

import hashlib
from typing import Any

from rapidfuzz import fuzz


class JobDeduplicator:
    """Find and merge duplicate jobs across sources."""

    def __init__(self, db_session: Any) -> None:
        self._db = db_session

    async def find_duplicates(self, job: dict[str, Any]) -> list[dict[str, Any]]:
        """Find existing jobs that are likely duplicates of the given job."""
        fingerprint = job.get("fingerprint", "")
        candidates: list[dict[str, Any]] = []

        if fingerprint:
            rows = await self._db.execute(
                "SELECT * FROM jobs WHERE fingerprint = :fp",
                {"fp": fingerprint},
            )
            candidates.extend(rows)

        title = job.get("title", "")
        company = job.get("company", "")
        if title and company:
            rows = await self._db.execute(
                "SELECT * FROM jobs WHERE title = :t AND company = :c",
                {"t": title, "c": company},
            )
            for row in rows:
                if row not in candidates:
                    candidates.append(row)

        similar: list[dict[str, Any]] = []
        for candidate in candidates:
            score = self._similarity_score(job, candidate)
            if score >= 80.0:
                similar.append({**candidate, "_match_score": score})

        similar.sort(key=lambda x: x.get("_match_score", 0), reverse=True)
        return similar

    async def is_duplicate(self, job: dict[str, Any]) -> bool:
        """Return True if the job already exists in the database."""
        duplicates = await self.find_duplicates(job)
        return len(duplicates) > 0

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

    async def merge_sources(self, canonical_id: str, new_source_id: str) -> None:
        """Merge a new source record into the canonical job, preserving provenance."""
        canonical = await self._db.execute_one(
            "SELECT * FROM jobs WHERE id = :id", {"id": canonical_id}
        )
        new_record = await self._db.execute_one(
            "SELECT * FROM jobs WHERE id = :id", {"id": new_source_id}
        )

        if not canonical or not new_record:
            return

        sources = canonical.get("sources", [])
        if isinstance(sources, str):
            sources = [s.strip() for s in sources.split(",") if s.strip()]

        new_source = new_record.get("source", "")
        if new_source and new_source not in sources:
            sources.append(new_source)

        merged_description = canonical.get("description", "")
        if not merged_description and new_record.get("description"):
            merged_description = new_record["description"]

        merged_skills = canonical.get("skills", [])
        if isinstance(merged_skills, str):
            merged_skills = [s.strip() for s in merged_skills.split(",")]
        new_skills = new_record.get("skills", [])
        if isinstance(new_skills, str):
            new_skills = [s.strip() for s in new_skills.split(",")]
        combined_skills = list(set(merged_skills + new_skills))

        salary_min = canonical.get("salary_min") or new_record.get("salary_min")
        salary_max = canonical.get("salary_max") or new_record.get("salary_max")
        salary_currency = canonical.get("salary_currency") or new_record.get("salary_currency")

        await self._db.execute(
            """UPDATE jobs SET
                sources = :sources,
                description = :desc,
                skills = :skills,
                salary_min = :salary_min,
                salary_max = :salary_max,
                salary_currency = :salary_currency,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id""",
            {
                "sources": ",".join(sources),
                "desc": merged_description,
                "skills": ",".join(combined_skills),
                "salary_min": salary_min,
                "salary_max": salary_max,
                "salary_currency": salary_currency,
                "id": canonical_id,
            },
        )

        await self._db.execute(
            "UPDATE jobs SET superseded_by = :canonical WHERE id = :id",
            {"canonical": canonical_id, "id": new_source_id},
        )

    async def deduplicate_batch(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deduplicate a batch of jobs, returning only unique ones with merged sources."""
        unique: list[dict[str, Any]] = []
        seen_fingerprints: dict[str, dict[str, Any]] = {}

        for job in jobs:
            fp = job.get("fingerprint", "")
            if fp in seen_fingerprints:
                existing = seen_fingerprints[fp]
                existing_sources = existing.get("sources", [])
                if isinstance(existing_sources, str):
                    existing_sources = [s.strip() for s in existing_sources.split(",")]
                new_source = job.get("source", "")
                if new_source and new_source not in existing_sources:
                    existing_sources.append(new_source)
                existing["sources"] = existing_sources
                continue

            existing_duplicates = await self.find_duplicates(job)
            if existing_duplicates:
                canonical = existing_duplicates[0]
                canonical_id = canonical.get("id", "")
                new_source = job.get("source", "")
                existing_sources = canonical.get("sources", [])
                if isinstance(existing_sources, str):
                    existing_sources = [s.strip() for s in existing_sources.split(",")]
                if new_source and new_source not in existing_sources:
                    existing_sources.append(new_source)
                canonical["sources"] = existing_sources

                db_canonical_id = canonical.get("db_id") or canonical_id
                if db_canonical_id:
                    await self.merge_sources(str(db_canonical_id), "")
                continue

            seen_fingerprints[fp] = job
            unique.append(job)

        return unique
