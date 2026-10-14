"""Tests for the deterministic skills extraction / classification pipeline."""

from backend.skills import analyze_skills, extract_matches, normalize_skill, normalize_skill_list
from backend.skills.extractor import prepare_text


# ---------------------------------------------------------------------------
# Vocabulary / normalization
# ---------------------------------------------------------------------------


def test_normalize_aliases():
    assert normalize_skill("JS") == "javascript"
    assert normalize_skill("Postgres") == "postgresql"
    assert normalize_skill("k8s") == "kubernetes"
    assert normalize_skill(".NET") == "dotnet"
    assert normalize_skill("sklearn") == "scikit-learn"
    assert normalize_skill("Fast API") == "fastapi"


def test_normalize_preserves_distinct_skills():
    # formerly collapsed into other canonical ids
    assert normalize_skill("flutter") == "flutter"
    assert normalize_skill("dart") == "dart"
    assert normalize_skill("solidity") == "solidity"
    assert normalize_skill("bigquery") == "bigquery"
    assert normalize_skill("GitHub") == "git"


def test_normalize_skill_list_keeps_unknown():
    result = normalize_skill_list(["PY3", "unknownskill", "Postgres", "PY3"])
    assert "python" in result
    assert "postgresql" in result
    assert "unknownskill" in result
    # deduplicated
    assert result.count("python") == 1


def test_normalize_go_and_r_are_canonical():
    assert normalize_skill("go") == "go"
    assert normalize_skill("golang") == "go"
    assert normalize_skill("r") == "r"


# ---------------------------------------------------------------------------
# Extraction boundaries
# ---------------------------------------------------------------------------


def test_boundary_cpp_and_csharp_detected():
    skills = analyze_skills("We hire C++ and C# engineers", "").skills
    assert "c++" in skills
    assert "c#" in skills


def test_cpp_version_suffix_detected():
    assert "c++" in analyze_skills("Modern C++17 development", "").skills


def test_go_verb_not_detected():
    assert "go" not in analyze_skills("We go to market quickly", "").skills


def test_go_language_detected_with_context():
    assert "go" in analyze_skills("Experience in Go", "").skills
    assert "go" in analyze_skills("Senior Golang Engineer", "").skills


def test_go_in_skill_list_detected_via_neighbour():
    skills = analyze_skills("Nice to have: Go, Rust, Terraform", "").skills
    assert {"go", "rust", "terraform"} <= set(skills)


def test_react_native_not_reported_as_react():
    skills = analyze_skills("We build React Native apps", "").skills
    assert "react native" in skills


def test_java_not_matched_inside_javascript():
    skills = analyze_skills("JavaScript everywhere", "").skills
    assert "javascript" in skills
    assert "java" not in skills


def test_ambiguous_ts_requires_context():
    assert "typescript" not in analyze_skills("Send your ts by Friday", "").skills
    assert "typescript" in analyze_skills("React + TS stack", "").skills


def test_bare_rest_word_not_matched():
    # "rest" as an ordinary word must not become "rest api"
    assert "rest api" not in analyze_skills("Take a rest after lunch", "").skills
    assert "rest api" in analyze_skills("Build REST APIs", "").skills


def test_html_is_stripped_but_structure_preserved():
    text = prepare_text("<p>Requirements:</p><ul><li>Python</li><li>SQL</li></ul>")
    assert "<" not in text
    assert "Requirements:" in text
    assert text.count("\n") >= 1


# ---------------------------------------------------------------------------
# Classification: required / preferred / negation
# ---------------------------------------------------------------------------


_SAMPLE = """
About the role
We are looking for a Senior Backend Engineer.

Requirements:
- Strong experience with Python and Django
- Proficiency in PostgreSQL and Redis
- Experience with Docker and Kubernetes (AWS a plus)

Nice to have: Go, Terraform

Responsibilities:
- Build REST APIs and GraphQL services
- No prior experience with Rust required
"""


def test_classification_required():
    a = analyze_skills("Senior Backend Engineer", _SAMPLE)
    assert {"python", "django", "docker", "kubernetes", "postgresql"} <= set(a.required)


def test_classification_preferred():
    a = analyze_skills("Senior Backend Engineer", _SAMPLE)
    assert {"aws", "terraform", "go"} <= set(a.preferred)
    # preferred skills are not in required
    assert not (set(a.preferred) & set(a.required))


def test_negation_excludes_skill():
    a = analyze_skills("Senior Backend Engineer", _SAMPLE)
    assert "rust" not in a.skills
    detail = {d["skill"]: d for d in a.detail}
    assert detail["rust"]["negated"] is True
    assert detail["rust"]["classification"] == "negated"


def test_detail_provenance_fields():
    a = analyze_skills("Dev", "Requirements: Strong Python experience")
    rec = next(d for d in a.detail if d["skill"] == "python")
    assert rec["section"] == "requirements"
    assert rec["classification"] == "required"
    assert rec["method"] in {"alias", "context"}
    assert "python" in rec["context"].lower()
    assert rec["occurrences"] >= 1


def test_empty_input():
    a = analyze_skills("", "")
    assert a.skills == []
    assert a.required == []
    assert a.preferred == []
    assert a.detail == []


def test_overlap_suppression_keeps_longest():
    matches = extract_matches("We use React Native and React")
    canonicals = {m.canonical for m in matches}
    assert "react native" in canonicals
