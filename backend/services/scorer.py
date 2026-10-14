from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.skills import normalize_skill_list


EXCELLENT = "EXCELLENT"
STRONG = "STRONG"
POSSIBLE = "POSSIBLE"
WEAK = "WEAK"
IGNORE = "IGNORE"


class JobScorer:
    """Score a job against a candidate profile with configurable weights."""

    DEFAULT_WEIGHTS = {
        "skills": 0.30,
        "experience": 0.15,
        "role": 0.15,
        "location": 0.10,
        "salary": 0.10,
        "projects": 0.08,
        "freshness": 0.05,
        "source_quality": 0.07,
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.weights: dict[str, float] = {
            **self.DEFAULT_WEIGHTS,
            **(self.config.get("weights") or {}),
        }
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def score(self, job: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        breakdown: dict[str, float] = {}

        breakdown["skills"] = self._score_skills(
            job.get("skills", []),
            candidate.get("skills", []),
        )
        breakdown["experience"] = self._score_experience(
            job.get("experience_level", ""),
            candidate.get("experience_level", ""),
        )
        breakdown["role"] = self._score_role(
            job.get("title", ""),
            candidate.get("preferred_roles", []),
        )
        breakdown["location"] = self._score_location(
            job.get("location", ""),
            candidate.get("location_preferences", {}),
        )
        breakdown["salary"] = self._score_salary(
            {
                "min": job.get("salary_min"),
                "max": job.get("salary_max"),
                "currency": job.get("salary_currency", ""),
            },
            candidate.get("salary_preferences", {}),
        )
        breakdown["projects"] = self._score_projects(
            job.get("skills", []),
            candidate.get("projects", []),
        )
        breakdown["freshness"] = self._score_freshness(job.get("posted_at", ""))
        breakdown["source_quality"] = self._score_source_quality(
            job.get("source_stats", {})
        )

        weighted_sum = sum(
            breakdown[key] * self.weights.get(key, 0) for key in breakdown
        )
        total_weight = sum(
            self.weights.get(key, 0) for key in breakdown
        )
        final_score = weighted_sum / total_weight if total_weight > 0 else 0.0
        final_score = round(min(max(final_score, 0.0), 1.0), 4)

        classification = self.classify(final_score)

        return {
            "score": final_score,
            "classification": classification,
            "breakdown": breakdown,
            "weights_used": self.weights,
        }

    @staticmethod
    def _score_skills(job_skills: list[str], candidate_skills: list[str]) -> float:
        if not job_skills:
            return 0.5
        if not candidate_skills:
            return 0.0

        job_set = {s.lower().strip() for s in normalize_skill_list(job_skills)}
        cand_set = {s.lower().strip() for s in normalize_skill_list(candidate_skills)}

        if not job_set:
            return 0.5

        matched = job_set & cand_set
        coverage = len(matched) / len(job_set) if job_set else 0.0

        bonus = 0.0
        if len(matched) >= 3:
            bonus = 0.1
        elif len(matched) >= 5:
            bonus = 0.2

        overlap = len(matched) / len(cand_set) if cand_set else 0.0
        breadth_bonus = min(overlap * 0.2, 0.15)

        return min(coverage + bonus + breadth_bonus, 1.0)

    @staticmethod
    def _score_experience(job_level: str, candidate_level: str) -> float:
        level_order = {
            "intern": 0,
            "junior": 1,
            "mid": 2,
            "senior": 3,
            "staff": 4,
            "executive": 5,
        }

        job_idx = level_order.get(job_level.lower(), 2)
        cand_idx = level_order.get(candidate_level.lower(), 2)

        diff = abs(job_idx - cand_idx)

        if diff == 0:
            return 1.0
        if diff == 1:
            return 0.75
        if diff == 2:
            return 0.4
        if diff == 3:
            return 0.2
        return 0.05

    @staticmethod
    def _score_role(title: str, preferred_roles: list[str]) -> float:
        if not preferred_roles:
            return 0.5
        if not title:
            return 0.3

        title_lower = title.lower()
        for role in preferred_roles:
            role_lower = role.lower().strip()
            if role_lower in title_lower:
                return 1.0

        role_words = title_lower.split()
        for role in preferred_roles:
            role_words_needed = role.lower().strip().split()
            if all(w in role_words for w in role_words_needed):
                return 0.85

        for role in preferred_roles:
            role_lower = role.lower().strip()
            if any(w in title_lower for w in role_lower.split()):
                return 0.5

        return 0.2

    @staticmethod
    def _score_location(job_location: str, candidate_prefs: dict[str, Any]) -> float:
        if not job_location:
            return 0.5
        if not candidate_prefs:
            return 0.5

        job_loc_lower = job_location.lower()

        if "remote" in job_loc_lower:
            remote_pref = candidate_prefs.get("remote", True)
            if remote_pref:
                return 1.0
            return 0.5

        preferred_cities = candidate_prefs.get("cities", [])
        for city in preferred_cities:
            if city.lower() in job_loc_lower:
                return 1.0

        preferred_countries = candidate_prefs.get("countries", [])
        for country in preferred_countries:
            if country.lower() in job_loc_lower:
                return 0.8

        willing_to_relocate = candidate_prefs.get("relocate", False)
        if willing_to_relocate:
            return 0.6

        return 0.2

    @staticmethod
    def _score_salary(job_salary: dict[str, Any], candidate_prefs: dict[str, Any]) -> float:
        if not job_salary:
            return 0.5
        if not candidate_prefs:
            return 0.5

        job_min = job_salary.get("min")
        job_max = job_salary.get("max")
        cand_min = candidate_prefs.get("min")
        cand_max = candidate_prefs.get("max")

        if job_min is None and job_max is None:
            return 0.5
        if cand_min is None and cand_max is None:
            return 0.5

        effective_job_max = job_max if job_max else job_min
        effective_job_min = job_min if job_min else job_max
        effective_cand_min = cand_min if cand_min else cand_max
        effective_cand_max = cand_max if cand_max else cand_min

        if effective_job_min is None or effective_cand_min is None:
            return 0.5

        if effective_job_max and effective_cand_min:
            if effective_job_max >= effective_cand_min:
                if effective_job_min and effective_cand_max and effective_job_min <= effective_cand_max:
                    return 1.0
                return 0.8
            overshoot = effective_job_max / effective_cand_min
            if overshoot >= 0.8:
                return 0.6
            if overshoot >= 0.6:
                return 0.4
            return 0.2

        if effective_job_min >= (effective_cand_min or 0) * 0.8:
            return 0.7
        return 0.3

    @staticmethod
    def _score_projects(job_skills: list[str], candidate_projects: list[dict[str, Any]]) -> float:
        if not candidate_projects:
            return 0.3
        if not job_skills:
            return 0.5

        job_set = {s.lower().strip() for s in normalize_skill_list(job_skills)}
        project_skill_hits = 0
        total_project_skills = 0

        for project in candidate_projects:
            proj_skills = project.get("skills", [])
            if isinstance(proj_skills, str):
                proj_skills = [s.strip() for s in proj_skills.split(",")]
            for ps in normalize_skill_list(proj_skills):
                total_project_skills += 1
                if ps.lower().strip() in job_set:
                    project_skill_hits += 1

        if total_project_skills == 0:
            return 0.3

        coverage = project_skill_hits / total_project_skills
        bonus = 0.1 if len(candidate_projects) >= 2 else 0.0

        return min(coverage * 0.9 + bonus, 1.0)

    @staticmethod
    def _score_freshness(posted_at: str) -> float:
        if not posted_at:
            return 0.5

        try:
            if posted_at.endswith("Z"):
                posted_at = posted_at[:-1] + "+00:00"
            posted = datetime.fromisoformat(posted_at)
        except (ValueError, TypeError):
            return 0.5

        now = datetime.now(timezone.utc)
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)

        age_days = (now - posted).total_seconds() / 86400

        if age_days <= 1:
            return 1.0
        if age_days <= 3:
            return 0.9
        if age_days <= 7:
            return 0.8
        if age_days <= 14:
            return 0.6
        if age_days <= 30:
            return 0.4
        if age_days <= 60:
            return 0.2
        return 0.05

    @staticmethod
    def _score_source_quality(source_stats: dict[str, Any]) -> float:
        if not source_stats:
            return 0.5

        response_rate = source_stats.get("response_rate", 0.5)
        relevance = source_stats.get("relevance_score", 0.5)
        freshness = source_stats.get("avg_freshness", 0.5)
        tier = source_stats.get("tier", 3)

        tier_score = max(0.0, 1.0 - (tier - 1) * 0.25)

        combined = (
            float(response_rate) * 0.3
            + float(relevance) * 0.3
            + float(freshness) * 0.2
            + tier_score * 0.2
        )
        return min(max(combined, 0.0), 1.0)

    @staticmethod
    def classify(score: float) -> str:
        if score >= 0.85:
            return EXCELLENT
        if score >= 0.70:
            return STRONG
        if score >= 0.50:
            return POSSIBLE
        if score >= 0.30:
            return WEAK
        return IGNORE

    def explain(self, score_result: dict[str, Any]) -> str:
        score_val = score_result.get("score", 0.0)
        classification = score_result.get("classification", "UNKNOWN")
        breakdown = score_result.get("breakdown", {})

        lines = [f"Overall Score: {score_val:.0%} ({classification})"]
        lines.append("")

        explanation_map = {
            "skills": "Skill coverage",
            "experience": "Experience level match",
            "role": "Role/title relevance",
            "location": "Location compatibility",
            "salary": "Salary alignment",
            "projects": "Project experience relevance",
            "freshness": "Job posting freshness",
            "source_quality": "Source reliability",
        }

        for key, label in explanation_map.items():
            value = breakdown.get(key, 0.0)
            weight = self.weights.get(key, 0.0)
            indicator = self._bar(value)
            lines.append(f"  {label:.<30} {indicator} {value:.0%} (weight: {weight:.0%})")

        lines.append("")
        lines.append(f"Weights: {', '.join(f'{k}={v:.0%}' for k, v in self.weights.items())}")

        return "\n".join(lines)

    @staticmethod
    def _bar(value: float, width: int = 10) -> str:
        filled = int(value * width)
        return "[" + "#" * filled + "." * (width - filled) + "]"
