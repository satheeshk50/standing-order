"""Operator instructions added to a run after it has already started."""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk


class RunInstruction(Base):
    __tablename__ = "run_instructions"

    id: Mapped[str] = uuid_pk()
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="user")
    #: When true the workflow wakes the agent immediately rather than letting
    #: the instruction land on the next scheduled turn.
    urgent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at_col()
