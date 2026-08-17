"""Database models for Work Hunter Bot."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    source = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    url = Column(String, nullable=False, unique=True)
    location = Column(String, default="")
    remote = Column(Boolean, default=False)
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    tech_stack = Column(Text, default="[]")
    job_type = Column(String, default="full_time")
    description = Column(Text, default="")
    scraped_at = Column(DateTime, default=datetime.utcnow)
    notified = Column(Boolean, default=False, index=True)

    def __repr__(self) -> str:
        return f"<Job {self.title} @ {self.company}>"


class UserPreferences(Base):
    __tablename__ = "preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String, unique=True, nullable=False)
    keywords = Column(Text, default="[]")
    exclude_keywords = Column(Text, default="[]")
    min_salary = Column(Integer, default=0)
    tech_stack = Column(Text, default="[]")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    chat_id = Column(String, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)


class ScraperState(Base):
    __tablename__ = "scraper_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, unique=True, nullable=False)
    last_run = Column(DateTime, nullable=True)
    last_url = Column(String, nullable=True)
    jobs_found = Column(Integer, default=0)
    errors = Column(Integer, default=0)


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    chat_id = Column(String, nullable=False)
    status = Column(String, default="pending", index=True)
    match_score = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=True)
    notes = Column(Text, default="")
    applied_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    interview_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    STATUSES = ["pending", "applied", "responded", "interview", "offer", "rejected", "withdrawn"]

    def __repr__(self) -> str:
        return f"<Application job={self.job_id} status={self.status}>"


class Database:
    """Database operations for Work Hunter Bot."""

    def __init__(self, db_path: str = "work_hunter.db"):
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def add_job(self, job_data: dict) -> bool:
        """Add a job to the database. Returns True if new, False if duplicate."""
        session = self.get_session()
        try:
            existing = session.query(Job).filter_by(url=job_data["url"]).first()
            if existing:
                return False

            job = Job(**job_data)
            session.add(job)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()

    def get_unnotified_jobs(self, limit: int = 10) -> list[Job]:
        """Get jobs that haven't been notified yet."""
        session = self.get_session()
        try:
            return (
                session.query(Job)
                .filter_by(notified=False)
                .order_by(Job.scraped_at.desc())
                .limit(limit)
                .all()
            )
        finally:
            session.close()

    def mark_notified(self, job_id: str) -> None:
        """Mark a job as notified."""
        session = self.get_session()
        try:
            job = session.query(Job).filter_by(id=job_id).first()
            if job:
                job.notified = True
                session.commit()
        finally:
            session.close()

    def get_stats(self) -> dict:
        """Get job statistics."""
        session = self.get_session()
        try:
            total = session.query(Job).count()
            sources = {}
            for source in session.query(Job.source, func.count(Job.id)).group_by(Job.source).all():
                sources[source[0]] = source[1]
            return {"total": total, "by_source": sources}
        finally:
            session.close()

    def update_scraper_state(self, source: str, **kwargs) -> None:
        """Update scraper state."""
        session = self.get_session()
        try:
            state = session.query(ScraperState).filter_by(source=source).first()
            if not state:
                state = ScraperState(source=source)
                session.add(state)
            for key, value in kwargs.items():
                setattr(state, key, value)
            session.commit()
        finally:
            session.close()

    def get_active_users(self) -> list[UserPreferences]:
        """Get all active users."""
        session = self.get_session()
        try:
            return session.query(UserPreferences).filter_by(is_active=True).all()
        finally:
            session.close()

    def add_application(self, job_id: str, chat_id: str, match_score: float = 0, risk_score: float = 0) -> bool:
        """Track a new job application. Returns True if created."""
        session = self.get_session()
        try:
            existing = session.query(Application).filter_by(job_id=job_id, chat_id=chat_id).first()
            if existing:
                return False
            app = Application(
                job_id=job_id,
                chat_id=chat_id,
                match_score=match_score,
                risk_score=risk_score,
                applied_at=datetime.utcnow(),
                status="applied",
            )
            session.add(app)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()

    def update_application_status(self, job_id: str, chat_id: str, status: str) -> bool:
        """Update application status. Returns True if updated."""
        if status not in Application.STATUSES:
            return False
        session = self.get_session()
        try:
            app = session.query(Application).filter_by(job_id=job_id, chat_id=chat_id).first()
            if not app:
                return False
            app.status = status
            app.updated_at = datetime.utcnow()
            if status == "responded":
                app.responded_at = datetime.utcnow()
            elif status == "interview":
                app.interview_at = datetime.utcnow()
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()

    def get_user_applications(self, chat_id: str, status: str | None = None) -> list[Application]:
        """Get all applications for a user, optionally filtered by status."""
        session = self.get_session()
        try:
            query = session.query(Application).filter_by(chat_id=chat_id)
            if status:
                query = query.filter_by(status=status)
            return query.order_by(Application.created_at.desc()).all()
        finally:
            session.close()

    def get_application_stats(self, chat_id: str) -> dict:
        """Get application statistics for a user."""
        session = self.get_session()
        try:
            total = session.query(Application).filter_by(chat_id=chat_id).count()
            by_status = {}
            for status, count in session.query(
                Application.status, func.count(Application.id)
            ).filter_by(chat_id=chat_id).group_by(Application.status).all():
                by_status[status] = count
            return {"total": total, "by_status": by_status}
        finally:
            session.close()
