"""Tests for job normalizer."""

from backend.services.normalizer import JobNormalizer


def test_normalize_title():
    n = JobNormalizer()
    job = {"title": "  Senior Python Developer  "}
    result = n.normalize(job, "test")
    assert result["title"] == "Senior Python Developer"


def test_normalize_title_expands_abbreviations():
    n = JobNormalizer()
    job = {"title": "Sr. Backend Engineer"}
    result = n.normalize(job, "test")
    assert "Senior" in result["title"]


def test_normalize_company():
    n = JobNormalizer()
    job = {"title": "Dev", "company": "  Acme CORP  "}
    result = n.normalize(job, "test")
    assert "Acme" in result["company"]
    assert "CORP" in result["company"]


def test_normalize_url():
    n = JobNormalizer()
    job = {"title": "Dev", "url": "https://example.com/jobs/123"}
    result = n.normalize(job, "test")
    assert result["url"] == "https://example.com/jobs/123"


def test_normalize_kenya_location():
    n = JobNormalizer()
    job = {"title": "Dev", "location": "nairobi"}
    result = n.normalize(job, "test")
    assert result["location"] != ""


def test_fingerprint_deterministic():
    n = JobNormalizer()
    fp1 = n.generate_fingerprint("Acme Corp", "Python Developer", "Nairobi")
    fp2 = n.generate_fingerprint("Acme Corp", "Python Developer", "Nairobi")
    assert fp1 == fp2


def test_fingerprint_differs():
    n = JobNormalizer()
    fp1 = n.generate_fingerprint("Acme Corp", "Python Developer", "Nairobi")
    fp2 = n.generate_fingerprint("Acme Corp", "Java Developer", "Nairobi")
    assert fp1 != fp2


def test_normalize_skills():
    n = JobNormalizer()
    job = {"title": "Dev", "skills": ["python", "PY3", "unknownskill"]}
    result = n.normalize(job, "test")
    assert "python" in result["skills"]
