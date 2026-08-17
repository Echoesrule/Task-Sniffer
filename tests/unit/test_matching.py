"""Tests for matching engine."""

import asyncio

from backend.matching.engine import MatchingEngine
from backend.config import Settings


def test_strong_match():
    engine = MatchingEngine(Settings())
    job = {
        "title": "Senior Python Developer",
        "skills": ["python", "django", "postgresql", "docker", "git"],
        "experience_level": "senior",
        "location": "Nairobi",
        "country": "KE",
        "remote": True,
        "remote_type": "full",
        "salary_min": 200000,
        "salary_max": 350000,
        "salary_currency": "KES",
        "posted_at": "2025-01-15",
    }
    candidate = {
        "skills": ["python", "django", "postgresql", "docker", "git", "fastapi"],
        "experience_level": "senior",
        "preferred_locations": ["Nairobi", "Remote"],
        "remote_preference": "full",
        "salary_min": 180000,
        "salary_max": 400000,
        "salary_currency": "KES",
        "preferred_roles": ["python developer", "backend engineer"],
    }
    result = asyncio.run(engine.match(job, candidate))
    assert "total_score" in result
    assert result["total_score"] >= 0.5


def test_weak_match():
    engine = MatchingEngine(Settings())
    job = {
        "title": "Java Developer",
        "skills": ["java", "spring", "mysql"],
        "experience_level": "senior",
        "location": "Lagos",
        "country": "NG",
        "remote": False,
        "remote_type": "onsite",
        "salary_min": 500000,
        "salary_max": 800000,
        "salary_currency": "NGN",
        "posted_at": "2025-01-10",
    }
    candidate = {
        "skills": ["python", "django"],
        "experience_level": "junior",
        "preferred_locations": ["Nairobi"],
        "remote_preference": "full",
        "salary_min": 100000,
        "salary_max": 200000,
        "salary_currency": "KES",
        "preferred_roles": ["python developer"],
    }
    result = asyncio.run(engine.match(job, candidate))
    assert "total_score" in result
    assert result["total_score"] < 0.5


def test_explain_produces_output():
    engine = MatchingEngine(Settings())
    job = {
        "title": "Python Developer",
        "skills": ["python"],
        "experience_level": "mid",
        "location": "Nairobi",
        "country": "KE",
        "remote": True,
        "remote_type": "full",
        "salary_min": 100000,
        "salary_max": 200000,
        "salary_currency": "KES",
        "posted_at": "2025-01-15",
    }
    candidate = {
        "skills": ["python"],
        "experience_level": "mid",
        "preferred_locations": ["Nairobi"],
        "remote_preference": "full",
        "salary_min": 80000,
        "salary_max": 250000,
        "salary_currency": "KES",
        "preferred_roles": ["python developer"],
    }
    result = asyncio.run(engine.match(job, candidate))
    explanation = engine.explain_match(result)
    assert len(explanation) > 0
