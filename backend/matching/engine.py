"""Multi-stage job matching engine with configurable weights."""

from __future__ import annotations

import re
from typing import Any


class MatchingEngine:
    """Multi-stage job matching engine.

    Pipeline:
        1. stage_1_filter - cheap deterministic filters
        2. stage_2_semantic - skill equivalence and transferable skills
        3. stage_3_score - final weighted score combination
    """

    CONFIGURABLE_WEIGHTS: dict[str, float] = {
        "location": 0.15,
        "salary": 0.15,
        "experience": 0.20,
        "skills": 0.40,
        "remote_fit": 0.10,
    }

    SKILL_ALIASES: dict[str, list[str]] = {
        "python": ["python3", "python2", "py"],
        "javascript": ["js", "ecmascript", "es6", "es2015", "es2020"],
        "typescript": ["ts"],
        "react": ["reactjs", "react.js"],
        "angular": ["angularjs", "angular.js", "angular2+"],
        "vue": ["vuejs", "vue.js", "vue3", "vue2"],
        "node": ["nodejs", "node.js", "node.js"],
        "postgresql": ["postgres", "psql"],
        "mongodb": ["mongo"],
        "kubernetes": ["k8s"],
        "terraform": ["tf"],
        "aws": ["amazon web services", "ec2", "s3", "lambda", "aws lambda"],
        "gcp": ["google cloud", "google cloud platform", "cloud run", "bigquery"],
        "azure": ["microsoft azure", "azure devops"],
        "docker": ["containerization", "containers"],
        "sql": ["mysql", "mssql", "mariadb", "database"],
        "html": ["html5", "xhtml"],
        "css": ["css3", "scss", "sass", "less", "tailwind", "bootstrap"],
        "git": ["github", "gitlab", "bitbucket", "version control"],
        "ci/cd": ["ci cd", "continuous integration", "continuous deployment", "jenkins", "circleci", "github actions"],
        "machine learning": ["ml", "deep learning", "neural networks", "ai"],
        "data analysis": ["analytics", "data analytics", "business intelligence"],
        "communication": ["verbal communication", "written communication", "interpersonal"],
        "leadership": ["team lead", "management", "people management"],
        "problem solving": ["analytical", "critical thinking", "troubleshooting"],
        "agile": ["scrum", "kanban", "sprint"],
        "rest api": ["rest", "restful", "rest apis"],
        "graphql": ["gql"],
        "grpc": ["grpc", "protocol buffers"],
    }

    LEVEL_RANK: dict[str, int] = {
        "intern": 0,
        "junior": 1,
        "entry": 1,
        "mid": 2,
        "intermediate": 2,
        "mid-level": 2,
        "senior": 3,
        "sr.": 3,
        "lead": 4,
        "principal": 5,
        "staff": 5,
        "architect": 5,
        "director": 6,
        "vp": 7,
        "vice president": 7,
        "c-level": 8,
        "cto": 8,
        "ceo": 8,
        "cfo": 8,
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the matching engine.

        Args:
            config: Optional configuration dict to override default weights
                    and settings.
        """
        self.weights = dict(self.CONFIGURABLE_WEIGHTS)
        if config:
            if "weights" in config:
                self.weights.update(config["weights"])

        total = sum(self.weights.values())
        if total > 0 and abs(total - 1.0) > 0.01:
            for key in self.weights:
                self.weights[key] /= total

        self.config = config or {}

    async def match(self, job: dict, candidate: dict) -> dict:
        """Run the full matching pipeline.

        Args:
            job: Job posting dictionary.
            candidate: Candidate profile dictionary.

        Returns:
            Complete match result with scores, explanations, and metadata.
        """
        filter_result = self.stage_1_filter(job, candidate)
        semantic_result = await self.stage_2_semantic(job, candidate)
        score_result = self.stage_3_score(filter_result, semantic_result)

        combined_result = {
            **score_result,
            "filter": filter_result,
            "semantic": semantic_result,
            "job_id": job.get("id", job.get("job_id")),
            "candidate_id": candidate.get("id", candidate.get("candidate_id")),
            "explanation": self.explain_match(score_result),
        }

        return combined_result

    def stage_1_filter(self, job: dict, candidate: dict) -> dict:
        """Apply cheap deterministic filters.

        Checks location compatibility, salary range overlap,
        experience level match, and basic skill presence.

        Args:
            job: Job posting dictionary.
            candidate: Candidate profile dictionary.

        Returns:
            Filter result with individual component scores and pass/fail flags.
        """
        location_score = self._location_filter(job, candidate)
        salary_score = self._salary_filter(job, candidate)
        experience_score = self._experience_filter(job, candidate)
        skills_score = self._basic_skills_filter(job, candidate)
        remote_score = self._remote_fit_filter(job, candidate)

        return {
            "location": location_score,
            "salary": salary_score,
            "experience": experience_score,
            "skills": skills_score,
            "remote_fit": remote_score,
            "passed": all(
                s["score"] > 0.0
                for s in [location_score, salary_score, experience_score]
            ),
        }

    async def stage_2_semantic(self, job: dict, candidate: dict) -> dict:
        """Analyze skill equivalence and transferable skills.

        This stage performs deeper skill matching using alias mapping,
        related skill detection, and transferable skill analysis.

        Args:
            job: Job posting dictionary.
            candidate: Candidate profile dictionary.

        Returns:
            Semantic analysis result with skill match details.
        """
        job_skills = [
            s.lower().strip() if isinstance(s, str) else str(s).lower()
            for s in job.get("skills", [])
        ]
        candidate_skills = [
            s.lower().strip() if isinstance(s, str) else str(s).lower()
            for s in candidate.get("skills", [])
        ]

        exact_matches: list[str] = []
        equivalent_matches: list[dict] = []
        missing_skills: list[str] = []
        transferable: list[dict] = []

        for job_skill in job_skills:
            matched = False
            if job_skill in candidate_skills:
                exact_matches.append(job_skill)
                matched = True
            else:
                equiv_score = self._skill_equivalence(job_skill, candidate_skills)
                if equiv_score > 0.5:
                    equivalent_matches.append({
                        "job_skill": job_skill,
                        "match_score": equiv_score,
                    })
                    matched = True
                elif equiv_score > 0.2:
                    transferable.append({
                        "job_skill": job_skill,
                        "similarity_score": equiv_score,
                    })

            if not matched:
                missing_skills.append(job_skill)

        total_job_skills = len(job_skills) or 1
        matched_count = len(exact_matches) + len(equivalent_matches)
        skill_coverage = matched_count / total_job_skills

        return {
            "exact_matches": exact_matches,
            "equivalent_matches": equivalent_matches,
            "missing_skills": missing_skills,
            "transferable_skills": transferable,
            "skill_coverage": skill_coverage,
            "total_job_skills": len(job_skills),
            "total_matched": matched_count,
        }

    def stage_3_score(self, filter_result: dict, semantic_result: dict) -> dict:
        """Compute the final weighted score.

        Combines stage 1 filter scores and stage 2 semantic results
        using configurable weights.

        Args:
            filter_result: Result from stage_1_filter.
            semantic_result: Result from stage_2_semantic.

        Returns:
            Final score breakdown with total_score and individual components.
        """
        filter_scores = {
            "location": filter_result["location"]["score"],
            "salary": filter_result["salary"]["score"],
            "experience": filter_result["experience"]["score"],
            "remote_fit": filter_result["remote_fit"]["score"],
        }

        skills_weight = self.weights.get("skills", 0.40)
        semantic_weight = 0.7
        basic_weight = 0.3

        basic_skills = filter_result.get("skills", {}).get("score", 0.0)
        semantic_skills = semantic_result.get("skill_coverage", 0.0)
        combined_skills = (
            basic_skills * basic_weight + semantic_skills * semantic_weight
        )

        total_score = 0.0
        breakdown: dict[str, float] = {}

        for component, weight in self.weights.items():
            if component == "skills":
                component_score = combined_skills
            else:
                component_score = filter_scores.get(component, 0.0)

            weighted = component_score * weight
            breakdown[component] = round(component_score, 4)
            total_score += weighted

        total_score = round(total_score, 4)

        return {
            "total_score": total_score,
            "breakdown": breakdown,
            "filter_passed": filter_result.get("passed", False),
        }

    def explain_match(self, result: dict) -> str:
        """Generate a human-readable match explanation.

        Args:
            result: Combined match result from stage_3_score and previous stages.

        Returns:
            Multi-line explanation string highlighting strong, partial,
            and missing skills.
        """
        parts: list[str] = []
        total = result.get("total_score", 0.0)
        percentage = round(total * 100, 1)

        if total >= 0.8:
            parts.append(f"Strong match ({percentage}%)")
        elif total >= 0.5:
            parts.append(f"Moderate match ({percentage}%)")
        elif total >= 0.3:
            parts.append(f"Weak match ({percentage}%)")
        else:
            parts.append(f"Poor match ({percentage}%)")

        semantic = result.get("semantic", {})
        if not semantic and "filter" in result:
            return parts[0]

        exact = semantic.get("exact_matches", [])
        equivalent = semantic.get("equivalent_matches", [])
        missing = semantic.get("missing_skills", [])
        transferable = semantic.get("transferable_skills", [])

        if exact:
            parts.append(
                f"Strong skills: {', '.join(exact)}"
            )

        if equivalent:
            equiv_str = ", ".join(
                f"{m['job_skill']} (via {m['match_score']:.0%} equivalent)"
                for m in equivalent
            )
            parts.append(f"Partial skills: {equiv_str}")

        if transferable:
            trans_str = ", ".join(
                t["job_skill"] for t in transferable
            )
            parts.append(f"Transferable skills: {trans_str}")

        if missing:
            parts.append(
                f"Missing skills: {', '.join(missing)}"
            )

        breakdown = result.get("breakdown", {})
        strong_areas = [
            k for k, v in breakdown.items() if v >= 0.7
        ]
        weak_areas = [
            k for k, v in breakdown.items() if v < 0.3
        ]

        if strong_areas:
            parts.append(f"Strong areas: {', '.join(strong_areas)}")
        if weak_areas:
            parts.append(f"Weak areas: {', '.join(weak_areas)}")

        if not result.get("filter_passed", True):
            parts.append(
                "Note: Did not pass basic filters (location/salary/experience)"
            )

        return "\n".join(parts)

    def _skill_equivalence(self, skill: str, candidate_skills: list[str]) -> float:
        """Check how well a job skill matches candidate skills via aliases.

        Args:
            skill: The required skill to match.
            candidate_skills: List of candidate's skills.

        Returns:
            Similarity score from 0.0 (no match) to 1.0 (exact match).
        """
        skill_lower = skill.lower().strip()

        for candidate_skill in candidate_skills:
            if skill_lower == candidate_skill:
                return 1.0

        aliases = self.SKILL_ALIASES.get(skill_lower, [])
        for candidate_skill in candidate_skills:
            if candidate_skill in aliases:
                return 0.9
            for alias in aliases:
                if candidate_skill == alias:
                    return 0.9

        for candidate_skill in candidate_skills:
            if (
                skill_lower in candidate_skill
                or candidate_skill in skill_lower
            ):
                if abs(len(skill_lower) - len(candidate_skill)) <= 3:
                    return 0.7

        return 0.0

    def _experience_relevance(self, job_level: str, candidate_level: str) -> float:
        """Score relevance between job experience level and candidate level.

        Args:
            job_level: Required experience level string.
            candidate_level: Candidate's experience level string.

        Returns:
            Relevance score from 0.0 to 1.0.
        """
        job_rank = self._parse_level(job_level)
        candidate_rank = self._parse_level(candidate_level)

        if job_rank is None or candidate_rank is None:
            return 0.5

        diff = abs(job_rank - candidate_rank)
        if diff == 0:
            return 1.0
        elif diff == 1:
            return 0.7
        elif diff == 2:
            return 0.4
        else:
            return 0.1

    def _parse_level(self, level_str: str) -> int | None:
        """Parse a level string into a numeric rank.

        Args:
            level_str: Level string like "senior", "junior", etc.

        Returns:
            Numeric rank or None if not recognized.
        """
        if not level_str:
            return None

        level_lower = level_str.lower().strip()

        for keyword, rank in self.LEVEL_RANK.items():
            if keyword in level_lower:
                return rank

        numbers = re.findall(r"\d+", level_lower)
        if numbers:
            return int(numbers[0])

        return None

    def _location_filter(self, job: dict, candidate: dict) -> dict:
        """Filter by location compatibility."""
        job_location = job.get("location", "").lower()
        candidate_location = candidate.get("location", "").lower()
        candidate_preferences = [
            p.lower() for p in candidate.get("preferred_locations", [])
        ]

        if not job_location:
            return {"score": 1.0, "reason": "No location specified in job"}

        if job_location in candidate_location or candidate_location in job_location:
            return {"score": 1.0, "reason": "Exact location match"}

        if job_location in candidate_preferences:
            return {"score": 0.9, "reason": "Matches preferred location"}

        for pref in candidate_preferences:
            if pref in job_location or job_location in pref:
                return {"score": 0.7, "reason": "Partial location match"}

        if candidate_preferences:
            return {"score": 0.1, "reason": "Location mismatch"}

        return {"score": 0.5, "reason": "No candidate location preferences set"}

    def _salary_filter(self, job: dict, candidate: dict) -> dict:
        """Filter by salary range overlap."""
        job_salary_str = job.get("salary", "")
        candidate_min = candidate.get("salary_min")
        candidate_max = candidate.get("salary_max")

        if not job_salary_str:
            return {"score": 0.5, "reason": "No salary specified in job"}

        job_numbers = re.findall(r"[\d,]+(?:\.\d+)?", job_salary_str.replace(",", ""))
        if not job_numbers:
            return {"score": 0.5, "reason": "Could not parse job salary"}

        job_values = []
        for n in job_numbers:
            try:
                job_values.append(float(n))
            except ValueError:
                continue

        if not job_values:
            return {"score": 0.5, "reason": "No valid salary numbers found"}

        job_min = min(job_values)
        job_max = max(job_values)

        if candidate_min is None and candidate_max is None:
            return {"score": 0.5, "reason": "No candidate salary expectations set"}

        c_min = candidate_min or 0
        c_max = candidate_max or float("inf")

        if job_max >= c_min and job_min <= c_max:
            overlap = min(job_max, c_max) - max(job_min, c_min)
            range_size = max(job_max - job_min, c_max - c_min, 1)
            return {"score": min(overlap / range_size + 0.3, 1.0), "reason": "Salary ranges overlap"}

        if job_max < c_min:
            gap = c_min - job_max
            return {"score": max(0.0, 1.0 - gap / c_min), "reason": "Job salary below expectations"}

        if job_min > c_max:
            return {"score": 1.0, "reason": "Job salary exceeds expectations"}

        return {"score": 0.5, "reason": "Salary comparison inconclusive"}

    def _experience_filter(self, job: dict, candidate: dict) -> dict:
        """Filter by experience level match."""
        job_level = job.get("experience", "")
        candidate_level = candidate.get("experience_level", "")

        if not job_level:
            return {"score": 1.0, "reason": "No experience requirement specified"}

        relevance = self._experience_relevance(job_level, candidate_level)
        return {
            "score": relevance,
            "reason": f"Level relevance: {relevance:.0%}",
        }

    def _basic_skills_filter(self, job: dict, candidate: dict) -> dict:
        """Basic skills presence check."""
        job_skills = [
            s.lower() if isinstance(s, str) else str(s).lower()
            for s in job.get("skills", [])
        ]
        candidate_skills = [
            s.lower() if isinstance(s, str) else str(s).lower()
            for s in candidate.get("skills", [])
        ]

        if not job_skills:
            return {"score": 1.0, "reason": "No skills required"}

        matched = 0
        for skill in job_skills:
            if skill in candidate_skills:
                matched += 1
            else:
                equiv = self._skill_equivalence(skill, candidate_skills)
                if equiv > 0.5:
                    matched += equiv

        score = matched / len(job_skills) if job_skills else 1.0
        return {
            "score": round(score, 4),
            "reason": f"Basic skill match: {matched:.1f}/{len(job_skills)}",
        }

    def _remote_fit_filter(self, job: dict, candidate: dict) -> dict:
        """Filter by remote work compatibility."""
        job_remote = job.get("remote", False)
        job_location = job.get("location", "").lower()
        candidate_remote = candidate.get("remote_ok", False)
        candidate_location = candidate.get("location", "").lower()

        if job_remote or "remote" in job_location:
            if candidate_remote:
                return {"score": 1.0, "reason": "Both support remote work"}
            return {"score": 0.6, "reason": "Job is remote but candidate prefers on-site"}

        if candidate_remote and not job_remote:
            return {"score": 0.4, "reason": "Candidate prefers remote but job is on-site"}

        job_country = job_location.split(",")[-1].strip() if "," in job_location else job_location
        candidate_country = candidate_location.split(",")[-1].strip() if "," in candidate_location else candidate_location

        if job_country and candidate_country and job_country == candidate_country:
            return {"score": 0.8, "reason": "Same country for on-site role"}

        if not job_country or not candidate_country:
            return {"score": 0.5, "reason": "Cannot determine country compatibility"}

        return {"score": 0.3, "reason": "Different countries, on-site role"}
