"""Normalizer - standardizes job data from different scrapers into a unified format."""

import json
import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class JobNormalizer:
    """Normalize, enrich, and standardize job data from all sources."""

    TECH_MAP: dict[str, list[str]] = {
        "python": ["python", "python3", "cpython", "pypy"],
        "javascript": ["javascript", "js", "es6", "es2015", "ecmascript"],
        "typescript": ["typescript", "ts"],
        "react": ["react", "reactjs", "react.js"],
        "vue": ["vue", "vuejs", "vue.js"],
        "angular": ["angular", "angularjs"],
        "node": ["node", "nodejs", "node.js"],
        "express": ["express", "expressjs"],
        "fastapi": ["fastapi", "fast api"],
        "django": ["django"],
        "flask": ["flask"],
        "spring": ["spring", "springboot", "spring boot"],
        "java": ["java"],
        "go": ["go", "golang"],
        "rust": ["rust", "rustlang"],
        "ruby": ["ruby", "rubyonrails", "rails"],
        "php": ["php", "laravel"],
        "c#": ["c#", "csharp", ".net"],
        "c++": ["c++", "cpp"],
        "kotlin": ["kotlin"],
        "swift": ["swift"],
        "postgresql": ["postgresql", "postgres", "psql"],
        "mysql": ["mysql"],
        "mongodb": ["mongodb", "mongo"],
        "redis": ["redis"],
        "elasticsearch": ["elasticsearch", "elastic", "opensearch"],
        "aws": ["aws", "amazon web services"],
        "gcp": ["gcp", "google cloud"],
        "azure": ["azure", "microsoft azure"],
        "docker": ["docker"],
        "kubernetes": ["kubernetes", "k8s"],
        "terraform": ["terraform"],
        "graphql": ["graphql", "gql"],
        "rest": ["rest", "restful", "restapi"],
        "grpc": ["grpc", "g-rpc"],
        "kafka": ["kafka"],
        "rabbitmq": ["rabbitmq", "rabbit"],
        "react native": ["react native", "react-native"],
        "flutter": ["flutter"],
        "tailwind": ["tailwind", "tailwindcss"],
        "nextjs": ["next", "nextjs", "next.js"],
        "nuxt": ["nuxt", "nuxtjs", "nuxt.js"],
        "svelte": ["svelte"],
    }

    LOCATION_NORMALIZE: dict[str, str] = {
        "usa": "United States",
        "us": "United States",
        "united states": "United States",
        "eu": "Europe",
        "europe": "Europe",
        "uk": "United Kingdom",
        "united kingdom": "United Kingdom",
        "asia": "Asia",
        "apac": "Asia Pacific",
        "latam": "Latin America",
        "worldwide": "Worldwide",
        "global": "Worldwide",
        "anywhere": "Worldwide",
    }

    def normalize(self, job: dict[str, Any]) -> dict[str, Any]:
        """Run full normalization pipeline on a job dict."""
        job = self._normalize_title(job)
        job = self._normalize_company(job)
        job = self._normalize_url(job)
        job = self._normalize_location(job)
        job = self._normalize_salary(job)
        job = self._normalize_tech_stack(job)
        job = self._normalize_job_type(job)
        job = self._normalize_description(job)
        job = self._set_defaults(job)
        return job

    def _normalize_title(self, job: dict) -> dict:
        title = job.get("title", "").strip()
        title = re.sub(r"\s+", " ", title)
        title = re.sub(r"^(remote\s*[-:]\s*)", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*[-:]\s*remote$", "", title, flags=re.IGNORECASE)
        job["title"] = title
        return job

    def _normalize_company(self, job: dict) -> dict:
        company = job.get("company", "Unknown").strip()
        if not company:
            company = "Unknown"
        company = re.sub(r"\s+", " ", company)
        job["company"] = company
        return job

    def _normalize_url(self, job: dict) -> dict:
        url = job.get("url", "").strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        job["url"] = url
        return job

    def _normalize_location(self, job: dict) -> dict:
        location = job.get("location", "").strip()
        location_lower = location.lower()

        for key, normalized in self.LOCATION_NORMALIZE.items():
            if key in location_lower:
                job["location"] = normalized
                break

        remote_keywords = ["remote", "anywhere", "worldwide", "distributed", "global"]
        if any(kw in location_lower for kw in remote_keywords):
            job["remote"] = True

        if not location:
            job["location"] = "Remote" if job.get("remote") else "Not specified"

        return job

    def _normalize_salary(self, job: dict) -> dict:
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")

        if salary_min is not None and salary_max is not None:
            if salary_min > 1_000_000:
                salary_min = salary_min // 1000
                salary_max = salary_max // 1000
            if salary_min > salary_max:
                salary_min, salary_max = salary_max, salary_min

        job["salary_min"] = salary_min
        job["salary_max"] = salary_max
        return job

    def _normalize_tech_stack(self, job: dict) -> list[str]:
        raw = job.get("tech_stack", [])
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                raw = [raw] if raw else []

        if not raw:
            text = f"{job.get('title', '')} {job.get('description', '')}"
            raw = self._detect_tech(text)

        normalized = []
        seen = set()
        for tech in raw:
            canonical = self._canonicalize_tech(tech)
            if canonical and canonical not in seen:
                normalized.append(canonical)
                seen.add(canonical)

        job["tech_stack"] = normalized
        return job

    def _canonicalize_tech(self, tech: str) -> str | None:
        tech_lower = tech.lower().strip()
        for canonical, aliases in self.TECH_MAP.items():
            if tech_lower in aliases:
                return canonical
        if len(tech_lower) > 1 and len(tech_lower) < 30:
            return tech_lower
        return None

    def _detect_tech(self, text: str) -> list[str]:
        text_lower = text.lower()
        found = []
        for canonical, aliases in self.TECH_MAP.items():
            for alias in aliases:
                pattern = r"\b" + re.escape(alias) + r"\b"
                if re.search(pattern, text_lower):
                    found.append(canonical)
                    break
        return found[:10]

    def _normalize_job_type(self, job: dict) -> dict:
        job_type = job.get("job_type", "full_time")
        type_map = {
            "full time": "full_time",
            "full-time": "full_time",
            "fulltime": "full_time",
            "part time": "part_time",
            "part-time": "part_time",
            "parttime": "part_time",
            "contract": "contract",
            "freelance": "freelance",
            "internship": "internship",
            "intern": "internship",
            "temporary": "contract",
            "temp": "contract",
        }
        job["job_type"] = type_map.get(job_type.lower().strip(), "full_time")
        return job

    def _normalize_description(self, job: dict) -> dict:
        desc = job.get("description", "")
        if not desc:
            job["description"] = ""
            return job
        desc = re.sub(r"<[^>]+>", " ", desc)
        desc = re.sub(r"\s+", " ", desc).strip()
        job["description"] = desc[:2000]
        return job

    def _set_defaults(self, job: dict) -> dict:
        job.setdefault("source", "unknown")
        job.setdefault("remote", True)
        job.setdefault("salary_min", None)
        job.setdefault("salary_max", None)
        job.setdefault("job_type", "full_time")
        job.setdefault("scraped_at", datetime.utcnow())
        job.setdefault("notified", False)
        return job
