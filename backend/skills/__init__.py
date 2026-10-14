"""Deterministic, dictionary-based skill extraction and classification.

Public entry point: :func:`analyze_skills`.
"""

from backend.skills.classifier import SkillAnalysis, SkillRecord, analyze_skills
from backend.skills.extractor import SkillMatch, extract_matches, prepare_text
from backend.skills.vocabulary import (
    SKILLS,
    TECH_SKILL_MAP,
    normalize_skill,
    normalize_skill_list,
)

__all__ = [
    "SkillAnalysis",
    "SkillMatch",
    "SkillRecord",
    "analyze_skills",
    "extract_matches",
    "normalize_skill",
    "normalize_skill_list",
    "prepare_text",
    "SKILLS",
    "TECH_SKILL_MAP",
]
