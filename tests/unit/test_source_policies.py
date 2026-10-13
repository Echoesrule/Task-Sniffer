"""Tests for Phase 4 source-specific domain policies (spec §8)."""

from __future__ import annotations

import asyncio

import pytest

from backend.scrapers import policy
from backend.scrapers.factory import (
    UnconfiguredSourceError,
    _LegacyAdapter,
    build_adapter,
)
from backend.sources.models import (
    AccessMethod,
    PermissionStatus,
    ProvenanceClass,
    SourceConfig,
)


def _config(name: str, extra_urls: list[str] | None = None) -> SourceConfig:
    return SourceConfig(
        name=name,
        url="https://example.invalid",
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED,
        provenance=ProvenanceClass.JOB_BOARD,
        extra_urls=extra_urls or [],
        rate_limit=0.0,
    )


async def _close_legacy(adapter: _LegacyAdapter) -> None:
    await adapter.close()
    await adapter._legacy._client.aclose()


def test_every_legacy_policy_is_configured():
    assert policy.LEGACY_SOURCE_POLICIES
    for name, pol in policy.LEGACY_SOURCE_POLICIES.items():
        assert pol.configured, f"{name} must declare a trusted domain"
        assert pol.allowed_domains, f"{name} must declare allowed_domains"


def test_get_policy_is_case_insensitive_and_absent_safe():
    assert policy.get_policy("GreenHouse") is policy.get_policy("greenhouse")
    assert policy.get_policy("does-not-exist") is None
    assert policy.get_policy("") is None


def test_report_covers_every_registered_source():
    from backend.sources.registry import default_registry

    report = policy.source_policy_report()
    assert report
    assert {r["name"] for r in report} == {c.name for c in default_registry.all()}


def test_every_report_entry_has_shape():
    for row in policy.source_policy_report():
        assert set(row) >= {"name", "kind", "configured", "allowed_domains", "job_url_patterns"}
        assert row["kind"] in {"adapter", "legacy", "unconfigured"}


def test_unconfigured_sources_are_surfaced():
    names = policy.unconfigured_sources()
    assert "careerpointkenya" in names
    assert "greenhouse" not in names


def test_legacy_adapter_applies_policy():
    adapter = build_adapter(_config("greenhouse", ["acme"]))
    try:
        assert isinstance(adapter, _LegacyAdapter)
        assert "greenhouse.io" in adapter.expected_domains()
        assert adapter.job_url_patterns
    finally:
        asyncio.run(_close_legacy(adapter))


def test_legacy_adapter_fails_closed_when_no_policy(monkeypatch):
    monkeypatch.setattr(policy, "LEGACY_SOURCE_POLICIES", {})
    adapter = _LegacyAdapter(_config("greenhouse"), "GreenhouseScraper")
    try:
        assert adapter.expected_domains() == set()
        assert adapter.job_url_patterns == []
    finally:
        asyncio.run(_close_legacy(adapter))


def test_unconfigured_source_raises_typed_error():
    with pytest.raises(UnconfiguredSourceError):
        build_adapter(_config("careerpointkenya"))
