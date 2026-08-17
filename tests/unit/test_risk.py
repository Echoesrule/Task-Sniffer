"""Tests for risk engine."""

from backend.risk.engine import RiskEngine


def test_legitimate_job_low_risk():
    engine = RiskEngine()
    job = {
        "title": "Senior Python Developer",
        "company": "Safaricom",
        "url": "https://safaricom.co.ke/careers/python-dev",
        "description": "We are looking for a senior Python developer to join our fintech team. Requirements: 5 years Python, Django, PostgreSQL.",
        "salary_min": 200000,
        "salary_max": 350000,
    }
    result = engine.analyze(job)
    assert result["risk_score"] < 30
    assert result["risk_level"] == "LOW"
    assert result["recommendation"] == "APPROVE"


def test_scam_job_high_risk():
    engine = RiskEngine()
    job = {
        "title": "Mystery Shopper - Earn KES 50000 per day",
        "company": "",
        "url": "http://suspicious-xyz.click/apply",
        "description": "Send money to start. Earn guaranteed income! Act now, limited time! No experience required. WhatsApp us for details.",
        "salary_min": None,
        "salary_max": None,
    }
    result = engine.analyze(job)
    assert result["risk_score"] >= 40
    assert len(result["risk_flags"]) >= 3


def test_suspicious_tld():
    engine = RiskEngine()
    job = {
        "title": "Developer",
        "company": "TechCo",
        "url": "https://techco.xyz/apply",
        "description": "Looking for a developer.",
    }
    result = engine.analyze(job)
    tld_flags = [f for f in result["risk_flags"] if "tld" in f["reason"].lower() or "domain" in f["reason"].lower()]
    assert len(tld_flags) > 0


def test_payment_request_flagged():
    engine = RiskEngine()
    job = {
        "title": "Data Entry",
        "company": "LegitCorp",
        "url": "https://legitcorp.com/careers",
        "description": "Send money to get started with training materials. Upfront fee required.",
    }
    result = engine.analyze(job)
    payment_flags = [f for f in result["risk_flags"] if "payment" in f["reason"].lower() or "fee" in f["reason"].lower() or "money" in f["reason"].lower()]
    assert len(payment_flags) > 0


def test_unknown_company():
    engine = RiskEngine()
    job = {
        "title": "Developer",
        "company": "",
        "url": "https://example.com/jobs/1",
        "description": "Looking for a developer with 3+ years experience.",
    }
    result = engine.analyze(job)
    company_flags = [f for f in result["risk_flags"] if "company" in f["reason"].lower()]
    assert len(company_flags) > 0


def test_urgency_language():
    engine = RiskEngine()
    job = {
        "title": "Developer",
        "company": "TechCo",
        "url": "https://techco.com/careers",
        "description": "Act now! Limited time offer. Don't miss this opportunity!",
    }
    result = engine.analyze(job)
    urgency_flags = [f for f in result["risk_flags"] if "urgency" in f["reason"].lower() or "act now" in f["reason"].lower()]
    assert len(urgency_flags) > 0
