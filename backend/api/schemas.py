"""Pydantic schemas for API request and response models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    """Risk classification levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Recommendation(str, Enum):
    """Risk-based recommendations."""

    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class ApplicationStatus(str, Enum):
    """Application lifecycle statuses."""

    SHORTLISTED = "shortlisted"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


# ---------------------------------------------------------------------------
# Risk & Match schemas
# ---------------------------------------------------------------------------


class RiskFlag(BaseModel):
    """Individual risk flag from analysis."""

    check: str = Field(..., description="Name of the risk check that flagged this")
    severity: int = Field(..., ge=0, le=3, description="Severity level 0-3")
    reason: str = Field(..., description="Human-readable reason for the flag")


class RiskAnalysis(BaseModel):
    """Complete risk analysis result for a job."""

    risk_score: int = Field(..., ge=0, le=100, description="Risk score 0-100")
    risk_level: RiskLevel = Field(..., description="Classified risk level")
    risk_flags: list[RiskFlag] = Field(default_factory=list, description="Individual risk flags")
    recommendation: Recommendation = Field(..., description="Action recommendation")


class MatchBreakdown(BaseModel):
    """Score breakdown by component."""

    location: float = Field(0.0, description="Location match score 0-1")
    salary: float = Field(0.0, description="Salary match score 0-1")
    experience: float = Field(0.0, description="Experience match score 0-1")
    skills: float = Field(0.0, description="Skills match score 0-1")
    remote_fit: float = Field(0.0, description="Remote work compatibility score 0-1")


class MatchResult(BaseModel):
    """Full match analysis result."""

    total_score: float = Field(..., ge=0.0, le=1.0, description="Overall match score 0-1")
    breakdown: MatchBreakdown = Field(default_factory=MatchBreakdown, description="Score breakdown by component")
    filter_passed: bool = Field(True, description="Whether basic filters passed")
    explanation: str = Field("", description="Human-readable match explanation")
    exact_skills: list[str] = Field(default_factory=list, description="Exact skill matches")
    missing_skills: list[str] = Field(default_factory=list, description="Required skills not found")


# ---------------------------------------------------------------------------
# Job schemas
# ---------------------------------------------------------------------------


class JobResponse(BaseModel):
    """Single job detail response."""

    id: str = Field(..., description="Unique job identifier")
    title: str = Field(..., description="Job title")
    company: str = Field("", description="Company name")
    location: str = Field("", description="Job location")
    country: str = Field("", description="Country")
    remote: bool = Field(False, description="Whether the job is remote")
    salary: str = Field("", description="Salary range string")
    description: str = Field("", description="Full job description")
    url: str = Field("", description="Application/Source URL")
    source: str = Field("", description="Job source platform")
    source_url: str = Field("", description="Original job-detail URL on the source")
    canonical_url: str = Field("", description="Canonicalized job-detail URL")
    url_status: str = Field("", description="URL validation status (VALID/INVALID/NEEDS_REVIEW)")
    skills: list[str] = Field(default_factory=list, description="Required skills")
    skills_required: list[str] = Field(default_factory=list, description="Skills classified as required")
    skills_preferred: list[str] = Field(default_factory=list, description="Skills classified as preferred/nice-to-have")
    skills_detail: list[dict[str, Any]] = Field(default_factory=list, description="Per-skill provenance and classification")
    experience: str = Field("", description="Experience requirement")
    posted_at: datetime | None = Field(None, description="When the job was posted")
    fetched_at: datetime | None = Field(None, description="When the job was fetched")
    match_score: float | None = Field(None, ge=0.0, le=1.0, description="Candidate-specific match score 0-1; null until scored")
    match_breakdown: dict[str, float] = Field(default_factory=dict, description="Match score breakdown by component")
    classification: str | None = Field(None, description="Match classification (EXCELLENT/STRONG/POSSIBLE/WEAK/IGNORE)")
    risk_score: float = Field(0.0, ge=0.0, le=100.0, description="Risk score 0-100")
    risk_level: str | None = Field(None, description="Classified risk level (LOW/MEDIUM/HIGH)")
    status: str = Field("discovered", description="Job lifecycle status")
    risk_analysis: RiskAnalysis | None = Field(None, description="Risk analysis result")
    match_result: MatchResult | None = Field(None, description="Match analysis result")


class JobListResponse(BaseModel):
    """Paginated list of jobs."""

    jobs: list[JobResponse] = Field(default_factory=list, description="List of jobs")
    total: int = Field(0, description="Total number of matching jobs")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(20, description="Results per page")
    filters_applied: dict[str, Any] = Field(default_factory=dict, description="Active filters")


class JobSearchRequest(BaseModel):
    """Request body for job search."""

    query: str = Field(..., min_length=1, description="Search query text")
    source: str | None = Field(None, description="Filter by source")
    country: str | None = Field(None, description="Filter by country")
    remote: bool | None = Field(None, description="Filter remote jobs")
    salary_min: float | None = Field(None, description="Minimum salary")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Results per page")


class JobStatsResponse(BaseModel):
    """Aggregated job statistics."""

    total_jobs: int = Field(0, description="Total number of jobs in system")
    by_source: dict[str, int] = Field(default_factory=dict, description="Job count by source")
    by_country: dict[str, int] = Field(default_factory=dict, description="Job count by country")
    by_remote: dict[str, int] = Field(default_factory=dict, description="Remote vs on-site counts")
    avg_risk_score: float = Field(0.0, description="Average risk score across jobs")
    avg_match_score: float | None = Field(None, description="Average match score for the authenticated candidate")
    strong_matches: int = Field(0, description="Jobs with match score at least 0.75")
    latest_created_at: datetime | None = Field(None, description="Most recent job creation timestamp")


# ---------------------------------------------------------------------------
# Candidate schemas
# ---------------------------------------------------------------------------


class CandidateProfile(BaseModel):
    """Candidate profile data."""

    id: str | None = Field(None, description="Profile identifier")
    name: str = Field("", description="Full name")
    email: str = Field("", description="Email address")
    location: str = Field("", description="Current location")
    preferred_locations: list[str] = Field(default_factory=list, description="Preferred work locations")
    preferred_roles: list[str] = Field(default_factory=list, description="Preferred job titles/roles")
    skills: list[str] = Field(default_factory=list, description="Technical and soft skills")
    experience_level: str = Field("", description="Experience level (junior/mid/senior)")
    experience_years: int | None = Field(None, ge=0, description="Years of experience")
    salary_min: float | None = Field(None, ge=0, description="Minimum salary expectation")
    salary_max: float | None = Field(None, ge=0, description="Maximum salary expectation")
    remote_ok: bool = Field(False, description="Open to remote work")
    bio: str = Field("", description="Brief professional summary")
    updated_at: datetime | None = Field(None, description="Last profile update time")


class CandidateCreate(BaseModel):
    """Request body for creating a candidate profile."""

    name: str = Field(..., min_length=1, description="Full name")
    email: str = Field(..., description="Email address")
    location: str = Field("", description="Current location")
    skills: list[str] = Field(default_factory=list, description="Skills")
    experience_level: str = Field("", description="Experience level")
    remote_ok: bool = Field(False, description="Open to remote work")


class CVUploadResponse(BaseModel):
    """Response after uploading a CV."""

    filename: str = Field(..., description="Uploaded filename")
    size: int = Field(0, description="File size in bytes")
    content_type: str = Field(..., description="MIME type of the file")
    message: str = Field("", description="Upload status message")


# ---------------------------------------------------------------------------
# Application schemas
# ---------------------------------------------------------------------------


class ApplicationCreate(BaseModel):
    """Request body for creating an application."""

    job_id: str = Field(..., description="Job identifier to apply for")
    notes: str = Field("", description="Optional notes about the application")
    match_score: float | None = Field(None, ge=0.0, le=1.0, description="Pre-computed match score")
    risk_score: float | None = Field(None, ge=0.0, le=100.0, description="Pre-computed risk score (0-100)")


class ApplicationUpdate(BaseModel):
    """Request body for updating an application."""

    status: ApplicationStatus | None = Field(None, description="New application status")
    notes: str | None = Field(None, description="Updated notes")


class ApplicationResponse(BaseModel):
    """Application detail response."""

    id: str = Field(..., description="Application identifier")
    job_id: str = Field(..., description="Associated job identifier")
    job_title: str = Field("", description="Associated job title")
    company: str = Field("", description="Associated company")
    status: str = Field("shortlisted", description="Current application status")
    notes: str = Field("", description="Application notes")
    match_score: float | None = Field(None, description="Match score at time of application")
    risk_score: float | None = Field(None, description="Risk score at time of application")
    created_at: datetime | None = Field(None, description="Application creation time")
    updated_at: datetime | None = Field(None, description="Last update time")


class ApplicationStatsResponse(BaseModel):
    """Application statistics for the current user."""

    total: int = Field(0, description="Total applications")
    by_status: dict[str, int] = Field(default_factory=dict, description="Count by status")
    avg_match_score: float | None = Field(None, description="Average match score for the authenticated candidate")
    avg_risk_score: float = Field(0.0, description="Average risk score")
    acceptance_rate: float = Field(0.0, description="Percentage of accepted offers")


# ---------------------------------------------------------------------------
# Analytics schemas
# ---------------------------------------------------------------------------


class SourceStats(BaseModel):
    """Performance metrics for a single job source."""

    source: str = Field(..., description="Source platform name")
    total_jobs: int = Field(0, description="Jobs from this source")
    avg_match_score: float | None = Field(None, description="Average match score for the authenticated candidate")
    avg_risk_score: float = Field(0.0, description="Average risk score")
    application_count: int = Field(0, description="Applications made to this source")
    success_rate: float = Field(0.0, description="Success rate for this source")


class MatchDistribution(BaseModel):
    """Distribution of match scores across jobs."""

    excellent: int = Field(0, description="Jobs with match score >= 0.8")
    good: int = Field(0, description="Jobs with match score 0.6-0.8")
    fair: int = Field(0, description="Jobs with match score 0.4-0.6")
    poor: int = Field(0, description="Jobs with match score < 0.4")
    avg_score: float | None = Field(None, description="Mean candidate-specific match score")
    median_score: float | None = Field(None, description="Median candidate-specific match score")


class ApplicationFunnel(BaseModel):
    """Application funnel stages and conversion counts."""

    viewed: int = Field(0, description="Jobs viewed")
    shortlisted: int = Field(0, description="Jobs shortlisted")
    applied: int = Field(0, description="Applications submitted")
    interview: int = Field(0, description="Interview stage")
    offered: int = Field(0, description="Offers received")
    accepted: int = Field(0, description="Offers accepted")


class ActivityItem(BaseModel):
    """Single activity event for the overview."""

    event_type: str = Field(..., description="Type of activity event")
    description: str = Field("", description="Human-readable event description")
    timestamp: datetime | None = Field(None, description="When the event occurred")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional event data")


class AnalyticsOverview(BaseModel):
    """Dashboard overview statistics."""

    total_jobs: int = Field(0, description="Total jobs in system")
    total_applications: int = Field(0, description="Total applications made")
    total_shortlisted: int = Field(0, description="Total shortlisted jobs")
    total_rejected: int = Field(0, description="Total rejected applications")
    avg_match_score: float | None = Field(None, description="Average match score for the authenticated candidate")
    avg_risk_score: float = Field(0.0, description="Average risk score")
    top_sources: list[SourceStats] = Field(default_factory=list, description="Top performing sources")
    recent_activity: list[ActivityItem] = Field(default_factory=list, description="Recent activity events")
