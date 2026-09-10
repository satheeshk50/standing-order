"""Supervisor template persistence."""

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Supervisor


async def get(session: AsyncSession, supervisor_id: str) -> Supervisor | None:
    return await session.get(Supervisor, supervisor_id)


async def list_all(session: AsyncSession) -> list[Supervisor]:
    stmt = select(Supervisor).order_by(
        desc(Supervisor.is_default), desc(Supervisor.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_default(session: AsyncSession) -> Supervisor | None:
    stmt = select(Supervisor).where(Supervisor.is_default.is_(True))
    found = (await session.execute(stmt)).scalars().first()
    if found:
        return found
    return (await session.execute(select(Supervisor))).scalars().first()


async def create(session: AsyncSession, **kwargs: Any) -> Supervisor:
    supervisor = Supervisor(**kwargs)
    session.add(supervisor)
    await session.commit()
    await session.refresh(supervisor)
    return supervisor


async def update(
    session: AsyncSession, supervisor_id: str, **fields: Any
) -> Supervisor | None:
    supervisor = await session.get(Supervisor, supervisor_id)
    if supervisor is None:
        return None
    for key, value in fields.items():
        if value is not None:
            setattr(supervisor, key, value)
    await session.commit()
    await session.refresh(supervisor)
    return supervisor
