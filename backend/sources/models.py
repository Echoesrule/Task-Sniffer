"""Source access-policy models.

Encodes the Task Sniffer source-access policy (spec §1): a source may only be
crawled when its audited permission status permits automated collection, using
the audited access method.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AccessMethod(str, Enum):
    """How a source may be accessed."""

    API = "api"
    RSS = "rss"
    ATOM = "atom"
    HTML = "html"
    PARTNER_FEED = "partner_feed"
    MANUAL = "manual"


class PermissionStatus(str, Enum):
    """Crawl permission verdict from the source audit."""

    APPROVED = "APPROVED"
    API = "API"
    REVIEW = "REVIEW"
    RESTRICTED = "RESTRICTED"
    DISABLED = "DISABLED"


#: statuses for which the crawler must refuse automatic collection
BLOCKED_PERMISSIONS: frozenset[str] = frozenset(
    {PermissionStatus.REVIEW, PermissionStatus.RESTRICTED, PermissionStatus.DISABLED}
)


class RobotsStatus(str, Enum):
    """robots.txt verdict."""

    ALLOWED = "ALLOWED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class TermsStatus(str, Enum):
    """Terms of service verdict."""

    REVIEWED = "REVIEWED"
    UNCLEAR = "UNCLEAR"
    PROHIBITS = "PROHIBITS"


class ProvenanceClass(str, Enum):
    """Provenance trust class for the risk engine (spec §14)."""

    OFFICIAL = "official"  # government / official company career page
    JOB_BOARD = "job_board"  # established job board
    AGGREGATOR = "aggregator"
    UNKNOWN = "unknown"


#: relative provenance signal strengths used by the risk engine
PROVENANCE_STRENGTH: dict[ProvenanceClass, float] = {
    ProvenanceClass.OFFICIAL: 1.0,
    ProvenanceClass.JOB_BOARD: 0.7,
    ProvenanceClass.AGGREGATOR: 0.4,
    ProvenanceClass.UNKNOWN: 0.1,
}


class SourceStatus(str, Enum):
    """Runtime state of a source."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class UrlStatus(str, Enum):
    """Validation state of a stored job URL (spec §8)."""

    VALID = "VALID"
    INVALID = "INVALID"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class UrlType(str, Enum):
    """Classification of a candidate URL extracted from a listing."""

    JOB_DETAIL = "job_detail"
    COMPANY = "company"
    CATEGORY = "category"
    SEARCH = "search"
    TRACKING = "tracking"
    NAV = "nav"
    UNKNOWN = "unknown"


class SourceConfig(BaseModel):
    """Audited configuration for a single job source."""

    name: str
    url: str = ""
    #: for RSS/API sources, the direct feed/endpoint URL (validated in audit)
    feed_url: str = ""
    #: extra fetch pages (pagination roots, sitemap entries) validated in audit
    extra_urls: list[str] = Field(default_factory=list)
    access_method: AccessMethod = AccessMethod.HTML
    permission_status: PermissionStatus = PermissionStatus.REVIEW
    robots_status: RobotsStatus = RobotsStatus.UNKNOWN
    terms_status: TermsStatus = TermsStatus.UNCLEAR
    provenance: ProvenanceClass = ProvenanceClass.UNKNOWN
    country_focus: str = "GLOBAL"
    tier: int = 3

    # politeness
    rate_limit: float = 2.0  # min seconds between requests
    request_timeout: float = 30.0
    concurrency_limit: int = 1
    retry_limit: int = 3
    backoff_base: float = 2.0
    max_pages: int | None = None
    requires_auth: bool = False  # auth needed to APPLY (not to read listings)

    # scheduling (spec §18)
    schedule_minutes: int = 60

    # audit trail
    last_audited: datetime | None = None

    # runtime state
    source_status: SourceStatus = SourceStatus.ACTIVE
    pause_reason: str | None = None
    retry_at: datetime | None = None

    model_config = {"frozen": False}

    # -- access policy ------------------------------------------------------

    @property
    def has_approved_access(self) -> bool:
        """True when the audited permission permits automated collection."""
        return self.permission_status not in BLOCKED_PERMISSIONS

    @property
    def permission_blocked(self) -> bool:
        """True when the crawler must refuse this source (spec §2)."""
        return self.permission_status in BLOCKED_PERMISSIONS

    @property
    def paused(self) -> bool:
        return self.source_status == SourceStatus.PAUSED

    @property
    def crawlable(self) -> bool:
        """Whether the crawler may attempt automated collection right now."""
        if not self.has_approved_access or not self.access_method:
            return False
        if self.permission_blocked:
            return False
        if self.paused:
            if self.retry_at and self.retry_at <= datetime.now(timezone.utc):
                return True
            return False
        return True


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_config(data: dict[str, Any] | SourceConfig) -> SourceConfig:
    """Coerce a dict (e.g. from DB or YAML) into a SourceConfig safely."""
    if isinstance(data, SourceConfig):
        return data
    allowed = {
        "name", "url", "feed_url", "extra_urls", "access_method", "permission_status",
        "robots_status", "terms_status", "provenance", "country_focus", "tier",
        "rate_limit", "request_timeout", "concurrency_limit", "retry_limit",
        "backoff_base", "max_pages", "requires_auth", "schedule_minutes",
        "last_audited", "source_status", "pause_reason", "retry_at",
    }
    payload = {k: v for k, v in (data or {}).items() if k in allowed}
    return SourceConfig.model_validate(payload)