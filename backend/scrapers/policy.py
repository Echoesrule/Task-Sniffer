"""Explicit, evidence-based URL/domain policies (Phase 4, spec §8).

New adapters (``backend.scrapers.adapters``) declare ``job_url_patterns`` and
``allowed_domains`` directly on the class. The legacy scrapers wrapped by
:class:`backend.scrapers.factory._LegacyAdapter` do not, so their policy lives
here, separate from parsing logic.

Policy rules:

* An empty ``allowed_domains`` is a hard fail-closed signal. It must never be
  read as "any domain is acceptable" - callers withhold normal persistence.
* Wildcards are not used; only exact hosts or explicit suffixes. A suffix
  entry ``greenhouse.io`` matches ``greenhouse.io`` and ``*.greenhouse.io``.
* External ATS destinations are only permitted when explicitly configured.
* Every registered source is reported, so a missing policy is visible rather
  than silently yielding no results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourcePolicy:
    """Declarative trust policy for a single source."""

    #: regexes matched against the *path* of a candidate detail URL
    job_url_patterns: tuple[str, ...] = ()
    #: hostname suffixes an individual job page (or its final redirect) may use
    allowed_domains: tuple[str, ...] = ()
    #: query params that establish job identity for this source
    identity_query_params: tuple[str, ...] = ()
    #: how the detail URL is derived (documented, for reviewability)
    detail_url_rule: str = ""
    notes: str = ""

    @property
    def configured(self) -> bool:
        """A source is only usable when it has at least one trusted domain."""
        return bool(self.allowed_domains)


#: Policies for the legacy scrapers, derived from each provider's documented
#: API/URL format and the historical data audit (see audit.md, Phase 4).
LEGACY_SOURCE_POLICIES: dict[str, SourcePolicy] = {
    "greenhouse": SourcePolicy(
        job_url_patterns=(r"/[^/]+/jobs/\d+/?$", r"^/jobs/\d+/?$"),
        allowed_domains=("greenhouse.io",),
        identity_query_params=("gh_jid",),
        detail_url_rule="https://job-boards.greenhouse.io/<board>/jobs/<id>",
        notes=(
            "Greenhouse Job Board API. Individual postings are /<board>/jobs/<id>; "
            "absolute_url may point at a company search/careers page and is not trusted."
        ),
    ),
    "ashby": SourcePolicy(
        job_url_patterns=(r"^/[^/]+/[0-9a-fA-F-]{8,}/?$",),
        allowed_domains=("ashbyhq.com",),
        identity_query_params=(),
        detail_url_rule="https://jobs.ashbyhq.com/<board>/<id>",
        notes="Ashby posting API. Individual postings are /<board>/<posting-id>.",
    ),
    "jobicy": SourcePolicy(
        job_url_patterns=(r"^/jobs/\d",),
        allowed_domains=("jobicy.com",),
        detail_url_rule="https://jobicy.com/jobs/<id>-<slug>",
        notes="Jobicy remote-jobs API. url field is an individual /jobs/<id>-<slug> page.",
    ),
    "myjobskenya": SourcePolicy(
        job_url_patterns=(r"/job/[^/?#]+/?$", r"/jobs?/\d+"),
        allowed_domains=("myjobskenya.com",),
        detail_url_rule="HTML listing -> /job/<slug>",
        notes="MyJobsKenya HTML listings; detail pages live under /job/<slug>.",
    ),
}


def get_policy(name: str) -> SourcePolicy | None:
    """Return the declared legacy policy for ``name`` (case-insensitive)."""
    return LEGACY_SOURCE_POLICIES.get((name or "").lower())


def source_policy_report(registry: Any = None) -> list[dict[str, Any]]:
    """Report the URL/domain policy of every registered source.

    Does not construct adapters (no clients are created); it reads class
    attributes and the legacy policy table instead. Each entry records whether
    the source is configured so unconfigured sources can be surfaced.
    """
    from backend.scrapers.adapters import ADAPTER_CLASSES
    from backend.sources.registry import default_registry

    reg = registry or default_registry
    report: list[dict[str, Any]] = []

    for config in reg.all():
        name = config.name
        if name in ADAPTER_CLASSES:
            cls = ADAPTER_CLASSES[name]
            domains = tuple(getattr(cls, "allowed_domains", ()) or ())
            patterns = tuple(getattr(cls, "job_url_patterns", ()) or ())
            report.append({
                "name": name,
                "kind": "adapter",
                "configured": bool(domains),
                "allowed_domains": list(domains),
                "job_url_patterns": list(patterns),
                "detail": "adapter declares policy directly",
            })
        elif name in LEGACY_SOURCE_POLICIES:
            policy = LEGACY_SOURCE_POLICIES[name]
            report.append({
                "name": name,
                "kind": "legacy",
                "configured": policy.configured,
                "allowed_domains": list(policy.allowed_domains),
                "job_url_patterns": list(policy.job_url_patterns),
                "detail": policy.detail_url_rule,
            })
        else:
            report.append({
                "name": name,
                "kind": "unconfigured",
                "configured": False,
                "allowed_domains": [],
                "job_url_patterns": [],
                "detail": "no adapter class or legacy policy registered",
            })
    return report


def unconfigured_sources(registry: Any = None) -> list[str]:
    """Names of registered sources lacking a usable URL/domain policy."""
    return [row["name"] for row in source_policy_report(registry) if not row["configured"]]
