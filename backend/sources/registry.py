"""Source registry.

Single place that records, for every known source, its audited access method
and permission status (spec §2). The ingestion engine consults this registry
and refuses to crawl sources whose permission status is REVIEW/RESTRICTED/
DISABLED.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.sources.models import (
    AccessMethod,
    PermissionStatus,
    ProvenanceClass,
    RobotsStatus,
    SourceConfig,
    SourceStatus,
    TermsStatus,
)


def _audited(
    name: str,
    access_method: AccessMethod,
    permission: PermissionStatus,
    *,
    url: str = "",
    feed_url: str = "",
    robots: RobotsStatus = RobotsStatus.ALLOWED,
    terms: TermsStatus = TermsStatus.REVIEWED,
    provenance: ProvenanceClass = ProvenanceClass.JOB_BOARD,
    country: str = "KE",
    tier: int = 1,
    rate_limit: float = 3.0,
    requires_auth: bool = False,
    schedule_minutes: int = 60,
    notes: str = "",
    active: bool = True,
) -> SourceConfig:
    return SourceConfig(
        name=name,
        url=url,
        feed_url=feed_url,
        access_method=access_method,
        permission_status=permission,
        robots_status=robots,
        terms_status=terms,
        provenance=provenance,
        country_focus=country,
        tier=tier,
        rate_limit=rate_limit,
        requires_auth=requires_auth,
        schedule_minutes=schedule_minutes,
        last_audited=datetime.now(timezone.utc),
        source_status=SourceStatus.ACTIVE if active else SourceStatus.DISABLED,
        pause_reason=notes or None,
    )


# ---------------------------------------------------------------------------
# Milestone 1 audit results (see docs/source_audit.md, 2026-08-30)
# ---------------------------------------------------------------------------

SOURCE_REGISTRY: dict[str, SourceConfig] = {
    # --- Approved (implement) -------------------------------------------
    "fuzu": _audited(
        "fuzu",
        AccessMethod.HTML,
        PermissionStatus.APPROVED,
        url="https://www.fuzu.com/kenya/jobs",
        robots=RobotsStatus.ALLOWED,
        provenance=ProvenanceClass.JOB_BOARD,
        rate_limit=3.0,
        schedule_minutes=45,
        notes="robots allowed; publishes kenya/sitemap-job-listings.xml.gz",
    ),
    "myjobmag": _audited(
        "myjobmag",
        AccessMethod.RSS,
        PermissionStatus.APPROVED,
        url="https://www.myjobmag.co.ke/jobs",
        robots=RobotsStatus.PARTIAL,
        provenance=ProvenanceClass.JOB_BOARD,
        rate_limit=5.0,
        schedule_minutes=45,
        notes=(
            "robots blocks all query-string URLs (/*?), /search/jobs?*, /apply-now/, "
            "/job-application/. Crawl only /jobs and detail pages /job/<slug>; a "
            "verified RSS feed URL can be set via feed_url."
        ),
    ),
    "corporatestaffing": _audited(
        "corporatestaffing",
        AccessMethod.HTML,
        PermissionStatus.APPROVED,
        url="https://www.corporatestaffing.co.ke",
        robots=RobotsStatus.ALLOWED,
        provenance=ProvenanceClass.JOB_BOARD,
        rate_limit=5.0,
        schedule_minutes=60,
    ),
    "careerpointkenya": _audited(
        "careerpointkenya",
        AccessMethod.HTML,
        PermissionStatus.APPROVED,
        url="https://www.careerpointkenya.co.ke",
        robots=RobotsStatus.ALLOWED,
        provenance=ProvenanceClass.JOB_BOARD,
        rate_limit=5.0,
        schedule_minutes=60,
    ),
    # --- Official (very high provenance; applying is auth-gated) --------
    "kra": _audited(
        "kra",
        AccessMethod.HTML,
        PermissionStatus.APPROVED,
        url="https://www.kra.go.ke/careers",
        robots=RobotsStatus.NONE,
        provenance=ProvenanceClass.OFFICIAL,
        rate_limit=5.0,
        requires_auth=True,
        schedule_minutes=240,
        notes="government source; application_url is erecruitment.kra.go.ke portal (account)",
    ),
    "psc": _audited(
        "psc",
        AccessMethod.HTML,
        PermissionStatus.APPROVED,
        url="https://www.publicservice.go.ke/jobs/",
        robots=RobotsStatus.ALLOWED,
        provenance=ProvenanceClass.OFFICIAL,
        rate_limit=6.0,
        requires_auth=True,
        schedule_minutes=240,
        notes="government source; applications via psckjobs.go.ke portal (account)",
    ),
    # --- Approved existing/legacy sources (kept crawlable) --------------
    "myjobskenya": _audited(
        "myjobskenya",
        AccessMethod.HTML,
        PermissionStatus.APPROVED,
        url="https://www.myjobskenya.com",
        provenance=ProvenanceClass.JOB_BOARD,
        rate_limit=3.0,
        schedule_minutes=60,
    ),
    "jobicy": _audited(
        "jobicy",
        AccessMethod.RSS,
        PermissionStatus.APPROVED,
        url="https://jobicy.com",
        country="GLOBAL",
        tier=2,
        rate_limit=5.0,
        schedule_minutes=180,
    ),
    "greenhouse": _audited(
        "greenhouse",
        AccessMethod.API,
        PermissionStatus.APPROVED,
        url="https://boards-api.greenhouse.io",
        country="GLOBAL",
        tier=2,
        rate_limit=1.5,
        schedule_minutes=180,
        notes="official public boards API",
    ),
    "ashby": _audited(
        "ashby",
        AccessMethod.API,
        PermissionStatus.APPROVED,
        url="https://api.ashbyhq.com",
        country="GLOBAL",
        tier=2,
        rate_limit=1.5,
        schedule_minutes=180,
        notes="official public posting API",
    ),
    # --- REVIEW (do not enable until re-audited) -------------------------
    "brightermonday": _audited(
        "brightermonday",
        AccessMethod.HTML,
        PermissionStatus.REVIEW,
        url="https://www.brightermonday.co.ke",
        robots=RobotsStatus.UNKNOWN,
        terms=TermsStatus.UNCLEAR,
        rate_limit=5.0,
        active=False,
notes=(
            "no public API; robots/terms at .co.ke unverified; "
            "legacy adapter points at stale .com domain. Keep off until re-audited."
        ),
    ),
    # --- RESTRICTED (never scrape) --------------------------------------
    "wellfound": _audited(
        "wellfound",
        AccessMethod.MANUAL,
        PermissionStatus.RESTRICTED,
        url="https://wellfound.com",
        robots=RobotsStatus.BLOCKED,
        terms=TermsStatus.UNCLEAR,
        country="GLOBAL",
        tier=2,
        active=False,
        notes=(
            "Cloudflare 403 even for /robots.txt and public API; no approved "
            "automated access path. Requires official API/partnership."
        ),
    ),
}


class SourceRegistry:
    """Access-policy resolver backed by :data:`SOURCE_REGISTRY`."""

    def __init__(self, overrides: dict[str, SourceConfig] | None = None) -> None:
        self._sources: dict[str, SourceConfig] = dict(SOURCE_REGISTRY)
        if overrides:
            self._sources.update(overrides)

    def get(self, name: str) -> SourceConfig | None:
        return self._sources.get(name)

    def all(self) -> list[SourceConfig]:
        return sorted(self._sources.values(), key=lambda s: (s.tier, s.name))

    def names(self) -> list[str]:
        return sorted(self._sources)

    def crawlable(self) -> list[SourceConfig]:
        return [s for s in self.all() if s.crawlable]

    def blocked(self) -> list[SourceConfig]:
        return [s for s in self.all() if not s.has_approved_access]

    def refuse_reason(self, name: str) -> str | None:
        """Return why a source cannot be crawled, or None if it may."""
        cfg = self._sources.get(name)
        if cfg is None:
            return f"source '{name}' is not registered"
        if not cfg.has_approved_access:
            return (
                f"permission_status={cfg.permission_status.value} - "
                "automated collection refused"
            )
        if cfg.paused:
            return f"source paused: {cfg.pause_reason}"
        return None

    def register(self, config: SourceConfig) -> None:
        self._sources[config.name] = config

    def unregister(self, name: str) -> None:
        self._sources.pop(name, None)


default_registry = SourceRegistry()