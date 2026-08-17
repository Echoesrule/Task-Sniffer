"""Parsers for CV and job description processing."""

import re
from typing import Any


def parse_salary_range(text: str) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Extract salary range and currency from text.

    Returns (min, max, currency) or (None, None, None).
    """
    if not text:
        return None, None, None

    currency_map = {"KES": "KES", "Ksh": "KES", "USD": "USD", "$": "USD", "EUR": "EUR"}
    currency = None
    for sym, cur in currency_map.items():
        if sym in text:
            currency = cur
            break

    patterns = [
        r"KES?\s*(\d{1,3}(?:,\d{3})*)\s*[-–to]+\s*KES?\s*(\d{1,3}(?:,\d{3})*)",
        r"\$\s*(\d{1,3}(?:,\d{3})*)\s*[-–to]+\s*\$\s*(\d{1,3}(?:,\d{3})*)",
        r"(\d{1,3}(?:,\d{3})*)\s*[-–to]+\s*(\d{1,3}(?:,\d{3})*)\s*(?:per month|monthly|pm)",
        r"(\d{1,3}(?:,\d{3})*)\s*[-–to]+\s*(\d{1,3}(?:,\d{3})*)\s*(?:per year|yearly|p\.?a\.?)",
        r"(\d{1,3}(?:,\d{3})*)\s*k?\s*[-–to]+\s*(\d{1,3}(?:,\d{3})*)\s*k",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            min_sal = int(match.group(1).replace(",", ""))
            max_sal = int(match.group(2).replace(",", ""))
            if min_sal < 1000:
                min_sal *= 1000
                max_sal *= 1000
            return min_sal, max_sal, currency

    return None, None, currency


def extract_skills_from_text(text: str, skill_map: dict[str, list[str]]) -> list[str]:
    """Extract skills from text using a skill alias map."""
    if not text:
        return []

    text_lower = text.lower()
    found = set()

    for canonical, aliases in skill_map.items():
        for alias in aliases:
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, text_lower):
                found.add(canonical)
                break

    return sorted(found)


def clean_html(text: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_requirements(description: str) -> list[str]:
    """Extract requirement lines from a job description."""
    if not description:
        return []

    requirements = []
    lines = description.split("\n")
    in_requirements = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        lower = line.lower()
        if any(kw in lower for kw in ["requirement", "qualification", "what you", "must have", "skills needed"]):
            in_requirements = True
            continue
        if any(kw in lower for kw in ["responsibilit", "about the role", "what you'll do", "we offer"]):
            in_requirements = False
            continue

        if in_requirements and (line.startswith(("•", "-", "✓", "*", "–")) or re.match(r"^\d+[.)]\s", line)):
            cleaned = re.sub(r"^[•\-*–]\s*", "", line)
            cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned)
            if cleaned:
                requirements.append(cleaned)

    return requirements[:20]


def extract_responsibilities(description: str) -> list[str]:
    """Extract responsibility lines from a job description."""
    if not description:
        return []

    responsibilities = []
    lines = description.split("\n")
    in_responsibilities = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        lower = line.lower()
        if any(kw in lower for kw in ["responsibilit", "what you'll do", "about the role", "your role"]):
            in_responsibilities = True
            continue
        if any(kw in lower for kw in ["requirement", "qualific", "we offer", "benefit"]):
            in_responsibilities = False
            continue

        if in_responsibilities and (line.startswith(("•", "-", "✓", "*", "–")) or re.match(r"^\d+[.)]\s", line)):
            cleaned = re.sub(r"^[•\-*–]\s*", "", line)
            cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned)
            if cleaned:
                responsibilities.append(cleaned)

    return responsibilities[:20]
