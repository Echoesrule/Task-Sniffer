from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qsl, urlparse

from backend.skills import analyze_skills
from backend.skills.vocabulary import TECH_SKILL_MAP, normalize_skill_list
from backend.sources.urls import canonicalize_url

#: source-specific query parameters that establish job identity.
#: only add entries backed by clear evidence for that source.
_SOURCE_IDENTITY_PARAMS: dict[str, tuple[str, ...]] = {
    "greenhouse": ("gh_jid",),
}

#: generic query parameters that may establish job identity (spec §10).
_IDENTITY_QUERY_PARAMS: frozenset[str] = frozenset(
    {"job", "job_id", "jobid", "jid", "vacancy", "vac", "offer", "posting",
     "position", "id", "listing", "advert"}
)

#: path segments that never identify a job on their own.
_NON_IDENTIFYING_PATH_SEGMENTS: frozenset[str] = frozenset(
    {
        "search", "results", "browse", "jobs", "job", "jobsearch",
        "careers", "career", "positions", "position", "openings", "opening",
        "apply", "apply-now", "view", "details", "detail", "listing",
        "listings", "vacancies", "vacancy", "category", "categories",
        "company", "companies", "profile", "about", "index",
    }
)


KENYA_LOCATIONS: dict[str, list[str]] = {
    "Nairobi": ["nairobi", "nbi", "westlands", "karen", "kilimani", "lavington", "upperhill", "cbd"],
    "Mombasa": ["mombasa", "nyali", "changamwe", "likoni"],
    "Kisumu": ["kisumu"],
    "Nakuru": ["nakuru"],
    "Eldoret": ["eldoret"],
    "Thika": ["thika"],
    "Nyeri": ["nyeri"],
    "Machakos": ["machakos"],
    "Meru": ["meru"],
    "Kitale": ["kitale"],
    "Garissa": ["garissa"],
    "Kakamega": ["kakamega"],
    "Kericho": ["kericho"],
    "Bungoma": ["bungoma"],
    "Busia": ["busia"],
    "Homa Bay": ["homa bay"],
    "Migori": ["migori"],
    "Siaya": ["siaya"],
    "Vihiga": ["vihiga"],
    "Trans-Nzoia": ["trans-nzoia", "trans nzoia"],
    "Bomet": ["bomet"],
    "Narok": ["narok"],
    "Laikipia": ["laikipia"],
    "Nyandarua": ["nyandarua"],
    "Murang'a": ["murang'a", "muranga"],
    "Kiambu": ["kiambu", "ruiru", "kikuyu", "thindigua"],
    "Kajiado": ["kajiado", "ngong"],
    "Makueni": ["makueni"],
    "Taita-Taveta": ["taita", "taveta", "voi"],
    "Kilifi": ["kilifi", "malindi"],
    "Kwale": ["kwale", "diani"],
    "Lamu": ["lamu"],
    "Marsabit": ["marsabit"],
    "Isiolo": ["isiolo"],
    "Mandera": ["mandera"],
    "Wajir": ["wajir"],
    "Samburu": ["samburu"],
    "West Pokot": ["west pokot"],
    "Turkana": ["turkana", "lodwar"],
}


class JobNormalizer:
    """Normalize raw scraped job data into a canonical schema."""

    def normalize(self, job: dict[str, Any], source: str) -> dict[str, Any]:
        title = self._normalize_title(job.get("title", ""))
        company = self._normalize_company(job.get("company", ""))
        location = self._normalize_location(job.get("location", ""))
        salary = self._normalize_salary(job)
        raw_description = job.get("description", "") or ""
        description = self._normalize_description(raw_description)

        # Extract skills from the free text, and union them with whatever the
        # adapter supplied explicitly.  Extraction is deterministic/rules-based.
        analysis = analyze_skills(title, raw_description)
        provided = self._normalize_skills(job.get("skills", []))
        skills = sorted(set(analysis.skills) | set(provided))

        employment_type = self._normalize_employment_type(job.get("employment_type", ""))
        experience_level = self._normalize_experience_level(title, job.get("experience_level", ""))

        url = job.get("url", "")
        if url:
            url = self._normalize_url(url)

        return {
            "source_job_id": self._extract_source_job_id(url, company, title, source),
            "title": title,
            "company": company,
            "location": location,
            "url": url,
            "description": description,
            "salary_currency": salary.get("currency"),
            "salary_min": salary.get("min"),
            "salary_max": salary.get("max"),
            "skills": skills,
            "skills_required": analysis.required,
            "skills_preferred": analysis.preferred,
            "skills_detail": analysis.detail,
            "employment_type": employment_type,
            "experience_level": experience_level,
            "remote": job.get("remote", False),
            "posted_at": job.get("posted_at", ""),
            "source": source,
            "fingerprint": self.generate_fingerprint(company, title, location),
        }

    def _normalize_title(self, title: str) -> str:
        title = re.sub(r"\s+", " ", title).strip()
        title = re.sub(r"\bSr\.?\b", "Senior", title)
        title = re.sub(r"\bJr\.?\b", "Junior", title)
        title = re.sub(r"\bSr\b", "Senior", title)
        title = re.sub(r"\bJr\b", "Junior", title)
        title = re.sub(r"\bSnr\b", "Senior", title)
        title = re.sub(r"\bSn\.?\b", "Senior", title)
        return title.strip()

    def _normalize_company(self, company: str) -> str:
        company = re.sub(r"\s+", " ", company).strip()
        company = company.strip(".")
        title_case_words = {"Ltd", "Inc", "LLC", "Corp", "Co", "PLC"}
        words = company.split()
        normalized = []
        for word in words:
            if word.upper() in {"LTD", "INC", "LLC", "CORP", "PLC"}:
                normalized.append(word.upper())
            elif word.lower() in {"co", "of", "the", "and", "or"}:
                normalized.append(word.lower())
            else:
                normalized.append(word.capitalize() if word.isupper() else word)
        return " ".join(normalized)

    def _normalize_url(self, url: str) -> str:
        """Normalize scheme/host/path without destroying job identity.

        Query parameters are preserved except for an explicit tracking policy
        (handled by ``canonicalize_url``). Identity parameters such as
        ``gh_jid`` or ``job_id`` therefore survive normalization.
        """
        url = (url or "").strip()
        if not url:
            return ""
        return canonicalize_url(url)

    @staticmethod
    def _extract_source_job_id(
        url: str, company: str, title: str, source: str = ""
    ) -> str:
        parsed = urlparse(url or "")
        query = {
            key.lower(): value
            for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        }

        for param in _SOURCE_IDENTITY_PARAMS.get((source or "").lower(), ()):
            if query.get(param):
                return query[param]

        for param in _IDENTITY_QUERY_PARAMS:
            if query.get(param):
                return query[param]

        path = parsed.path or ""
        for part in reversed([s for s in path.split("/") if s]):
            if len(part) <= 1:
                continue
            if part.lower() in _NON_IDENTIFYING_PATH_SEGMENTS:
                continue
            return part

        raw = f"{company}|{title}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _normalize_location(self, location: str) -> str:
        if not location:
            return "Nairobi"

        location_lower = location.lower().strip()

        for canonical, aliases in KENYA_LOCATIONS.items():
            for alias in aliases:
                if alias in location_lower:
                    return canonical

        if "remote" in location_lower:
            return "Remote"

        if "hybrid" in location_lower:
            parts = [p.strip() for p in location.split(",")]
            city = parts[0] if parts else location
            return f"{city} (Hybrid)"

        parts = [p.strip() for p in location.split(",")]
        if len(parts) >= 2:
            return f"{parts[0]}, {parts[1]}"

        return location.title()

    def _normalize_salary(self, job: dict[str, Any]) -> dict[str, Any]:
        currency = job.get("salary_currency")
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")

        text = job.get("salary_text", "")
        if text and (salary_min is None or salary_max is None):
            parsed_currency, parsed_min, parsed_max = self._parse_salary_text(text)
            if currency is None:
                currency = parsed_currency
            if salary_min is None:
                salary_min = parsed_min
            if salary_max is None:
                salary_max = parsed_max

        if currency is None:
            currency = self._detect_currency(job.get("location", ""))

        if salary_min is not None:
            salary_min = int(salary_min)
        if salary_max is not None:
            salary_max = int(salary_max)

        return {"currency": currency, "min": salary_min, "max": salary_max}

    @staticmethod
    def _parse_salary_text(text: str) -> tuple[str | None, int | None, int | None]:
        currency_map = {"$": "USD", "€": "EUR", "£": "GBP", "KSh": "KES", "KES": "KES"}
        currency: str | None = None
        for symbol, code in currency_map.items():
            if symbol.lower() in text.lower():
                currency = code
                break

        numbers = re.findall(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
        clean = [int(float(n.replace(",", ""))) for n in numbers]

        if len(clean) >= 2:
            lo, hi = min(clean), max(clean)
        elif clean:
            lo = hi = clean[0]
        else:
            return (currency, None, None)

        if any(k in text.lower() for k in ("k /month", "k/month", "k pm")):
            lo *= 1000
            hi *= 1000

        return (currency, lo, hi)

    @staticmethod
    def _detect_currency(location: str) -> str | None:
        loc_lower = location.lower()
        kenyan_cities = list(KENYA_LOCATIONS.keys()) + ["ke", "kenya"]
        if any(c.lower() in loc_lower for c in kenyan_cities):
            return "KES"
        return None

    def _normalize_skills(self, skills: list[str] | str) -> list[str]:
        """Canonicalize an explicitly supplied skill list via the vocabulary."""
        return normalize_skill_list(skills)

    @staticmethod
    def _normalize_employment_type(raw: str) -> str:
        if not raw:
            return "unknown"
        raw_lower = raw.lower().strip()
        mapping = {
            "full": "full-time",
            "full-time": "full-time",
            "full time": "full-time",
            "ft": "full-time",
            "part": "part-time",
            "part-time": "part-time",
            "part time": "part-time",
            "pt": "part-time",
            "contract": "contract",
            "contractor": "contract",
            "freelance": "contract",
            "temp": "temporary",
            "temporary": "temporary",
            "intern": "internship",
            "internship": "internship",
            "permanent": "full-time",
        }
        for key, value in mapping.items():
            if key in raw_lower:
                return value
        return raw_lower

    @staticmethod
    def _normalize_experience_level(title: str, raw: str) -> str:
        combined = f"{title} {raw}".lower()
        if any(w in combined for w in ("intern", "internship", "trainee")):
            return "intern"
        if any(w in combined for w in ("junior", "jr", "entry level", "entry-level", "associate")):
            return "junior"
        if any(w in combined for w in ("senior", "sr", "sr.", "snr", "lead", "principal")):
            return "senior"
        if any(w in combined for w in ("staff", "distinguished", "fellow")):
            return "staff"
        if any(w in combined for w in ("mid", "intermediate", "mid-level")):
            return "mid"
        if any(w in combined for w in ("director", "vp", "vice president", "head of")):
            return "executive"
        return "mid"

    @staticmethod
    def _normalize_description(description: str) -> str:
        if not description:
            return ""
        text = re.sub(r"<[^>]+>", " ", description)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&#\d+;", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def generate_fingerprint(company: str, title: str, location: str) -> str:
        raw = f"{company.strip().lower()}|{title.strip().lower()}|{location.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()
