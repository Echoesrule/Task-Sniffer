"""Source registry.

Single place that records, for every known source, its audited access method
and permission status (spec §2). The ingestion engine consults this registry
and refuses to crawl sources whose permission status is REVIEW/RESTRICTED/
DISABLED.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
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
    extra_urls: list[str] | None = None,
    notes: str = "",
    active: bool = True,
) -> SourceConfig:
    return SourceConfig(
        name=name,
        url=url,
        feed_url=feed_url,
        extra_urls=extra_urls or [],
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


_BOARD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def _configured_ids(variable: str, environ: dict[str, str] | None = None) -> list[str]:
    """Read comma-separated public board/account identifiers, never credentials."""
    if environ is None:
        from backend.config import get_settings

        values = str(getattr(get_settings(), variable.lower(), "") or "")
    else:
        values = environ.get(variable, "")
    return list(dict.fromkeys(
        part for raw in values.split(",")
        if (part := raw.strip()) and _BOARD_ID.fullmatch(part)
    ))


def _explicitly_enabled(variable: str, environ: dict[str, str] | None = None) -> bool:
    """Require an explicit deployment opt-in; registration alone does not run a source."""
    if environ is None:
        from backend.config import get_settings

        return bool(getattr(get_settings(), variable.lower(), False))
    value = environ.get(variable, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _board_source_enabled(
    identifiers_variable: str,
    enabled_variable: str,
    environ: dict[str, str] | None = None,
) -> bool:
    """A configured ATS source needs both known board IDs and an explicit opt-in."""
    return bool(_configured_ids(identifiers_variable, environ)) and _explicitly_enabled(
        enabled_variable, environ
    )


# ---------------------------------------------------------------------------
# Milestone 1 audit results (see docs/source_audit.md, 2026-08-30)
# ---------------------------------------------------------------------------

SOURCE_REGISTRY: dict[str, SourceConfig] = {
    # --- Approved (implement) -------------------------------------------
    "fuzu": _audited(
        "fuzu",
        AccessMethod.HTML,
        PermissionStatus.RESTRICTED,
        url="https://www.fuzu.com/kenya/jobs",
        robots=RobotsStatus.PARTIAL,
        terms=TermsStatus.PROHIBITS,
        provenance=ProvenanceClass.JOB_BOARD,
        rate_limit=3.0,
        schedule_minutes=45,
        active=False,
        notes="Current Fuzu terms prohibit automated scraping/extraction. Keep the existing adapter registered but disabled unless Fuzu provides written authorization or an approved feed.",
    ),
    "myjobmag": _audited(
        "myjobmag",
        AccessMethod.HTML,
        PermissionStatus.REVIEW,
        url="https://www.myjobmag.co.ke/jobs",
        robots=RobotsStatus.PARTIAL,
        terms=TermsStatus.UNCLEAR,
        provenance=ProvenanceClass.JOB_BOARD,
        rate_limit=5.0,
        schedule_minutes=45,
        active=False,
        notes=(
            "Current robots.txt blocks query-string URLs, /apply-now/ and "
            "/job-application/. Terms do not clearly authorize automated "
            "extraction; keep disabled pending permission review."
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
        PermissionStatus.REVIEW,
        url="https://www.careerpointkenya.co.ke",
        robots=RobotsStatus.UNKNOWN,
        terms=TermsStatus.UNCLEAR,
        provenance=ProvenanceClass.JOB_BOARD,
        rate_limit=5.0,
        schedule_minutes=60,
        active=False,
        notes="No adapter is registered and current robots/terms could not be verified; keep disabled pending review.",
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
        url="https://job-boards.greenhouse.io/",
        country="GLOBAL",
        tier=2,
        rate_limit=1.5,
        schedule_minutes=180,
        extra_urls=_configured_ids("GREENHOUSE_BOARD_TOKENS"),
        active=_board_source_enabled("GREENHOUSE_BOARD_TOKENS", "GREENHOUSE_ENABLED"),
        notes=(
            "Official public Job Board API. Configure known employer tokens in "
            "GREENHOUSE_BOARD_TOKENS and explicitly opt in with GREENHOUSE_ENABLED=true."
        ),
    ),
    "ashby": _audited(
        "ashby",
        AccessMethod.API,
        PermissionStatus.APPROVED,
        url="https://jobs.ashbyhq.com/",
        country="GLOBAL",
        tier=2,
        rate_limit=1.5,
        schedule_minutes=180,
        extra_urls=_configured_ids("ASHBY_BOARD_NAMES"),
        active=_board_source_enabled("ASHBY_BOARD_NAMES", "ASHBY_ENABLED"),
        notes=(
            "Official public posting API. Configure known employer board names in "
            "ASHBY_BOARD_NAMES and explicitly opt in with ASHBY_ENABLED=true."
        ),
    ),
    # --- REVIEW (do not enable until re-audited) -------------------------
    "brightermonday": _audited(
        "brightermonday",
        AccessMethod.HTML,
        PermissionStatus.REVIEW,
        url="https://www.brightermonday.co.ke",
        robots=RobotsStatus.PARTIAL,
        terms=TermsStatus.UNCLEAR,
        rate_limit=5.0,
        active=False,
notes=(
            "Current robots.txt disallows /job/ detail pages and allows sitemap "
            "discovery; no permitted detail flow or terms approval established. "
            "Legacy scraper targets stale .com domain. Keep disabled pending review."
        ),
    ),
    "jobwebkenya": _audited(
        "jobwebkenya",
        AccessMethod.HTML,
        PermissionStatus.REVIEW,
        url="https://jobwebkenya.com/",
        robots=RobotsStatus.UNKNOWN,
        terms=TermsStatus.UNCLEAR,
        provenance=ProvenanceClass.JOB_BOARD,
        rate_limit=5.0,
        active=False,
        notes="Candidate source registered only; current robots/terms and permitted discovery method have not been verified, and no adapter is enabled.",
    ),
    "workable": _audited(
        "workable",
        AccessMethod.API,
        PermissionStatus.REVIEW,
        url="https://apply.workable.com/",
        country="GLOBAL",
        tier=2,
        rate_limit=2.0,
        schedule_minutes=180,
        extra_urls=_configured_ids("WORKABLE_ACCOUNT_SUBDOMAINS"),
        active=False,
        notes=(
            "Adapter uses Workable's documented unauthenticated published-jobs "
            "account endpoint. Configure explicitly selected employer subdomains "
            "with WORKABLE_ACCOUNT_SUBDOMAINS. Aggregator redistribution terms are unverified; "
            "permission remains REVIEW. SPI jobs API requires employer-issued "
            "r_jobs access and is not used."
        ),
    ),
    "remotive": _audited(
        "remotive",
        AccessMethod.API,
        PermissionStatus.RESTRICTED,
        url="https://remotive.com/",
        feed_url="https://remotive.com/remote-jobs/api",
        extra_urls=["https://remotive.com/remote-jobs/feed"],
        robots=RobotsStatus.UNKNOWN,
        terms=TermsStatus.PROHIBITS,
        provenance=ProvenanceClass.AGGREGATOR,
        country="GLOBAL",
        tier=2,
        active=False,
        notes=(
            "Not enabled: current Terms of Use prohibit automated extraction and "
            "redistribution without written permission. Public API requires source "
            "attribution/backlinks and forbids some third-party/job-board uses; "
            "Task Sniffer signup/display terms need written clearance."
        ),
    ),
    "linkedin": _audited(
        "linkedin",
        AccessMethod.MANUAL,
        PermissionStatus.RESTRICTED,
        url="https://www.linkedin.com/jobs/",
        robots=RobotsStatus.UNKNOWN,
        terms=TermsStatus.PROHIBITS,
        provenance=ProvenanceClass.JOB_BOARD,
        country="GLOBAL",
        tier=2,
        active=False,
        notes="Do not scrape. LinkedIn User Agreement prohibits scraping/copying services; developer/API access is not blanket permission for job retrieval. Requires a written approved product scope or partner feed.",
    ),
    "fiverr": _audited(
        "fiverr",
        AccessMethod.MANUAL,
        PermissionStatus.RESTRICTED,
        url="https://www.fiverr.com/",
        robots=RobotsStatus.UNKNOWN,
        terms=TermsStatus.PROHIBITS,
        provenance=ProvenanceClass.AGGREGATOR,
        country="GLOBAL",
        tier=3,
        active=False,
        notes="Freelance-gig marketplace, not a conventional job board. Terms prohibit unauthorized automation/scraping; no general public gig API identified. Requires an authorized access method and separate product treatment.",
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
        if cfg.source_status.value == "DISABLED":
            return f"source disabled: {cfg.pause_reason or 'not explicitly enabled'}"
        if cfg.paused:
            return f"source paused: {cfg.pause_reason}"
        return None

    def register(self, config: SourceConfig) -> None:
        self._sources[config.name] = config

    def unregister(self, name: str) -> None:
        self._sources.pop(name, None)


default_registry = SourceRegistry()
