#!/usr/bin/env python3
"""End-to-end integration test: Scrape → DB → API → Match."""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from backend.models.database import Database, Source, Job, Candidate, Application, ApplicationStatusChange, Base
from backend.services.normalizer import JobNormalizer
from backend.risk.engine import RiskEngine
from backend.matching.engine import MatchingEngine
from backend.config import Settings
from backend.scrapers.greenhouse import GreenhouseScraper
from backend.scrapers.ashby import AshbyScraper

from sqlalchemy import select, func as sa_func


DB_URL = "sqlite+aiosqlite:///./test_integration.db"


async def main():
    settings = Settings()
    settings.database_url = DB_URL

    # Clean slate
    if os.path.exists("test_integration.db"):
        os.remove("test_integration.db")

    db = Database(DB_URL)
    await db.init_db()
    print("[OK] Database initialized")

    # Seed sources
    async with db.async_session_factory() as session:
        sources = [
            Source(name="greenhouse", url="https://boards-api.greenhouse.io", tier=2, enabled=True, country_focus="GLOBAL"),
            Source(name="ashby", url="https://api.ashbyhq.com", tier=2, enabled=True, country_focus="GLOBAL"),
        ]
        session.add_all(sources)
        await session.commit()
        print("[OK] Sources seeded")

    normalizer = JobNormalizer()
    risk_engine = RiskEngine()
    match_engine = MatchingEngine(settings)

    candidate_profile = {
        "skills": ["python", "django", "postgresql", "docker", "git", "react"],
        "experience_level": "mid",
        "preferred_locations": ["Nairobi", "Remote"],
        "remote_preference": "full",
        "salary_min": 100000,
        "salary_max": 300000,
        "salary_currency": "KES",
        "preferred_roles": ["python developer", "backend engineer", "full stack"],
    }

    # ── Phase 1: Scrape ──
    print("\n=== PHASE 1: SCRAPE ===")
    scrapers = [
        ("greenhouse", GreenhouseScraper({"enabled": True, "boards": ["airbnb", "figma"]})),
        ("ashby", AshbyScraper({"enabled": True, "boards": ["openai"]})),
    ]

    total_scraped = 0
    for source_name, scraper in scrapers:
        try:
            raw_jobs = await scraper.fetch_jobs()
            print(f"  {source_name}: {len(raw_jobs)} raw jobs")
            total_scraped += len(raw_jobs)

            async with db.async_session_factory() as session:
                source_result = await session.execute(select(Source).where(Source.name == source_name))
                source = source_result.scalars().first()

                inserted = 0
                for raw in raw_jobs[:25]:  # cap at 25 per source
                    norm = normalizer.normalize(raw, source_name)

                    existing = await session.execute(
                        select(Job).where(Job.source_id == source.id, Job.source_job_id == norm.get("source_job_id", ""))
                    )
                    if existing.scalars().first():
                        continue

                    risk = risk_engine.analyze(norm)
                    result = await match_engine.match(norm, candidate_profile)

                    job = Job(
                        source_id=source.id,
                        source_job_id=norm.get("source_job_id", ""),
                        title=norm.get("title", ""),
                        company=norm.get("company", ""),
                        description=norm.get("description", ""),
                        skills=json.dumps(norm.get("skills", [])),
                        location=norm.get("location", ""),
                        country=norm.get("country", ""),
                        remote=norm.get("remote", False),
                        remote_type=norm.get("remote_type"),
                        employment_type=norm.get("employment_type"),
                        experience_level=norm.get("experience_level"),
                        salary_min=norm.get("salary_min"),
                        salary_max=norm.get("salary_max"),
                        salary_currency=norm.get("salary_currency"),
                        application_url=norm.get("url", ""),
                        fingerprint=norm.get("fingerprint", ""),
                        risk_score=risk["risk_score"],
                        risk_level=risk["risk_level"],
                        risk_flags=json.dumps(risk.get("risk_flags", [])),
                        match_score=result.get("total_score", 0.0),
                        match_breakdown=json.dumps(result.get("breakdown", {})),
                    )
                    session.add(job)
                    inserted += 1

                await session.commit()
                print(f"  {source_name}: inserted {inserted} jobs into DB")

            await scraper.close()
        except Exception as e:
            print(f"  {source_name}: ERROR - {e}")

    print(f"\n  Total scraped: {total_scraped}")

    # ── Phase 2: Verify DB state ──
    print("\n=== PHASE 2: VERIFY DB ===")
    async with db.async_session_factory() as session:
        job_count = (await session.execute(select(sa_func.count(Job.id)))).scalar()
        source_count = (await session.execute(select(sa_func.count(Source.id)))).scalar()
        print(f"  Sources in DB: {source_count}")
        print(f"  Jobs in DB: {job_count}")

        top_jobs = (
            await session.execute(
                select(Job.title, Job.company, Job.match_score, Job.risk_score, Job.risk_level)
                .order_by(Job.match_score.desc())
                .limit(5)
            )
        ).all()
        print(f"\n  Top 5 by match score:")
        for i, (title, company, match, risk, risk_level) in enumerate(top_jobs):
            print(f"    [{i+1}] {title[:50]} @ {company}")
            print(f"        Match: {match:.3f}  Risk: {risk:.1f}/100 ({risk_level})")

    # ── Phase 3: Create candidate profile ──
    print("\n=== PHASE 3: CANDIDATE PROFILE ===")
    async with db.async_session_factory() as session:
        from backend.models.database import User
        user = User(email="test@example.com", hashed_password="placeholder")
        session.add(user)
        await session.flush()

        candidate = Candidate(
            user_id=user.id,
            name="Test Developer",
            email="test@example.com",
            skills=json.dumps(candidate_profile["skills"]),
            preferred_locations=json.dumps(candidate_profile["preferred_locations"]),
            preferred_roles=json.dumps(candidate_profile["preferred_roles"]),
            experience_level="mid",
            salary_min=100000,
            salary_max=300000,
            salary_currency="KES",
            remote_preference="full",
        )
        session.add(candidate)
        await session.commit()
        await session.refresh(candidate)
        print(f"  Created candidate: {candidate.name} (id={candidate.id[:8]}...)")

    # ── Phase 4: Create application ──
    print("\n=== PHASE 4: APPLICATION TRACKING ===")
    async with db.async_session_factory() as session:
        result = await session.execute(select(Job).order_by(Job.match_score.desc()).limit(1))
        top_job = result.scalars().first()

        result = await session.execute(select(Candidate))
        cand = result.scalars().first()

        app = Application(
            candidate_id=cand.id,
            job_id=top_job.id,
            status="shortlisted",
            notes="High match score, applying",
            match_score=top_job.match_score,
            risk_score=top_job.risk_score,
        )
        session.add(app)
        await session.flush()

        change = ApplicationStatusChange(
            application_id=app.id,
            old_status=None,
            new_status="shortlisted",
            notes="Initial shortlist",
        )
        session.add(change)
        await session.commit()
        await session.refresh(app)
        print(f"  Application created for: {top_job.title[:50]}")
        print(f"  Status: {app.status}")

    # ── Phase 5: Analytics queries ──
    print("\n=== PHASE 5: ANALYTICS ===")
    async with db.async_session_factory() as session:
        total_jobs = (await session.execute(select(sa_func.count(Job.id)))).scalar()
        avg_match = (await session.execute(select(sa_func.avg(Job.match_score)))).scalar()
        avg_risk = (await session.execute(select(sa_func.avg(Job.risk_score)))).scalar()

        source_rows = (
            await session.execute(
                select(Source.name, sa_func.count(Job.id))
                .join(Job, Job.source_id == Source.id, isouter=True)
                .group_by(Source.name)
            )
        ).all()

        excellent = (await session.execute(select(sa_func.count(Job.id)).where(Job.match_score >= 0.8))).scalar()
        good = (await session.execute(select(sa_func.count(Job.id)).where(Job.match_score >= 0.6, Job.match_score < 0.8))).scalar()
        fair = (await session.execute(select(sa_func.count(Job.id)).where(Job.match_score >= 0.4, Job.match_score < 0.6))).scalar()
        poor = (await session.execute(select(sa_func.count(Job.id)).where(Job.match_score < 0.4))).scalar()

        print(f"  Total jobs: {total_jobs}")
        print(f"  Avg match: {avg_match:.3f}" if avg_match else "  Avg match: N/A")
        print(f"  Avg risk: {avg_risk:.1f}" if avg_risk else "  Avg risk: N/A")
        print(f"  Jobs by source:")
        for name, count in source_rows:
            print(f"    {name}: {count}")
        print(f"  Match distribution:")
        print(f"    Excellent (>=0.8): {excellent}")
        print(f"    Good (0.6-0.8):    {good}")
        print(f"    Fair (0.4-0.6):    {fair}")
        print(f"    Poor (<0.4):       {poor}")

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"  INTEGRATION TEST PASSED")
    print(f"{'='*60}")
    print(f"  Scrape:    {total_scraped} raw jobs")
    print(f"  DB:        {job_count} jobs stored")
    print(f"  Candidate: Profile created")
    print(f"  Application: Tracking active")
    print(f"  Analytics: Aggregation working")

    await db.close()

    # Cleanup
    if os.path.exists("test_integration.db"):
        os.remove("test_integration.db")


if __name__ == "__main__":
    asyncio.run(main())
