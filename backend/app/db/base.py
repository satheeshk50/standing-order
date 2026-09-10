"""Declarative base + the metadata Alembic autogenerates against."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[str]:
    return mapped_column(
        primary_key=True, default=lambda: str(uuid.uuid4()), index=True
    )


def created_at_col() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
