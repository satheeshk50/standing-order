"""initial schema

Status / kind / importance columns are plain VARCHARs rather than Postgres
ENUMs. Values are validated by the Python StrEnums in app.domain.enums; keeping
them out of the database means adding a new event kind is a code change, not a
migration with an ALTER TYPE in it.

Revision ID: 0001
Create Date: 2026-09-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supervisors",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("base_instruction", sa.Text(), nullable=False),
        sa.Column(
            "allowed_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "default_wake_seconds", sa.Integer(), nullable=False, server_default="900"
        ),
        sa.Column(
            "max_run_age_seconds",
            sa.Integer(),
            nullable=False,
            server_default="604800",
        ),
        sa.Column(
            "wake_aggressiveness",
            sa.String(20),
            nullable=False,
            server_default="balanced",
        ),
        sa.Column("wake_guidance", sa.Text()),
        sa.Column(
            "model", sa.String(100), nullable=False, server_default="claude-opus-5"
        ),
        sa.Column(
            "classifier_model",
            sa.String(100),
            nullable=False,
            server_default="claude-haiku-4-5",
        ),
        sa.Column("effort", sa.String(20), nullable=False, server_default="medium"),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_supervisors_id", "supervisors", ["id"])

    op.create_table(
        "runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "supervisor_id",
            sa.String(),
            sa.ForeignKey("supervisors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("order_id", sa.String(120), nullable=False, unique=True),
        sa.Column("workflow_id", sa.String(200), nullable=False),
        sa.Column("temporal_run_id", sa.String(200)),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column(
            "order_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "supervisor_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("next_wake_at", sa.DateTime(timezone=True)),
        sa.Column("last_agent_turn_at", sa.DateTime(timezone=True)),
        sa.Column("sleep_reason", sa.Text()),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wake_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "suppressed_event_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completion_reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_runs_id", "runs", ["id"])
    op.create_index("ix_runs_order_id", "runs", ["order_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_workflow_id", "runs", ["workflow_id"])
    op.create_index("ix_runs_supervisor_id", "runs", ["supervisor_id"])

    op.create_table(
        "activities",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(20), nullable=False, server_default="system"),
        sa.Column("importance", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("idempotency_key", sa.String(300), unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_activities_id", "activities", ["id"])
    op.create_index("ix_activities_run_id", "activities", ["run_id"])
    op.create_index("ix_activities_seq", "activities", ["seq"])
    op.create_index("ix_activities_kind", "activities", ["kind"])
    op.create_index(
        "ix_activities_idempotency_key", "activities", ["idempotency_key"]
    )
    # The timeline is always read run-scoped and seq-ordered.
    op.create_index("ix_activities_run_seq", "activities", ["run_id", "seq"])

    op.create_table(
        "run_memory",
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "key_facts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "open_issues",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("wake_guidance", sa.Text()),
        sa.Column(
            "compacted_through_seq", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("compaction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_table(
        "run_instructions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False, server_default="user"),
        sa.Column("urgent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_run_instructions_id", "run_instructions", ["id"])
    op.create_index("ix_run_instructions_run_id", "run_instructions", ["run_id"])

    op.create_table(
        "run_outputs",
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "important_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "learnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "recommendations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("run_outputs")
    op.drop_table("run_instructions")
    op.drop_table("run_memory")
    op.drop_table("activities")
    op.drop_table("runs")
    op.drop_table("supervisors")
