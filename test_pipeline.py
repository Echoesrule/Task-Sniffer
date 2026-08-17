"""Pipeline test - runs scrapers, normalizer, and analysis engine."""

import asyncio
import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("test_pipeline")

from src.normalizer import JobNormalizer
from src.analysis import JobAnalysisEngine
from src.config import config

normalizer = JobNormalizer()
analysis_engine = JobAnalysisEngine()


def get_default_prefs() -> dict:
    filters = config.filters
    return {
        "keywords": filters.get("keywords", []),
        "exclude_keywords": filters.get("exclude_keywords", []),
        "min_salary": filters.get("min_salary", 0),
        "tech_stack": filters.get("keywords", []),
        "remote_only": filters.get("remote_only", True),
        "job_types": filters.get("job_types", ["full_time", "contract"]),
    }


async def test_api_scraper(name: str, scraper_cls, cfg: dict):
    """Test a single API-based scraper."""
    print(f"\n{'='*60}")
    print(f"  Testing: {name}")
    print(f"{'='*60}")

    scraper = scraper_cls(cfg)
    try:
        jobs = await scraper.run()
        print(f"  Raw jobs scraped: {len(jobs)}")

        if not jobs:
            print("  No jobs returned, skipping analysis")
            return

        prefs = get_default_prefs()
        analyzed = analysis_engine.analyze_batch(jobs[:5], prefs)

        for i, job in enumerate(analyzed):
            print(f"\n  --- Job {i+1} ---")
            print(f"  Title:    {job.get('title', '?')}")
            print(f"  Company:  {job.get('company', '?')}")
            print(f"  URL:      {job.get('url', '?')[:80]}")
            print(f"  Remote:   {job.get('remote', '?')}")
            print(f"  Tech:     {', '.join(job.get('tech_stack', [])[:5]) or 'N/A'}")
            print(f"  Salary:   {job.get('salary_min', '?')} - {job.get('salary_max', '?')}")
            print(f"  Match:    {job.get('match_score', 0):.1f}/100 ({job.get('match_level', '?')})")
            print(f"  Risk:     {job.get('risk_score', 0)}/100 ({job.get('risk_level', '?')})")
            print(f"  Apply?    {'YES' if job.get('should_apply') else 'NO'}")
            if job.get("risk_flags"):
                for flag in job["risk_flags"]:
                    print(f"  ⚠ Flag:   {flag['reason']} (severity {flag['severity']})")

    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        await scraper.client.aclose()


async def test_scraper_pipeline():
    """Test each scraper individually."""
    sources = config.sources
    prefs = get_default_prefs()

    print("Default preferences:")
    print(f"  Keywords:  {prefs['keywords']}")
    print(f"  Min salary: ${prefs['min_salary']:,}")
    print(f"  Remote only: {prefs['remote_only']}")
    print(f"  Exclude:   {prefs['exclude_keywords']}")

    from src.scrapers.jobicy import JobicyScraper
    from src.scrapers.greenhouse import GreenhouseScraper
    from src.scrapers.ashby import AshbyScraper
    from src.scrapers.lever import LeverScraper

    api_scrapers = [
        ("jobicy", JobicyScraper, sources.get("jobicy", {})),
        ("greenhouse", GreenhouseScraper, sources.get("greenhouse", {})),
        ("ashby", AshbyScraper, sources.get("ashby", {})),
        ("lever", LeverScraper, sources.get("lever", {})),
    ]

    for name, cls, cfg in api_scrapers:
        if cfg.get("enabled", True):
            await test_api_scraper(name, cls, cfg)


async def test_analysis_engine():
    """Test analysis engine with sample jobs."""
    print(f"\n{'='*60}")
    print(f"  Analysis Engine Unit Tests")
    print(f"{'='*60}")

    prefs = get_default_prefs()
    ae = JobAnalysisEngine()

    good_job = {
        "title": "Senior Python Developer",
        "company": "TechCorp",
        "url": "https://example.com/jobs/1",
        "description": "Python, Django, PostgreSQL, Docker required. Remote position.",
        "tech_stack": ["python", "django", "postgresql", "docker"],
        "remote": True,
        "salary_min": 120000,
        "salary_max": 180000,
        "job_type": "full_time",
    }

    scam_job = {
        "title": "Mystery Shopper - Earn $500/day",
        "company": "",
        "url": "https://suspicious.xyz/apply-now",
        "description": "Send money to get started. Earn guaranteed income! Act now, limited time!",
        "tech_stack": [],
        "remote": True,
        "salary_min": None,
        "salary_max": None,
        "job_type": "full_time",
    }

    marginal_job = {
        "title": "Junior React Developer",
        "company": "StartupInc",
        "url": "https://example.com/jobs/3",
        "description": "React, JavaScript, some Node.js.",
        "tech_stack": ["react", "javascript", "node"],
        "remote": False,
        "salary_min": 50000,
        "salary_max": 70000,
        "job_type": "full_time",
    }

    test_cases = [
        ("Good match (Python, remote, high salary)", good_job),
        ("Scam listing (mystery shopper, asks for money)", scam_job),
        ("Marginal (junior, low salary, not remote)", marginal_job),
    ]

    for label, job in test_cases:
        result = ae.analyze(job, prefs)
        print(f"\n  {label}")
        print(f"    Match: {result['match_score']:.1f}/100 ({result['match_level']})")
        print(f"    Risk:  {result['risk_score']}/100 ({result['risk_level']})")
        print(f"    Apply: {'YES' if result['should_apply'] else 'NO'}")
        if result["risk_flags"]:
            for f in result["risk_flags"]:
                print(f"    ⚠ {f['reason']}")


async def main():
    print("=" * 60)
    print("  WORK HUNTER BOT - Pipeline Test")
    print("=" * 60)

    await test_analysis_engine()
    await test_scraper_pipeline()

    print(f"\n{'='*60}")
    print("  Tests complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
