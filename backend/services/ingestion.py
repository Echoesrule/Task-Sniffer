"""Ingestion engine (spec §6, §16).

Owns the job pipeline end-to-end for a single source run:

    access-policy check
      -> rate-limited fetch of listing(s)
      -> identify canonical job URL (never trust anchor order)
      -> resolve redirects + canonicalize
      -> fetch detail page (when supported) + validate against checklist
      -> normalizer
      -> dedup / provenance merge
      -> persist with url_status
      -> update source metrics & health

Failure isolation: a bad job never aborts the source run; errors are recorded
to ``ingestion_errors``. On sustained rate-limiting the source is paused.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.database import IngestionError, Job, Source
from backend.scrapers.adapter import JobSourceAdapter, ListingItem
from backend.services.normalizer import JobNormalizer
from backend.sources.models import SourceConfig, UrlStatus, utcnow
from backend.sources.rate_limit import RateLimiter, should_pause
from backend.sources.registry import default_registry
from backend.sources.urls import (
    CandidateLink,
    canonicalize_url,
    classify_url,
    identify_job_url,
    resolve_redirects,
    validate_job_page,
)

from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class SourceRunResult:
    """Outcome of a single source run (spec §16 metrics)."""

    source: str = ""
    started_at: str = ""
    finished_at: str = ""
    listings_seen: int = 0
    new_jobs: int = 0
    updated_jobs: int = 0
    duplicates: int = 0
    invalid_urls: int = 0
    review_urls: int = 0
    errors: int = 0
    paused: bool = False
    pause_reason: str = ""
    error_messages: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "listings_seen": self.listings_seen,
            "new_jobs": self.new_jobs,
            "updated_jobs": self.updated_jobs,
            "duplicates": self.duplicates,
            "invalid_urls": self.invalid_urls,
            "review_urls": self.review_urls,
            "errors": self.errors,
            "error_messages": self.error_messages[:20],
            "paused": self.paused,
            "pause_reason": self.pause_reason,
        }


class IngestionEngine:
    """Headless orchestrator of the ingestion pipeline."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: Any = None,
        *,
        adapter_factory: Callable[[SourceConfig], JobSourceAdapter] | None = None,
        normalizer: JobNormalizer | None = None,
        max_jobs_per_source: int = 100,
        dry_run: bool = False,
    ) -> None:
        self._sf: async_sessionmaker[AsyncSession] = session_factory
        self._registry = registry or default_registry
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._normalizer = normalizer or JobNormalizer()
        self.max_jobs_per_source = max_jobs_per_source
        self.dry_run = dry_run

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run_source(
        self,
        name: str,
        *,
        force: bool = False,
        limit: int | None = None,
        on_job: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> SourceRunResult:
        started = utcnow()
        limit = limit or self.max_jobs_per_source
        result = SourceRunResult(source=name, started_at=started.isoformat())

        config = self._registry.get(name)
        if config is None:
            result.errors += 1
            result.error_messages.append(f"source '{name}' not registered")
            result.finished_at = utcnow().isoformat()
            return result

        refuse = self._registry.refuse_reason(name)
        if refuse and not force:
            logger.info("[%s] refused: %s", name, refuse)
            result.error_messages.append(refuse)
            result.finished_at = utcnow().isoformat()
            return result

        if not config.crawlable and not force:
            logger.info("[%s] not crawlable", name)
            result.finished_at = utcnow().isoformat()
            return result

        limiter = RateLimiter(config)
        adapter = self._adapter_factory(config)

        async with self._sf() as session:
            source_row = await self._get_or_create_source(session, config)

            # --- collect listing(s) --------------------------------------
            try:
                listing_items = await adapter.fetch_listings(limit=limit, limiter=limiter)
            except Exception as exc:  # noqa: BLE001 - isolate source failure
                result.errors += 1
                result.error_messages.append(str(exc))
                await self._record_error(session, source_row, stage="listing", exc=exc)
                if self.dry_run is False:
                    self._mark_source_error(session, source_row, str(exc))
                await session.commit()
                return result

            if not listing_items:
                logger.info("[%s] no listings returned", name)
                result.finished_at = utcnow().isoformat()
                await session.commit()
                return result

            result.listings_seen = len(listing_items)

            # --- per-listing URL pipeline + persist ----------------------
            jobs_seen: int = 0
            for item in listing_items:
                if jobs_seen >= limit:
                    break
                try:
                    outcome = await self._process_listing(
                        session=session,
                        config=config,
                        adapter=adapter,
                        item=item,
                        source_row=source_row,
                    )
                    jobs_seen += 1
                    result.new_jobs += outcome.new
                    result.updated_jobs += outcome.updated
                    result.duplicates += outcome.duplicates
                    result.invalid_urls += outcome.invalid
                    result.review_urls += outcome.review
                    result.errors += outcome.errors
                    result.error_messages.extend(outcome.errors_details)
                    if on_job is not None:
                        await on_job(name, outcome.job)
                except Exception as exc:  # noqa: BLE001 - per-job isolation
                    result.errors += 1
                    result.error_messages.append(f"{item.title}: {exc}")
                    await self._record_error(session, source_row, stage="process", exc=exc, job_url=item.raw_url or item.source_url)

                if self.dry_run:
                    await session.rollback()
                    continue

            # --- source health / metrics ---------------------------------
            if not self.dry_run:
                await self._update_source_stats(
                    session, source_row, config, limiter,
                    total_seen=jobs_seen,
                    new=result.new_jobs,
                    dup=result.duplicates,
                    invalid=result.invalid_urls,
                    review=result.review_urls,
                )
                if result.errors and result.new_jobs == 0:
                    result.paused = True
                    result.pause_reason = "SOURCE_FAILED"
                    await self._pause_source(session, source_row, "SOURCE_FAILED")

            await adapter.close()
            result.finished_at = utcnow().isoformat()
            await session.commit()
            return result

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    async def _process_listing(
        self,
        *,
        session: AsyncSession,
        config: SourceConfig,
        adapter: JobSourceAdapter,
        item: ListingItem,
        source_row: Source,
    ) -> "_ListingOutcome":
        outcome = _ListingOutcome()

        candidate = await self._resolve_candidate_url(adapter, item, config)
        if candidate is None or not candidate["url"]:
            outcome.review += 1  # no detail url identifiable -> needs review
            outcome.errors += 1
            outcome.errors_details.append(f"{item.title}: no job-detail URL identified")
            return outcome

        detail, validation = await self._fetch_and_validate(adapter, item, candidate["url"])

        # --- build raw job dict -----------------------------------------
        raw = item.as_raw()
        raw.update(detail or {})
        raw["url"] = candidate["url"]
        raw["source"] = config.name
        if validation is not None and not validation.ok:
            raw["url_status"] = validation.status.value

        normalized = self._normalizer.normalize(raw, config.name)
        # carry URL-pipeline provenance through the normalizer's fixed schema
        normalized["url_status"] = raw.get("url_status") or UrlStatus.VALID.value
        normalized["source_url"] = candidate["url"]
        normalized["application_url"] = raw.get("application_url") or ""
        normalized["_final_url"] = raw.get("_final_url")
        normalized["_redirect_chain"] = raw.get("_redirect_chain") or []
        normalized["_http_status"] = raw.get("_http_status")
        normalized["source"] = config.name

        # --- persist / dedup ---------------------------------------------
        if self.dry_run:
            outcome.new += 1
            outcome.job = normalized
            return outcome

        persisted = await self._persist_job(session, source_row, normalized, candidate, item)
        outcome.job = normalized
        outcome.new += persisted.new
        outcome.updated += persisted.updated
        outcome.duplicates += persisted.dup
        if validation is not None and not validation.ok:
            if validation.status == UrlStatus.INVALID:
                outcome.invalid += 1
            else:
                outcome.review += 1
        elif validation is not None:
            outcome.review += 1 if not validation.checks.get("has_job_content") else 0
        return outcome

    async def _resolve_candidate_url(self, adapter: JobSourceAdapter, item: ListingItem, config: SourceConfig) -> dict[str, Any] | None:
        """Canonicalize + classify + identify a job-detail candidate URL.

        Never trusts the first anchor or first URL order (spec §9).
        """
        candidates: list[str] = []
        for u in item.url_candidates or []:
            c = canonicalize_url(u)
            if c:
                candidates.append(c)
        if not candidates and item.source_url:
            c = canonicalize_url(item.source_url)
            if c:
                candidates.append(c)

        links = [
            CandidateLink(url=u, text="", kind=classify_url(u, source_patterns=adapter.job_url_patterns))
            for u in dict.fromkeys(candidates)
        ]
        chosen = identify_job_url(
            links,
            title_hint=item.title,
            source_patterns=adapter.job_url_patterns,
        )
        if chosen is None:
            return None
        return {"url": chosen.url, "kind": chosen.kind.value}

    async def _fetch_and_validate(
        self, adapter: JobSourceAdapter, item: ListingItem, url: str
    ) -> tuple[dict[str, Any], Any]:
        """Fetch the detail page once, resolve redirects, run the §8 checklist."""
        allowed_domains = {d for d in adapter.allowed_domains if d}
        if not allowed_domains:
            host = urlparse(url).netloc.split(":")[0]
            if host:
                allowed_domains = {host}

        client = adapter._client
        try:
            response = await client.get(url)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] detail fetch failed %s: %s", adapter.name, url, exc)
            validation = validate_job_page(
                url=url, status_code=0,
                allowed_domains=allowed_domains or None,
            )
            validation.reason = f"fetch error: {exc}"
            return {}, validation

        final_url = str(response.url) if response.url else url
        chain = [u for u in ([url] + [h.headers.get("location", "") for h in response.history]) if u]

        html = response.text if response.status_code == 200 else ""
        page_title = _page_title(html)
        body_text = _body_text(html)

        validation = adapter.validate_page(
            url=final_url,
            status_code=response.status_code,
            page_title=page_title,
            body_text=body_text,
            expected_title=item.title,
            expected_company=item.company,
        )

        detail: dict[str, Any] = {}
        if response.status_code == 200 and html:
            try:
                parsed = await adapter.parse_detail(html, final_url)
                detail = parsed or {}
                detail["_page_fetched"] = True
            except Exception as exc:  # noqa: BLE001 - detail parse is enrich-only
                logger.debug("[%s] detail parse failed %s: %s", adapter.name, final_url, exc)
                detail = {}

        detail["_final_url"] = final_url
        detail["_redirect_chain"] = chain
        detail["_http_status"] = response.status_code
        return detail, validation

    async def _persist_job(
        self,
        session: AsyncSession,
        source_row: Source,
        normalized: dict[str, Any],
        candidate: dict[str, Any],
        item: ListingItem,
    ) -> "_PersistOutcome":
        """Insert or update the job, dedup against existing records."""
        out = _PersistOutcome()

        fingerprint = normalized.get("fingerprint", "")
        source_job_id = normalized.get("source_job_id", "")
        source_url = normalized.get("source_url", "") or candidate.get("url", "")

        # 1) exact re-scrape of same source+id -> update URL fields
        if source_job_id:
            existing = (
                await session.execute(
                    select(Job).where(
                        Job.source_id == source_row.id,
                        Job.source_job_id == source_job_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.source_url = source_url
                existing.canonical_url = source_url
                if normalized.get("_final_url"):
                    existing.final_url = normalized["_final_url"]
                if normalized.get("application_url"):
                    existing.application_url = normalized["application_url"]
                existing.scraped_at = datetime.now(timezone.utc)
                out.updated += 1
                return out

        # 2) cross-source fingerprint dedup
        if fingerprint:
            dup = (
                await session.execute(
                    select(Job).where(Job.fingerprint == fingerprint).limit(1)
                )
            ).scalars().first()
            if dup is not None:
                await self._merge_provenance(session, dup, source_row.name, source_url)
                if normalized.get("_final_url"):
                    dup.final_url = normalized["_final_url"]
                out.dup += 1
                return out

        # 3) new job
        job = Job(
            source_id=source_row.id,
            source_job_id=source_job_id or fingerprint,
            title=normalized.get("title", item.title),
            company=normalized.get("company", item.company),
            description=normalized.get("description", ""),
            skills_list=normalized.get("skills", []),
            location=normalized.get("location", item.location),
            country=source_row.country_focus,
            remote=bool(normalized.get("remote", item.remote)),
            employment_type=normalized.get("employment_type"),
            experience_level=normalized.get("experience_level"),
            salary_min=normalized.get("salary_min"),
            salary_max=normalized.get("salary_max"),
            salary_currency=normalized.get("salary_currency"),
            source_url=source_url,
            canonical_url=source_url,
            final_url=normalized.get("_final_url") or source_url,
            redirect_chain_list=normalized.get("_redirect_chain") or [],
            application_url=normalized.get("application_url") or source_url,
            url_status=normalized.get("url_status", UrlStatus.VALID.value),
            url_validated_at=utcnow(),
            provenances_list=[],
            fingerprint=fingerprint,
            scraped_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.flush()
        await self._merge_provenance(session, job, source_row.name, source_url)
        out.new += 1
        return out

    async def _merge_provenance(self, session: AsyncSession, job: Job, source_name: str, url: str) -> None:
        sources = job.provenances_list
        if not any(s.get("source") == source_name for s in sources):
            sources.append({
                "source": source_name,
                "source_url": url,
                "seen_at": utcnow().isoformat(),
            })
            job.provenances_list = sources

    # ------------------------------------------------------------------
    # Source bookkeeping
    # ------------------------------------------------------------------

    async def _get_or_create_source(self, session: AsyncSession, config: SourceConfig) -> Source:
        row = (await session.execute(select(Source).where(Source.name == config.name))).scalar_one_or_none()
        if row is None:
            row = Source(
                name=config.name,
                url=config.url or f"https://{config.name}",
                tier=config.tier,
                enabled=True,
                country_focus=config.country_focus,
                access_method=config.access_method.value,
                permission_status=config.permission_status.value,
                robots_status=config.robots_status.value,
                terms_status=config.terms_status.value,
                provenance=config.provenance.value,
                rate_limit=config.rate_limit,
                requires_auth=config.requires_auth,
                last_audited=config.last_audited,
            )
            session.add(row)
            await session.flush()
        else:
            row.access_method = config.access_method.value
            row.permission_status = config.permission_status.value
            row.robots_status = config.robots_status.value
            row.terms_status = config.terms_status.value
            row.provenance = config.provenance.value
            row.rate_limit = config.rate_limit
            row.requires_auth = config.requires_auth
            row.last_audited = config.last_audited
        return row

    async def _update_source_stats(
        self,
        session: AsyncSession,
        source_row: Source,
        config: SourceConfig,
        limiter: RateLimiter,
        *,
        total_seen: int,
        new: int,
        dup: int,
        invalid: int,
        review: int,
    ) -> None:
        source_row.jobs_found += total_seen
        source_row.unique_jobs += new
        processed = new + dup
        if processed:
            source_row.duplicate_rate = round((dup / processed) * 100, 2)
        source_row.invalid_url_rate = round((invalid / total_seen) * 100, 2) if total_seen else 0.0
        source_row.review_url_rate = round((review / total_seen) * 100, 2) if total_seen else 0.0
        source_row.last_scraped_at = datetime.now(timezone.utc)
        source_row.last_successful_fetch = datetime.now(timezone.utc)
        source_row.last_error = None
        if should_pause(limiter):
            source_row.source_status = "PAUSED"
            source_row.pause_reason = "RATE_LIMITED"
            source_row.retry_at = utcnow()
            source_row.retry_count += 1

    async def _pause_source(self, session: AsyncSession, source_row: Source, reason: str) -> None:
        source_row.source_status = "PAUSED"
        source_row.pause_reason = reason
        source_row.retry_at = utcnow()
        source_row.retry_count += 1

    def _mark_source_error(self, session: AsyncSession, source_row: Source, msg: str) -> None:
        source_row.last_error = (msg or "")[:2000]
        source_row.last_scraped_at = datetime.now(timezone.utc)

    async def _record_error(self, session: AsyncSession, source_row: Source, *, stage: str, exc: Exception, job_url: str = "") -> None:
        session.add(
            IngestionError(
                source_id=source_row.id,
                job_url=job_url or None,
                stage=stage,
                error_class=exc.__class__.__name__,
                error_message=str(exc)[:4000],
            )
        )


# ---------------------------------------------------------------------------
# outcome containers
# ---------------------------------------------------------------------------


@dataclass
class _ListingOutcome:
    new: int = 0
    updated: int = 0
    duplicates: int = 0
    invalid: int = 0
    review: int = 0
    errors: int = 0
    errors_details: list[str] = field(default_factory=list)
    job: dict[str, Any] | None = None


@dataclass
class _PersistOutcome:
    new: int = 0
    updated: int = 0
    dup: int = 0


def _page_title(html: str) -> str:
    import re
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def _body_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        return " ".join(soup.get_text(" ", strip=True).split())[:6000]
    except Exception:  # noqa: BLE001
        return ""


def _default_adapter_factory(config: SourceConfig) -> JobSourceAdapter:
    from backend.scrapers.factory import build_adapter

    return build_adapter(config)


def build_engine(session_factory: async_sessionmaker[AsyncSession], **kwargs: Any) -> IngestionEngine:
    return IngestionEngine(session_factory, **kwargs)