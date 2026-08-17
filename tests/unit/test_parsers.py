"""Tests for parsers."""

from backend.parsers import parse_salary_range, extract_skills_from_text, clean_html


def test_parse_salary_kes():
    min_s, max_s, cur = parse_salary_range("KES 150,000 - 250,000 per month")
    assert min_s == 150000
    assert max_s == 250000
    assert cur == "KES"


def test_parse_salary_usd():
    min_s, max_s, cur = parse_salary_range("$80,000 - $120,000 per year")
    assert min_s == 80000
    assert max_s == 120000
    assert cur == "USD"


def test_parse_salary_k():
    min_s, max_s, cur = parse_salary_range("100k - 150k per month")
    assert min_s == 100000
    assert max_s == 150000


def test_parse_salary_none():
    min_s, max_s, cur = parse_salary_range("Competitive salary")
    assert min_s is None
    assert max_s is None


def test_extract_skills():
    skill_map = {
        "python": ["python", "python3"],
        "javascript": ["javascript", "js"],
        "react": ["react", "reactjs"],
    }
    skills = extract_skills_from_text("We need python and react experience", skill_map)
    assert "python" in skills
    assert "react" in skills
    assert "javascript" not in skills


def test_clean_html():
    result = clean_html("<p>Hello <b>world</b></p>")
    assert result == "Hello world"


def test_clean_html_none():
    result = clean_html(None)
    assert result == ""
