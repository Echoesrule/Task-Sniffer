"""Multi-stage job matching engine."""

from backend.matching.engine import MatchingEngine
from backend.matching.scoring import (
    DEFAULT_CANDIDATE,
    DEFAULT_USER_EMAIL,
    apply_score,
    candidate_to_scoring_dict,
    ensure_default_candidate,
    job_to_scoring_dict,
    load_candidate,
    score_job,
)

__all__ = [
    "MatchingEngine",
    "DEFAULT_CANDIDATE",
    "DEFAULT_USER_EMAIL",
    "apply_score",
    "candidate_to_scoring_dict",
    "ensure_default_candidate",
    "job_to_scoring_dict",
    "load_candidate",
    "score_job",
]
