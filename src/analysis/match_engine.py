"""Match Score Engine - scores how well a job matches user preferences."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class MatchScoreEngine:
    """Score jobs against user preferences (0-100)."""

    WEIGHTS = {
        "tech_stack": 0.35,
        "salary": 0.25,
        "keywords": 0.20,
        "remote": 0.10,
        "job_type": 0.10,
    }

    def score(self, job: dict[str, Any], preferences: dict[str, Any]) -> dict[str, Any]:
        """Score a job against user preferences. Returns score breakdown."""
        scores = {
            "tech_stack": self._score_tech_stack(job, preferences),
            "salary": self._score_salary(job, preferences),
            "keywords": self._score_keywords(job, preferences),
            "remote": self._score_remote(job, preferences),
            "job_type": self._score_job_type(job, preferences),
        }

        total = sum(scores[k] * self.WEIGHTS[k] for k in scores)

        return {
            "match_score": round(total, 1),
            "breakdown": scores,
            "match_level": self._classify_match(total),
        }

    def _score_tech_stack(self, job: dict, prefs: dict) -> float:
        desired = prefs.get("tech_stack", [])
        if not desired:
            return 50.0

        job_tech = job.get("tech_stack", [])
        if isinstance(job_tech, str):
            try:
                job_tech = json.loads(job_tech)
            except (json.JSONDecodeError, TypeError):
                job_tech = []

        if not job_tech:
            return 30.0

        job_tech_lower = {t.lower() for t in job_tech}
        desired_lower = {d.lower() for d in desired}

        matches = job_tech_lower & desired_lower
        if not desired_lower:
            return 50.0

        return min(100.0, (len(matches) / len(desired_lower)) * 100)

    def _score_salary(self, job: dict, prefs: dict) -> float:
        min_salary_pref = prefs.get("min_salary", 0)
        job_min = job.get("salary_min")
        job_max = job.get("salary_max")

        if not min_salary_pref:
            return 70.0

        if not job_min and not job_max:
            return 40.0

        if job_max and job_max >= min_salary_pref:
            return 100.0

        if job_min and job_min >= min_salary_pref:
            return 90.0

        if job_min and job_max:
            if job_min < min_salary_pref <= job_max:
                ratio = (min_salary_pref - job_min) / (job_max - job_min)
                return max(30.0, 80.0 - ratio * 50)

        return 20.0

    def _score_keywords(self, job: dict, prefs: dict) -> float:
        keywords = prefs.get("keywords", [])
        if not keywords:
            return 50.0

        text = f"{job.get('title', '')} {job.get('description', '')} {' '.join(job.get('tech_stack', []))}".lower()
        matches = sum(1 for kw in keywords if kw.lower() in text)

        if not keywords:
            return 50.0

        return min(100.0, (matches / len(keywords)) * 100)

    def _score_remote(self, job: dict, prefs: dict) -> float:
        if not prefs.get("remote_only", False):
            return 70.0
        return 100.0 if job.get("remote", False) else 0.0

    def _score_job_type(self, job: dict, prefs: dict) -> float:
        allowed_types = prefs.get("job_types", [])
        if not allowed_types:
            return 70.0

        job_type = job.get("job_type", "full_time")
        return 100.0 if job_type in allowed_types else 20.0

    def _classify_match(self, score: float) -> str:
        if score >= 80:
            return "excellent"
        elif score >= 60:
            return "good"
        elif score >= 40:
            return "fair"
        else:
            return "poor"
