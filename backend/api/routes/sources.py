"""Source management & audit routes.

Exposes the registry access-policy (spec §2), source health metrics, and
controls to pause/resume a source and inspect URL quality.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from backend.api.deps import get_db
from backend.models.database import IngestionError, Job, Source
from backend.sources.registry import default_registry

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SourceInfo(BaseModel):
    name: str
    url: str
    tier: int
    country_focus: str
    enabled: bool
    access_method: str
    permission_status: str
    robots_status: str
    provenance: str
    requires_auth: bool
    rate_limit: float
    crawlable: bool = False
    blocked_reason: str | None = None
    source_status: str = "UNREGISTERED"
    pause_reason: str | None = None
    last_audited: str | None = None
    last_scraped_at: str | None = None
    last_error: str | None = None
    jobs_found: int = 0
    unique_jobs: int = 0
    duplicate_rate: float = 0.0
    invalid_url_rate: float = 0.0
    review_url_rate: float = 0.0
    average_match_score: float = 0.0
    risk_rate: float = 0.0
    applications: int = 0


class SourceListResponse(BaseModel):
    sources: list[SourceInfo] = Field(default_factory=list)
    total: int = 0


class SourceRunRequest(BaseModel):
    force: bool = Field(False, description="Bypass the access-policy block")
    limit: int | None = Field(None, ge=1, le=500, description="Max jobs to fetch")


class JobUrlStats(BaseModel):
    total_jobs: int = 0
    valid_urls: int = 0
    invalid_urls: int = 0
    review_urls: int = 0


class PauseResponse(BaseModel):
    name: str
    source_status: str
    pause_reason: str | None = None
    retry_at: str | None = None


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


@router.get("", response_model=SourceListResponse)
async def list_sources(db: AsyncSession = Depends(get_db)) -> SourceListResponse:
    rows = (await db.execute(select(Source))).scalars().all()
    out: list[SourceInfo] = []
    registered = {s.name for s in default_registry.all()}

    for row in rows:
        cfg = default_registry.get(row.name)
        out.append(
            SourceInfo(
                name=row.name,
                url=row.url or "",
                tier=row.tier or 3,
                country_focus=row.country_focus or "GLOBAL",
                enabled=bool(row.enabled),
                access_method=(row.access_method or "html"),
                permission_status=(row.permission_status or "REVIEW"),
                robots_status=(row.robots_status or "UNKNOWN"),
                provenance=(row.provenance or "unknown"),
                requires_auth=bool(row.requires_auth),
                rate_limit=row.rate_limit or 2.0,
                crawlable=cfg.crawlable if cfg else bool(row.enabled),
                blocked_reason=default_registry.refuse_reason(row.name) if cfg else None,
                source_status=row.source_status or "ACTIVE",
                pause_reason=row.pause_reason,
                last_audited=_iso(row.last_audited),
                last_scraped_at=_iso(row.last_scraped_at),
                last_error=row.last_error,
                jobs_found=row.jobs_found or 0,
                unique_jobs=row.unique_jobs or 0,
                duplicate_rate=row.duplicate_rate or 0.0,
                invalid_url_rate=row.invalid_url_rate or 0.0,
                review_url_rate=row.review_url_rate or 0.0,
                average_match_score=row.average_match_score or 0.0,
                risk_rate=row.risk_rate or 0.0,
                applications=row.applications or 0,
            )
        )

    # sources present in the registry but not yet materialized in the DB
    known = {s.name for s in rows}
    for name in sorted(registered - known):
        cfg = default_registry.get(name)
        out.append(
            SourceInfo(
                name=name,
                url=cfg.url if cfg else "",
                tier=cfg.tier if cfg else 3,
                country_focus=cfg.country_focus if cfg else "GLOBAL",
                enabled=cfg.source_status.value != "DISABLED" if cfg else False,
                access_method=cfg.access_method.value if cfg else "html",
                permission_status=cfg.permission_status.value if cfg else "REVIEW",
                robots_status=cfg.robots_status.value if cfg else "UNKNOWN",
                provenance=cfg.provenance.value if cfg else "unknown",
                requires_auth=cfg.requires_auth if cfg else False,
                rate_limit=cfg.rate_limit if cfg else 2.0,
                crawlable=cfg.crawlable if cfg else False,
                blocked_reason=default_registry.refuse_reason(name),
                source_status=cfg.source_status.value if cfg else "UNREGISTERED",
                last_audited=_iso(cfg.last_audited) if cfg else None,
            )
        )

    return SourceListResponse(sources=out, total=len(out))


@router.post("/{name}/ingest", response_model=dict[str, Any])
async def ingest_source(
    name: str,
    request: SourceRunRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Trigger a single-source run against the ingestion engine (spec §6)."""
    from backend.services.ingestion import IngestionEngine

    engine = IngestionEngine(
        async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
    )
    cfg = default_registry.get(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Source '{name}' not registered")

    result = await engine.run_source(name, force=request.force, limit=request.limit)
    return result.as_dict()


@router.post("/{name}/pause", response_model=PauseResponse)
async def pause_source(
    name: str,
    db: AsyncSession = Depends(get_db),
    reason: str = Query("MANUAL", description="Reason for pausing"),
) -> PauseResponse:
    row = (await db.execute(select(Source).where(Source.name == name))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Source '{name}' not found")
    row.source_status = "PAUSED"
    row.pause_reason = reason
    row.retry_at = None
    await db.commit()
    return PauseResponse(name=name, source_status="PAUSED", pause_reason=reason)


@router.post("/{name}/resume", response_model=PauseResponse)
async def resume_source(
    name: str,
    db: AsyncSession = Depends(get_db),
) -> PauseResponse:
    row = (await db.execute(select(Source).where(Source.name == name))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Source '{name}' not found")
    cfg = default_registry.get(name)
    if cfg is not None and cfg.permission_status.value in {"REVIEW", "RESTRICTED", "DISABLED"}:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Source '{name}' has permission_status={cfg.permission_status.value}; "
                "automated collection stays refused"
            ),
        )
    row.source_status = "ACTIVE"
    row.pause_reason = None
    row.retry_at = None
    row.retry_count = 0
    await db.commit()
    return PauseResponse(name=name, source_status="ACTIVE")


@router.get("/{name}/urls", response_model=JobUrlStats)
async def source_url_stats(
    name: str,
    db: AsyncSession = Depends(get_db),
) -> JobUrlStats:
    row = (await db.execute(select(Source).where(Source.name == name))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Source '{name}' not found")

    base = select(sa_func.count(Job.id)).join(Source).where(Source.id == row.id)
    total = (await db.execute(base)).scalar() or 0
    valid = (
        await db.execute(base.where(Job.url_status == "VALID"))
    ).scalar() or 0
    invalid = (
        await db.execute(base.where(Job.url_status == "INVALID"))
    ).scalar() or 0
    review = (
        await db.execute(base.where(Job.url_status == "NEEDS_REVIEW"))
    ).scalar() or 0
    return JobUrlStats(
        total_jobs=total, valid_urls=valid, invalid_urls=invalid, review_urls=review,
    )


@router.get("/{name}/errors", response_model=list[dict[str, Any]])
async def source_errors(
    name: str,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
) -> list[dict[str, Any]]:
    row = (await db.execute(select(Source).where(Source.name == name))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Source '{name}' not found")
    errors = (
        await db.execute(
            select(IngestionError)
            .where(IngestionError.source_id == row.id)
            .order_by(IngestionError.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "stage": e.stage,
            "job_url": e.job_url,
            "error_class": e.error_class,
            "error_message": e.error_message,
            "attempt": e.attempt,
            "created_at": _iso(e.created_at),
        }
        for e in errors
    ]