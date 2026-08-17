"""Tests for deduplication."""

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
