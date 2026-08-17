"""Database models for the job intelligence platform.

SQLAlchemy 2.0 declarative style with async support.
Uses generic types for SQLite compatibility; swap to PostgreSQL types in production.
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship


def _uuid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Source(Base):
    """Tracks job sources with intelligence metrics."""

    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(String(1024), nullable=False)
    tier = Column(Integer, default=2)
    enabled = Column(Boolean, default=True)
    country_focus = Column(String(10))

    jobs_found = Column(Integer, default=0)
    unique_jobs = Column(Integer, default=0)
    duplicate_rate = Column(Float, default=0.0)
    average_match_score = Column(Float, default=0.0)
    risk_rate = Column(Float, default=0.0)
    applications = Column(Integer, default=0)
    interviews = Column(Integer, default=0)
    offers = Column(Integer, default=0)

    last_scraped_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    jobs = relationship("Job", back_populates="source", lazy="selectin")
    job_fingerprints = relationship("JobFingerprint", back_populates="source", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Source {self.name} (tier={self.tier})>"


class User(Base):
    """Basic auth user."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    candidates = relationship("Candidate", back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class Job(Base):
    """The core normalized job model."""

    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False, index=True)
    source_job_id = Column(String(255), nullable=False)

    title = Column(String(500), nullable=False)
    company = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    requirements = Column(Text, default="[]")
    responsibilities = Column(Text, default="[]")
    skills = Column(Text, default="[]")

    location = Column(String(500), nullable=True)
    country = Column(String(10), nullable=True)
    remote = Column(Boolean, default=False)
    remote_type = Column(String(10), nullable=True)

    employment_type = Column(String(20), nullable=True)
    experience_level = Column(String(20), nullable=True)

    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    salary_currency = Column(String(3), nullable=True)
    salary_period = Column(String(10), nullable=True)

    application_url = Column(String(2048), nullable=True)
    company_url = Column(String(2048), nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    closing_at = Column(DateTime(timezone=True), nullable=True)

    raw_hash = Column(String(64), nullable=True)
    fingerprint = Column(String(255), nullable=True, index=True)

    risk_score = Column(Float, default=0.0)
    risk_level = Column(String(10), nullable=True)
    risk_flags = Column(Text, default="[]")

    match_score = Column(Float, default=0.0)
    match_breakdown = Column(Text, default="{}")
    classification = Column(String(50), nullable=True)

    status = Column(String(20), default="discovered", nullable=False)

    scraped_at = Column(DateTime(timezone=True), server_default=func.now())
    analyzed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    source = relationship("Source", back_populates="jobs")
    applications = relationship("Application", back_populates="job", lazy="selectin")
    canonical_fingerprint = relationship("JobFingerprint", back_populates="canonical_job", uselist=False)

    __table_args__ = (
        Index("ix_jobs_company_status", "company", "status"),
        Index("ix_jobs_experience_level", "experience_level"),
        Index("ix_jobs_created_at", "created_at"),
        UniqueConstraint("source_id", "source_job_id", name="uq_source_source_job"),
    )

    @property
    def skills_list(self) -> list[str]:
        try:
            return json.loads(self.skills) if self.skills else []
        except (json.JSONDecodeError, TypeError):
            return []

    @skills_list.setter
    def skills_list(self, value: list[str]) -> None:
        self.skills = json.dumps(value)

    @property
    def risk_flags_list(self) -> list[dict]:
        try:
            return json.loads(self.risk_flags) if self.risk_flags else []
        except (json.JSONDecodeError, TypeError):
            return []

    @risk_flags_list.setter
    def risk_flags_list(self, value: list[dict]) -> None:
        self.risk_flags = json.dumps(value)

    @property
    def match_breakdown_dict(self) -> dict:
        try:
            return json.loads(self.match_breakdown) if self.match_breakdown else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @match_breakdown_dict.setter
    def match_breakdown_dict(self, value: dict) -> None:
        self.match_breakdown = json.dumps(value)

    def __repr__(self) -> str:
        return f"<Job {self.title} at {self.company}>"


class Candidate(Base):
    """User profile for job matching."""

    __tablename__ = "candidates"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)

    education = Column(Text, default="[]")
    experience = Column(Text, default="[]")
    skills = Column(Text, default="[]")
    projects = Column(Text, default="[]")
    certifications = Column(Text, default="[]")
    languages = Column(Text, default="[]")

    preferred_roles = Column(Text, default="[]")
    preferred_locations = Column(Text, default="[]")
    remote_preference = Column(String(10), nullable=True)
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    salary_currency = Column(String(3), nullable=True)
    experience_level = Column(String(20), nullable=True)

    cv_file_path = Column(String(1024), nullable=True)
    cv_parsed = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="candidates")
    applications = relationship("Application", back_populates="candidate", lazy="selectin")

    __table_args__: tuple = ()

    @property
    def skills_list(self) -> list[str]:
        try:
            return json.loads(self.skills) if self.skills else []
        except (json.JSONDecodeError, TypeError):
            return []

    @skills_list.setter
    def skills_list(self, value: list[str]) -> None:
        self.skills = json.dumps(value)

    @property
    def preferred_locations_list(self) -> list[str]:
        try:
            return json.loads(self.preferred_locations) if self.preferred_locations else []
        except (json.JSONDecodeError, TypeError):
            return []

    @preferred_locations_list.setter
    def preferred_locations_list(self, value: list[str]) -> None:
        self.preferred_locations = json.dumps(value)

    @property
    def preferred_roles_list(self) -> list[str]:
        try:
            return json.loads(self.preferred_roles) if self.preferred_roles else []
        except (json.JSONDecodeError, TypeError):
            return []

    @preferred_roles_list.setter
    def preferred_roles_list(self, value: list[str]) -> None:
        self.preferred_roles = json.dumps(value)

    def __repr__(self) -> str:
        return f"<Candidate {self.name}>"


class Application(Base):
    """Tracks job applications."""

    __tablename__ = "applications"

    id = Column(String(36), primary_key=True, default=_uuid)
    candidate_id = Column(String(36), ForeignKey("candidates.id"), nullable=False, index=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False, index=True)

    status = Column(String(20), default="shortlisted", nullable=False)

    applied_at = Column(DateTime(timezone=True), nullable=True)
    cv_version = Column(Integer, default=1)
    notes = Column(Text, nullable=True)
    follow_up_date = Column(DateTime(timezone=True), nullable=True)
    cover_letter_path = Column(String(1024), nullable=True)

    match_score = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    candidate = relationship("Candidate", back_populates="applications")
    job = relationship("Job", back_populates="applications")
    status_changes = relationship("ApplicationStatusChange", back_populates="application", lazy="selectin")

    __table_args__ = (
        Index("ix_applications_candidate_status", "candidate_id", "status"),
        Index("ix_applications_job_status", "job_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Application {self.candidate_id} -> {self.job_id} ({self.status})>"


class ApplicationStatusChange(Base):
    """Audit log for application status changes."""

    __tablename__ = "application_status_changes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(
        String(36),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text, nullable=True)

    application = relationship("Application", back_populates="status_changes")

    __table_args__ = (
        Index("ix_status_changes_application_id", "application_id"),
        Index("ix_status_changes_changed_at", "changed_at"),
    )

    def __repr__(self) -> str:
        return f"<StatusChange {self.old_status} -> {self.new_status}>"


class JobFingerprint(Base):
    """Dedup tracking for jobs."""

    __tablename__ = "job_fingerprints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint = Column(String(255), unique=True, nullable=False, index=True)
    canonical_job_id = Column(
        String(36),
        ForeignKey("jobs.id"),
        nullable=False,
        index=True,
    )
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    canonical_job = relationship("Job", back_populates="canonical_fingerprint")
    source = relationship("Source", back_populates="job_fingerprints")

    def __repr__(self) -> str:
        return f"<JobFingerprint {self.fingerprint[:16]}...>"


class TelegramUser(Base):
    """Tracks Telegram users for bot alerts."""

    __tablename__ = "telegram_users"

    id = Column(String(36), primary_key=True, default=_uuid)
    chat_id = Column(String(50), unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)

    is_active = Column(Boolean, default=True)
    keywords = Column(Text, default="[]")
    exclude_keywords = Column(Text, default="[]")
    min_salary = Column(Integer, nullable=True)
    preferred_locations = Column(Text, default="[]")

    last_notified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    @property
    def keywords_list(self) -> list[str]:
        try:
            return json.loads(self.keywords) if self.keywords else []
        except (json.JSONDecodeError, TypeError):
            return []

    @keywords_list.setter
    def keywords_list(self, value: list[str]) -> None:
        self.keywords = json.dumps(value)

    @property
    def exclude_keywords_list(self) -> list[str]:
        try:
            return json.loads(self.exclude_keywords) if self.exclude_keywords else []
        except (json.JSONDecodeError, TypeError):
            return []

    @exclude_keywords_list.setter
    def exclude_keywords_list(self, value: list[str]) -> None:
        self.exclude_keywords = json.dumps(value)

    def __repr__(self) -> str:
        return f"<TelegramUser {self.chat_id} ({self.username})>"


class Database:
    """Async database session management."""

    def __init__(self, database_url: str) -> None:
        connect_args = {}
        if "sqlite" in database_url:
            connect_args["check_same_thread"] = False

        self.engine = create_async_engine(
            database_url,
            echo=False,
            connect_args=connect_args,
        )
        self.async_session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def get_session(self):
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def init_db(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()
