"""Deterministic skill extraction from free text.

Extraction is boundary-aware (so ``C++``/``C#`` work, and ``go`` does not match
inside ``golang`` or the verb "go"), overlap-suppressed (``Java`` does not fire
inside ``JavaScript``) and context-gated for aliases that are also ordinary
words (``go``, ``ml``, ``ts``, ``r`` ...).

The extractor is intentionally dictionary + rules based: no network calls, no
language model, fully deterministic and cheap enough to run on every ingested
job.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Iterable

from backend.skills.vocabulary import SKILLS

# ---------------------------------------------------------------------------
# Text preparation
# ---------------------------------------------------------------------------

_BLOCK_END_RE = re.compile(r"</(?:p|div|li|h[1-6]|tr|ul|ol|table)\s*>", re.I)
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_INLINE_WS_RE = re.compile(r"[ \t\f\v\u00a0]+")
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")


def prepare_text(raw: str | None) -> str:
    """Best-effort HTML -> text while preserving block/line structure.

    Unlike :func:`normalizer._normalize_description` (which collapses all
    whitespace for storage), this keeps paragraph and list-item boundaries so
    the classifier can segment the description into sections.
    """
    if not raw:
        return ""
    text = _BR_RE.sub("\n", raw)
    text = _BLOCK_END_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _INLINE_WS_RE.sub(" ", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Pattern compilation
# ---------------------------------------------------------------------------


def _compile_alias(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias)
    left = r"(?<![A-Za-z0-9_])"
    # aliases ending in a non-alphanumeric (+/#) may be followed by a version
    # digit, e.g. "C++17", "C# 8"; only block a following letter to keep the
    # boundary meaningful.
    right = r"(?![A-Za-z])" if not alias[-1].isalnum() else r"(?![A-Za-z0-9_])"
    return re.compile(left + escaped + right, re.IGNORECASE)


@dataclass(frozen=True)
class _AliasPattern:
    alias: str
    pattern: re.Pattern[str]
    is_ambiguous: bool


#: canonical id -> list of compiled alias matchers (safe + ambiguous).
_PATTERNS: dict[str, list[_AliasPattern]] = {}
#: canonical id -> list of (alias, compiled context patterns) for ambiguous aliases
_CONTEXT: dict[str, list[tuple[str, tuple[re.Pattern[str], ...]]]] = {}

for _skill in SKILLS:
    matchers: list[_AliasPattern] = []
    for _alias in _skill.aliases:
        matchers.append(_AliasPattern(_alias, _compile_alias(_alias), False))
    ctx_entries: list[tuple[str, tuple[re.Pattern[str], ...]]] = []
    for _alias, _patterns in _skill.ambiguous:
        matchers.append(_AliasPattern(_alias, _compile_alias(_alias), True))
        ctx_entries.append((_alias, tuple(re.compile(p, re.I) for p in _patterns)))
    _PATTERNS[_skill.id] = matchers
    _CONTEXT[_skill.id] = ctx_entries
del _skill


@dataclass(frozen=True)
class SkillMatch:
    """A single raw match of a skill phrase in the text."""

    canonical: str
    display: str
    matched_text: str
    start: int
    end: int
    method: str  # "alias" | "context"
    ambiguous: bool


def _context_ok(text: str, start: int, end: int, patterns: tuple[re.Pattern[str], ...], window: int = 80) -> bool:
    lo = max(0, start - window)
    hi = min(len(text), end + window)
    snippet = text[lo:hi]
    return any(p.search(snippet) for p in patterns)


_NEIGHBOUR_WINDOW = 40


def extract_matches(text: str) -> list[SkillMatch]:
    """Return every (overlap-suppressed) skill match in ``text``.

    Ambiguous aliases are accepted when corroborating context appears nearby,
    or when an unambiguous skill appears within ``_NEIGHBOUR_WINDOW`` characters
    (a comma/phrase list such as "Go, Rust, Terraform" is a strong signal that
    the ambiguous token is a skill too).
    """
    if not text:
        return []

    # Pass 1: unambiguous aliases.
    base: list[SkillMatch] = []
    ambiguous_candidates: list[tuple[SkillMatch, tuple[re.Pattern[str], ...]]] = []
    for skill in SKILLS:
        ambiguous_aliases = {a for a, _ in skill.ambiguous}
        for matcher in _PATTERNS[skill.id]:
            for m in matcher.pattern.finditer(text):
                match = SkillMatch(
                    canonical=skill.id,
                    display=skill.display,
                    matched_text=text[m.start():m.end()],
                    start=m.start(),
                    end=m.end(),
                    method="context" if matcher.is_ambiguous else "alias",
                    ambiguous=matcher.is_ambiguous,
                )
                if matcher.is_ambiguous:
                    ctx = next((c for a, c in _CONTEXT[skill.id] if a == matcher.alias), ())
                    ambiguous_candidates.append((match, ctx))
                else:
                    base.append(match)

    # Pass 2: ambiguous aliases, accepted via context or nearby unambiguous skill.
    accepted = list(base)
    for match, ctx in ambiguous_candidates:
        if _context_ok(text, match.start, match.end, ctx) or _has_skill_neighbour(match, base):
            accepted.append(match)

    return _suppress_overlaps(accepted)


def _has_skill_neighbour(match: SkillMatch, base: list[SkillMatch]) -> bool:
    for other in base:
        if other.end <= match.start:
            if match.start - other.end <= _NEIGHBOUR_WINDOW:
                return True
        elif other.start >= match.end:
            if other.start - match.end <= _NEIGHBOUR_WINDOW:
                return True
    return False


def _suppress_overlaps(matches: Iterable[SkillMatch]) -> list[SkillMatch]:
    """Drop a match fully contained in a longer match.

    Prevents a short alias (``react``) from firing inside a longer one
    (``react native``) while keeping the longest, most specific match.
    """
    by_span = sorted(matches, key=lambda m: (m.start, -(m.end - m.start)))
    kept: list[SkillMatch] = []
    for m in by_span:
        contained = any(
            k.start <= m.start and k.end >= m.end and (k.end - k.start) > (m.end - m.start)
            for k in kept
        )
        if not contained:
            kept.append(m)
    return kept
