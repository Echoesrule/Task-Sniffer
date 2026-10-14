"""Classification of extracted skills into required / preferred / responsibility.

Uses deterministic section segmentation and marker keywords.  No language model
is involved.  Negated mentions are retained in the detail payload (with a flag)
but excluded from the canonical/required/preferred lists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.skills.extractor import SkillMatch, extract_matches, prepare_text
from backend.skills.vocabulary import SKILL_BY_ID

#: priority order used when a skill appears in several contexts.
_PRIORITY = {"required": 4, "preferred": 3, "responsibility": 2, "mention": 1, "negated": 0}

#: section headings, in precedence order (first match wins on ties).
_SECTION_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("preferred", r"\b(?:preferred(?:\s+(?:qualifications?|skills?))?|nice[ -]to[ -]have|good to have|bonus points?|a (?:big )?plus|desirable|optional)\b"),
    ("requirements", r"\b(?:requirements?|qualifications?|minimum qualifications?|what you(?:'|’)?ll need|what we(?:'|’)?re looking for|must[ -]haves?|required (?:skills?|experience|qualifications?)|key skills?|who you are)\b"),
    ("responsibilities", r"\b(?:responsibilities|what you(?:'|’)?ll do|the role|your role|key duties|duties|day[ -]to[ -]day|you will)\b"),
    ("about", r"\b(?:about us|about the (?:company|team)|company overview|who we are|benefits|perks|what we offer|why join)\b"),
)

_REQUIRED_RE = re.compile(
    r"\b(?:required|must(?: have)?|strong(?:ly)?|proficien\w+|expert(?:ise)?|expertise|"
    r"hands[ -]on|solid|advanced|deep (?:knowledge|understanding)|experience (?:in|with)|"
    r"knowledge of|familiar(?:ity)? with|skilled in|extensive)\b",
    re.I,
)
_PREFERRED_RE = re.compile(
    r"\b(?:preferred|nice[ -]to[ -]have|a plus|bonus|desirable|optional|good to have|plus(?:es)?)\b",
    re.I,
)
_NEGATION_BEFORE_RE = re.compile(
    r"\b(?:no|not|without|never|don'?t|doesn'?t|do not|does not|no prior)\b",
    re.I,
)
_NEGATION_AFTER_RE = re.compile(
    r"^\s*(?:not|isn'?t|is not|aren'?t|are not|not required|not necessary|not needed)\b",
    re.I,
)

_SENTENCE_BREAK = re.compile(r"[.!?;\n]\s")


@dataclass
class SkillRecord:
    """Provenance/classification for one canonical skill in a posting."""

    skill: str
    display: str
    matched_text: str
    method: str
    ambiguous: bool
    section: str
    classification: str
    negated: bool
    occurrences: int
    context: str

    def as_dict(self) -> dict[str, object]:
        return {
            "skill": self.skill,
            "display": self.display,
            "matched_text": self.matched_text,
            "method": self.method,
            "ambiguous": self.ambiguous,
            "section": self.section,
            "classification": self.classification,
            "negated": self.negated,
            "occurrences": self.occurrences,
            "context": self.context,
        }


@dataclass
class SkillAnalysis:
    """Result of analysing a posting's title + description for skills."""

    skills: list[str] = field(default_factory=list)
    required: list[str] = field(default_factory=list)
    preferred: list[str] = field(default_factory=list)
    detail: list[dict[str, object]] = field(default_factory=list)

    @property
    def canonical(self) -> list[str]:
        return self.skills


# ---------------------------------------------------------------------------
# Section segmentation
# ---------------------------------------------------------------------------


def _heading_spans(text: str) -> list[tuple[int, str]]:
    """Return ``(position, section_name)`` for heading-like keyword hits."""
    spans: list[tuple[int, str]] = []
    for name, pattern in _SECTION_KEYWORDS:
        for m in re.finditer(pattern, text, re.I):
            if _looks_like_heading(text, m.start(), m.end()):
                spans.append((m.start(), name))
    spans.sort(key=lambda s: s[0])
    return spans


def _looks_like_heading(text: str, start: int, end: int) -> bool:
    i = start - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    at_line_start = i < 0 or text[i] == "\n"

    j = end
    while j < len(text) and text[j] in " \t":
        j += 1
    followed_by_colon = j < len(text) and text[j] == ":"

    return at_line_start or followed_by_colon


def _section_for(pos: int, spans: list[tuple[int, str]]) -> str:
    section = "intro"
    for start, name in spans:
        if start <= pos:
            section = name
        else:
            break
    return section


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _sentence_around(text: str, start: int, end: int) -> str:
    lower_bound = max(0, start - 200)
    cut = text.rfind("\n", lower_bound, start)
    for m in _SENTENCE_BREAK.finditer(text, lower_bound, start):
        cut = m.end()
    if cut == -1:
        cut = lower_bound
    upper = min(len(text), end + 120)
    stop = text.find("\n", end, upper)
    if stop != -1:
        upper = stop
    return text[cut:upper]


def _is_negated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 45):start]
    if _NEGATION_BEFORE_RE.search(before):
        return True
    after = text[end:end + 18]
    return bool(_NEGATION_AFTER_RE.search(after))


def _interval_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    if a[1] <= b[0]:
        return b[0] - a[1]
    if a[0] >= b[1]:
        return a[0] - b[1]
    return 0


def _nearest_preferred(text: str, matches: list[SkillMatch]) -> set[int]:
    """Index set of matches that a preferred marker most directly modifies.

    For "Docker and Kubernetes (AWS a plus)", the "a plus" is assigned to AWS
    (the nearest skill) rather than to Kubernetes.
    """
    indexes: set[int] = set()
    for marker in _PREFERRED_RE.finditer(text):
        span = (marker.start(), marker.end())
        nearest_idx = min(
            range(len(matches)),
            key=lambda i: _interval_distance(span, (matches[i].start, matches[i].end)),
        )
        indexes.add(nearest_idx)
    return indexes


def _classify(text: str, match: SkillMatch, section: str, local_preferred: bool) -> tuple[str, bool]:
    negated = _is_negated(text, match.start, match.end)
    sentence = _sentence_around(text, match.start, match.end)
    has_required = bool(_REQUIRED_RE.search(sentence))
    has_preferred = bool(_PREFERRED_RE.search(sentence))

    if negated:
        return "negated", True
    if local_preferred or (has_preferred and not has_required):
        return "preferred", False
    if section == "preferred":
        return "preferred", False
    if has_required:
        return "required", False
    if section == "requirements":
        return "required", False
    if section == "responsibilities":
        return "responsibility", False
    return "mention", False


def _snippet(text: str, start: int, end: int, width: int = 90) -> str:
    lo = max(0, start - width)
    hi = min(len(text), end + width)
    snippet = re.sub(r"\s+", " ", text[lo:hi]).strip()
    return snippet[:200]


def analyze_skills(title: str | None, description: str | None) -> SkillAnalysis:
    """Full pipeline: prepare -> extract -> classify -> aggregate."""
    text = prepare_text(f"{title or ''}\n{description or ''}").strip()
    if not text:
        return SkillAnalysis()

    matches = extract_matches(text)
    if not matches:
        return SkillAnalysis()

    spans = _heading_spans(text)
    preferred_idx = _nearest_preferred(text, matches)

    grouped: dict[str, list[tuple[SkillMatch, str, bool]]] = {}
    for idx, match in enumerate(matches):
        section = _section_for(match.start, spans)
        classification, negated = _classify(text, match, section, idx in preferred_idx)
        grouped.setdefault(match.canonical, []).append((match, classification, negated))

    records: list[SkillRecord] = []
    for canonical, occurrences in grouped.items():
        best = max(occurrences, key=lambda o: (_PRIORITY[o[1]], -o[0].start))
        match, classification, negated = best
        all_negated = all(o[2] for o in occurrences)
        records.append(
            SkillRecord(
                skill=canonical,
                display=SKILL_BY_ID[canonical].display,
                matched_text=match.matched_text,
                method=match.method,
                ambiguous=match.ambiguous,
                section=_section_for(match.start, spans),
                classification=classification,
                negated=all_negated,
                occurrences=len(occurrences),
                context=_snippet(text, match.start, match.end),
            )
        )

    records.sort(key=lambda r: r.skill)
    active = [r for r in records if not r.negated]

    return SkillAnalysis(
        skills=sorted({r.skill for r in active}),
        required=sorted({r.skill for r in active if r.classification == "required"}),
        preferred=sorted({r.skill for r in active if r.classification == "preferred"}),
        detail=[r.as_dict() for r in records],
    )
