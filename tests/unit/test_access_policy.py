"""Tests for the source access-policy (spec §1-2)."""

from backend.sources.models import (
    AccessMethod,
    PermissionStatus,
    ProvenanceClass,
    RobotsStatus,
    SourceConfig,
    SourceStatus,
)
from backend.sources.registry import default_registry


def test_approved_source_is_crawlable():
    cfg = default_registry.get("corporatestaffing")
    assert cfg is not None
    assert cfg.has_approved_access
    assert cfg.crawlable
    assert default_registry.refuse_reason("corporatestaffing") is None


def test_review_source_is_refused():
    cfg = default_registry.get("brightermonday")
    assert cfg is not None
    assert not cfg.has_approved_access
    assert not cfg.crawlable
    reason = default_registry.refuse_reason("brightermonday")
    assert reason and "REVIEW" in reason


def test_restricted_source_is_refused():
    cfg = default_registry.get("wellfound")
    assert cfg is not None
    assert not cfg.crawlable
    reason = default_registry.refuse_reason("wellfound")
    assert reason and "RESTRICTED" in reason


def test_unknown_source_not_registered():
    assert default_registry.get("nonsense-source") is None
    assert "not registered" in default_registry.refuse_reason("nonsense-source")


def test_paused_source_not_crawlable_until_retry_at():
    cfg = SourceConfig(
        name="x",
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED,
        source_status=SourceStatus.PAUSED,
        pause_reason="RATE_LIMITED",
    )
    assert not cfg.crawlable


def test_registry_crawlable_only_approved():
    names = {s.name for s in default_registry.crawlable()}
    assert "corporatestaffing" in names
    assert "kra" in names
    assert "fuzu" not in names
    assert "myjobmag" not in names
    assert "brightermonday" not in names
    assert "wellfound" not in names


def test_requested_sources_are_registered_with_safe_activation_defaults():
    expected = {
        "brightermonday",
        "myjobmag",
        "fuzu",
        "careerpointkenya",
        "corporatestaffing",
        "jobwebkenya",
        "greenhouse",
        "ashby",
        "workable",
        "remotive",
        "linkedin",
        "fiverr",
    }
    assert expected <= set(default_registry.names())

    for name in (
        "brightermonday", "careerpointkenya", "jobwebkenya", "workable",
        "fuzu", "myjobmag",
    ):
        cfg = default_registry.get(name)
        assert cfg is not None
        assert cfg.source_status == SourceStatus.DISABLED
        assert not cfg.crawlable

    for name in ("remotive", "linkedin", "fiverr"):
        cfg = default_registry.get(name)
        assert cfg is not None
        assert cfg.permission_blocked
        assert cfg.source_status == SourceStatus.DISABLED
        assert not cfg.crawlable

    assert default_registry.get("myjobmag").access_method == AccessMethod.HTML
    assert default_registry.get("fuzu").permission_status == PermissionStatus.RESTRICTED
    assert default_registry.get("myjobmag").permission_status == PermissionStatus.REVIEW


def test_ats_board_configuration_requires_known_ids_and_explicit_opt_in():
    from backend.sources.registry import (
        _board_source_enabled,
        _configured_ids,
        _explicitly_enabled,
    )

    empty_env = {}
    assert _configured_ids("GREENHOUSE_BOARD_TOKENS", empty_env) == []
    assert _configured_ids("ASHBY_BOARD_NAMES", empty_env) == []
    assert not _explicitly_enabled("GREENHOUSE_ENABLED", empty_env)
    assert not _explicitly_enabled("ASHBY_ENABLED", empty_env)
    assert not _board_source_enabled(
        "GREENHOUSE_BOARD_TOKENS", "GREENHOUSE_ENABLED", empty_env
    )

    env = {
        "GREENHOUSE_BOARD_TOKENS": "acme, good-board,invalid/token,,",
        "GREENHOUSE_ENABLED": "true",
    }
    assert _configured_ids("GREENHOUSE_BOARD_TOKENS", env) == ["acme", "good-board"]
    assert _explicitly_enabled("GREENHOUSE_ENABLED", env)
    assert not _explicitly_enabled("ASHBY_ENABLED", env)
    assert _board_source_enabled(
        "GREENHOUSE_BOARD_TOKENS", "GREENHOUSE_ENABLED", env
    )
    assert not _board_source_enabled(
        "ASHBY_BOARD_NAMES", "ASHBY_ENABLED", env
    )
    assert not _board_source_enabled(
        "GREENHOUSE_BOARD_TOKENS",
        "GREENHOUSE_ENABLED",
        {"GREENHOUSE_BOARD_TOKENS": "acme"},
    )


def test_workable_is_not_enabled_while_downstream_terms_are_unreviewed():
    cfg = default_registry.get("workable")
    assert cfg is not None
    assert cfg.permission_status == PermissionStatus.REVIEW
    assert "WORKABLE_ACCOUNT_SUBDOMAINS" in (cfg.pause_reason or "")
    assert "redistribution terms are unverified" in (cfg.pause_reason or "")


def test_official_provenance_strength():
    assert ProvenanceClass.OFFICIAL.value == "official"
    kra = default_registry.get("kra")
    assert kra is not None
    assert kra.provenance == ProvenanceClass.OFFICIAL
    assert kra.requires_auth is True


def test_rookie_config_defaults():
    cfg = SourceConfig(name="new")
    assert cfg.permission_status == PermissionStatus.REVIEW
    assert not cfg.has_approved_access
