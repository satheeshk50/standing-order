"""Writes and reads against the unified activity log."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Activity
from app.domain.enums import ActivityKind, Actor, Importance


async def next_seq(session: AsyncSession, run_id: str) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(Activity.seq), 0)).where(
            Activity.run_id == run_id
        )
    )
    return int(result.scalar_one()) + 1


async def log(
    session: AsyncSession,
    *,
    run_id: str,
    kind: ActivityKind | str,
    title: str,
    body: str | None = None,
    payload: dict[str, Any] | None = None,
    actor: Actor | str = Actor.SYSTEM,
    importance: Importance | str = Importance.NORMAL,
    idempotency_key: str | None = None,
) -> Activity:
    """Append one row.

    When ``idempotency_key`` is supplied the write is an upsert, so a retried
    Temporal activity refreshes its row rather than duplicating the timeline.
    """
    seq = await next_seq(session, run_id)
    values = {
        "run_id": run_id,
        "seq": seq,
        "kind": str(kind),
        "actor": str(actor),
        "importance": str(importance),
        "title": title[:300],
        "body": body,
        "payload": payload or {},
        "idempotency_key": idempotency_key,
    }

    if idempotency_key:
        stmt = (
            pg_insert(Activity)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[Activity.idempotency_key],
                set_={
                    "title": values["title"],
                    "body": values["body"],
                    "payload": values["payload"],
                    "importance": values["importance"],
                },
            )
            .returning(Activity)
        )
        row = (await session.execute(stmt)).scalar_one()
        await session.commit()
        return row

    activity = Activity(**values)
    session.add(activity)
    await session.commit()
    return activity


async def list_for_run(
    session: AsyncSession,
    run_id: str,
    *,
    kinds: list[str] | None = None,
    limit: int = 500,
) -> list[Activity]:
    stmt = select(Activity).where(Activity.run_id == run_id)
    if kinds:
        stmt = stmt.where(Activity.kind.in_(kinds))
    stmt = stmt.order_by(Activity.seq.asc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def recent_for_prompt(
    session: AsyncSession, run_id: str, *, after_seq: int = 0, limit: int = 40
) -> list[Activity]:
    """Timeline entries the agent has not yet folded into its summary."""
    stmt = (
        select(Activity)
        .where(Activity.run_id == run_id, Activity.seq > after_seq)
        .where(
            Activity.kind.in_(
                [
                    ActivityKind.EVENT_RECEIVED,
                    ActivityKind.AGENT_ACTION,
                    ActivityKind.AGENT_TURN,
                    ActivityKind.INSTRUCTION_ADDED,
                    ActivityKind.CONTROL,
                ]
            )
        )
        .order_by(Activity.seq.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
