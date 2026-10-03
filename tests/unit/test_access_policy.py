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
    cfg = default_registry.get("fuzu")
    assert cfg is not None
    assert cfg.has_approved_access
    assert cfg.crawlable
    assert default_registry.refuse_reason("fuzu") is None


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
    assert "fuzu" in names
    assert "myjobmag" in names
    assert "kra" in names
    assert "brightermonday" not in names
    assert "wellfound" not in names


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