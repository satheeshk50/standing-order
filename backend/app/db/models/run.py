"""One row per supervised order — mirrors the live Temporal workflow state."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col, uuid_pk


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = uuid_pk()
    supervisor_id: Mapped[str] = mapped_column(
        ForeignKey("supervisors.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    #: Business key. Unique — one supervisor workflow per order, enforced both
    #: here and by the Temporal workflow id.
    order_id: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True, index=True
    )
    workflow_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    temporal_run_id: Mapped[str | None] = mapped_column(String(200))

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )

    #: Snapshot of the order at run start (items, customer, value, ...).
    order_context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    #: Snapshot of the supervisor template, so later template edits don't
    #: retroactively change how a historical run is interpreted.
    supervisor_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    # --- Live sleep / wake state ---------------------------------------
    next_wake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_agent_turn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sleep_reason: Mapped[str | None] = mapped_column(Text)

    # --- Analytics ------------------------------------------------------
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wake_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Events the classifier judged unimportant — the whole point of the gate.
    suppressed_event_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    supervisor = relationship("Supervisor", lazy="joined")
