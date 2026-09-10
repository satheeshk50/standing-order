"""The unified activity log.

Every observable thing that happens to a run lands here: incoming events,
classifier wake decisions, agent turns, the 5 business actions, sleep
decisions, operator instructions and controls, and the final output. The UI
renders this table directly as both the timeline and the action history.
"""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[str] = uuid_pk()
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: Monotonic per-run ordering. Wall-clock timestamps can collide when a
    #: single agent turn writes several rows in the same millisecond.
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, index=True)

    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(20), nullable=False, default="system")
    importance: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    #: Temporal retries activities. Every writer passes a deterministic key so
    #: a retried attempt updates its row instead of duplicating it.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(300), unique=True, index=True
    )

    created_at: Mapped[datetime] = created_at_col()
