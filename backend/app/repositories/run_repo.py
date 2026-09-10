"""Run lifecycle persistence."""

from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Run, RunInstruction, RunOutput


async def get(session: AsyncSession, run_id: str) -> Run | None:
    return await session.get(Run, run_id)


async def get_by_order(session: AsyncSession, order_id: str) -> Run | None:
    stmt = select(Run).where(Run.order_id == order_id)
    return (await session.execute(stmt)).scalars().first()


async def list_runs(
    session: AsyncSession, *, status: str | None = None, limit: int = 100
) -> list[Run]:
    stmt = select(Run)
    if status:
        stmt = stmt.where(Run.status == status)
    stmt = stmt.order_by(desc(Run.created_at)).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def create(session: AsyncSession, **kwargs: Any) -> Run:
    run = Run(**kwargs)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def update(session: AsyncSession, run_id: str, **fields: Any) -> Run | None:
    run = await session.get(Run, run_id)
    if run is None:
        return None
    for key, value in fields.items():
        if value is not None or key in ("next_wake_at", "sleep_reason"):
            setattr(run, key, value)
    await session.commit()
    await session.refresh(run)
    return run


async def bump_counters(session: AsyncSession, run_id: str, **deltas: int) -> None:
    run = await session.get(Run, run_id)
    if run is None:
        return
    for key, delta in deltas.items():
        setattr(run, key, (getattr(run, key) or 0) + delta)
    await session.commit()


# --- instructions -------------------------------------------------------


async def add_instruction(
    session: AsyncSession, run_id: str, text: str, *, urgent: bool = False
) -> RunInstruction:
    row = RunInstruction(run_id=run_id, text=text, urgent=urgent)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_instructions(
    session: AsyncSession, run_id: str
) -> list[RunInstruction]:
    stmt = (
        select(RunInstruction)
        .where(RunInstruction.run_id == run_id)
        .order_by(RunInstruction.created_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


# --- final output -------------------------------------------------------


async def save_output(
    session: AsyncSession,
    run_id: str,
    *,
    summary: str,
    important_actions: list,
    learnings: list,
    recommendations: list,
    stats: dict,
) -> RunOutput:
    existing = await session.get(RunOutput, run_id)
    if existing is None:
        existing = RunOutput(run_id=run_id)
        session.add(existing)
    existing.summary = summary
    existing.important_actions = important_actions
    existing.learnings = learnings
    existing.recommendations = recommendations
    existing.stats = stats
    await session.commit()
    await session.refresh(existing)
    return existing


async def get_output(session: AsyncSession, run_id: str) -> RunOutput | None:
    return await session.get(RunOutput, run_id)


def utcnow() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
