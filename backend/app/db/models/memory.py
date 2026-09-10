"""Compact rolling memory — one row per run, rewritten by the agent."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RunMemory(Base):
    __tablename__ = "run_memory"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: The rolling narrative summary. This is what gets sent to the model on
    #: every wake-up instead of the full history.
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Durable structured facts, e.g. {"carrier": "DHL", "refund_open": true}.
    key_facts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    #: Unresolved problems the agent is tracking.
    open_issues: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    #: Agent-authored steer for the classifier (a "good-to-have" in the brief):
    #: the main agent can tell the gate what to wake it for next time.
    wake_guidance: Mapped[str | None] = mapped_column(Text)

    #: How many timeline entries have already been folded into `summary`.
    compacted_through_seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    compaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
