"""A reusable supervisor template: instruction, tools, wake policy, model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, created_at_col, uuid_pk


class Supervisor(Base):
    __tablename__ = "supervisors"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    #: The agent's standing system instruction.
    base_instruction: Mapped[str] = mapped_column(Text, nullable=False)

    #: Subset of domain.enums.BUSINESS_ACTIONS this template may execute.
    allowed_actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # --- Wake / sleep policy -------------------------------------------
    default_wake_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=900
    )
    max_run_age_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60 * 60 * 24 * 7
    )
    wake_aggressiveness: Mapped[str] = mapped_column(
        String(20), nullable=False, default="balanced"
    )
    #: Natural-language steer handed to the classifier. The main agent may
    #: refine this at runtime (stored per-run on run_memory.wake_guidance).
    wake_guidance: Mapped[str | None] = mapped_column(Text)

    # --- Model config ---------------------------------------------------
    model: Mapped[str] = mapped_column(
        String(100), nullable=False, default="gemini-3.5-flash"
    )
    classifier_model: Mapped[str] = mapped_column(
        String(100), nullable=False, default="gemini-3.5-flash-lite"
    )
    effort: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")

    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
