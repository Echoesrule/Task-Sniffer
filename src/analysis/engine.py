"""Job Analysis Engine - orchestrates match scoring and scam detection."""

import json
import logging
from typing import Any

from src.analysis.match_engine import MatchScoreEngine
from src.analysis.scam_detector import ScamRiskDetector

logger = logging.getLogger(__name__)


class JobAnalysisEngine:
    """Combine match scoring and scam detection for comprehensive job analysis."""

    def __init__(self) -> None:
        self.match_engine = MatchScoreEngine()
        self.scam_detector = ScamRiskDetector()

    def analyze(self, job: dict[str, Any], preferences: dict[str, Any]) -> dict[str, Any]:
        """Full analysis: match score + scam risk. Returns enriched job dict."""
        match_result = self.match_engine.score(job, preferences)
        risk_result = self.scam_detector.analyze(job)

        job["match_score"] = match_result["match_score"]
        match_tech = job.get("tech_stack", [])
        if isinstance(match_tech, str):
            try:
                match_tech = json.loads(match_tech)
            except (json.JSONDecodeError, TypeError):
                match_tech = []
        job["tech_stack"] = match_tech
        job["match_breakdown"] = match_result["breakdown"]
        job["match_level"] = match_result["match_level"]

        job["risk_score"] = risk_result["risk_score"]
        job["risk_level"] = risk_result["risk_level"]
        job["risk_flags"] = risk_result["flags"]
        job["is_suspicious"] = risk_result["is_suspicious"]

        job["should_apply"] = (
            match_result["match_score"] >= 60
            and not risk_result["is_suspicious"]
        )

        return job

    def analyze_batch(
        self, jobs: list[dict[str, Any]], preferences: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Analyze a batch of jobs. Returns enriched list sorted by match score."""
        analyzed = [self.analyze(job, preferences) for job in jobs]
        analyzed.sort(key=lambda j: j.get("match_score", 0), reverse=True)
        return analyzed
