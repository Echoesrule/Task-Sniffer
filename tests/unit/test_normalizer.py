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


def test_normalize_extracts_skills_from_description():
    """Regression: a job with only a description must still yield skills."""
    n = JobNormalizer()
    job = {
        "title": "Backend Engineer",
        "description": "Requirements: Strong Python and Django. Experience with Docker. AWS a plus.",
    }
    result = n.normalize(job, "test")
    assert {"python", "django", "docker"} <= set(result["skills"])
    assert "aws" in result["skills_preferred"]
    assert "python" in result["skills_required"]
    assert result["skills_detail"]


def test_normalize_unions_provided_and_extracted():
    n = JobNormalizer()
    job = {"title": "Dev", "skills": ["golang"], "description": "We use Python daily."}
    result = n.normalize(job, "test")
    assert {"go", "python"} <= set(result["skills"])


# ---------------------------------------------------------------------------
# Data-accuracy regressions: no fabricated facts, no lost currency
# ---------------------------------------------------------------------------


def test_missing_location_is_not_defaulted_to_nairobi():
    """Regression: empty source locations were stored as a fake 'Nairobi'."""
    n = JobNormalizer()
    result = n.normalize({"title": "Dev"}, "test")
    assert result["location"] == ""
    assert result["salary_currency"] is None


def test_legacy_currency_key_is_accepted():
    """Adapters historically emitted ``currency``; it must not be dropped."""
    n = JobNormalizer()
    result = n.normalize(
        {"title": "Dev", "currency": "EUR", "salary_min": 1000, "salary_max": 2000},
        "test",
    )
    assert result["salary_currency"] == "EUR"
    assert result["salary_min"] == 1000
    assert result["salary_max"] == 2000


def test_currency_without_amount_is_dropped():
    """A currency alone is not salary data and must not be persisted."""
    n = JobNormalizer()
    result = n.normalize({"title": "Dev", "location": "Nairobi", "currency": "KES"}, "test")
    assert result["salary_currency"] is None
    assert result["salary_min"] is None
    assert result["salary_max"] is None


def test_kenyan_location_still_infers_currency_when_salary_present():
    n = JobNormalizer()
    result = n.normalize(
        {"title": "Dev", "location": "Nairobi", "salary_min": 150000}, "test"
    )
    assert result["salary_currency"] == "KES"


def test_salary_period_is_normalized():
    n = JobNormalizer()
    assert n.normalize({"title": "Dev", "salary_period": "ANNUAL"}, "test")["salary_period"] == "year"
    assert n.normalize({"title": "Dev", "salary_period": "per month"}, "test")["salary_period"] == "month"


def test_remote_type_only_derived_from_explicit_remote_flag():
    n = JobNormalizer()
    assert n.normalize({"title": "Dev"}, "test")["remote_type"] is None
    assert n.normalize({"title": "Dev", "remote": True}, "test")["remote_type"] == "remote"
    assert n.normalize(
        {"title": "Dev", "remote": True, "remote_type": "Hybrid"}, "test"
    )["remote_type"] == "hybrid"
    assert n.normalize(
        {"title": "Dev", "remote_type": "TELECOMMUTE"}, "test"
    )["remote_type"] == "remote"


def test_employment_type_accepts_a_list():
    n = JobNormalizer()
    result = n.normalize({"title": "Dev", "employment_type": ["FULL_TIME"]}, "test")
    assert result["employment_type"] == "full-time"


def test_double_escaped_html_entities_are_decoded_in_title():
    """Regression: jobicy titles arrived as ``Risk &amp;#038; Controls``."""
    n = JobNormalizer()
    result = n.normalize(
        {"title": "Risk &amp;#038; Controls Manager"}, "jobicy"
    )
    assert result["title"] == "Risk & Controls Manager"


def test_single_and_numeric_entities_are_decoded():
    n = JobNormalizer()
    assert n.normalize({"title": "R&amp;D Lead"}, "test")["title"] == "R&D Lead"
    assert (
        n.normalize({"title": "Analyst &amp;#8211; Remote"}, "test")["title"]
        == "Analyst – Remote"
    )


def test_entities_are_decoded_in_company_and_location():
    n = JobNormalizer()
    result = n.normalize(
        {"title": "Dev", "company": "Acme &amp; Co", "location": "Kigali &amp; Kampala"},
        "test",
    )
    # company normalization lowercases short joiner words like "Co"
    assert result["company"] == "Acme & co"
    assert result["location"] == "Kigali & Kampala"


