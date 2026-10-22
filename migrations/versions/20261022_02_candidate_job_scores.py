"""Store match scores per candidate and job.

Revision ID: 20261022_02
Revises: 20261022_01
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_02"
down_revision = "20261022_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("candidates") or not inspector.has_table("jobs"):
        # Fresh databases create all ORM tables during application startup.
        return
    if inspector.has_table("candidate_job_scores"):
        return
    op.create_table(
        "candidate_job_scores",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("breakdown", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("classification", sa.String(length=50), nullable=True),
        sa.Column("algorithm_version", sa.String(length=50), nullable=False, server_default="job-scorer-v1"),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "job_id", name="uq_candidate_job_score"),
    )
    op.create_index(
        "ix_candidate_job_scores_candidate_score",
        "candidate_job_scores",
        ["candidate_id", "score"],
    )
    op.create_index("ix_candidate_job_scores_job_id", "candidate_job_scores", ["job_id"])


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("candidate_job_scores"):
        op.drop_index("ix_candidate_job_scores_job_id", table_name="candidate_job_scores")
        op.drop_index("ix_candidate_job_scores_candidate_score", table_name="candidate_job_scores")
        op.drop_table("candidate_job_scores")
