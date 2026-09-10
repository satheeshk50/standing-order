"""Database-only activities. Retried by Temporal, so writes are idempotent."""

from datetime import datetime

from temporalio import activity

from app.db.models import Run
from app.db.session import SessionLocal
from app.repositories import activity_repo
from app.temporal.shared import LogActivityInput, RunStateSync


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@activity.defn(name="log_activity")
async def log_activity(data: LogActivityInput) -> str:
    async with SessionLocal() as session:
        row = await activity_repo.log(
            session,
            run_id=data.run_id,
            kind=data.kind,
            title=data.title,
            body=data.body,
            payload=data.payload,
            actor=data.actor,
            importance=data.importance,
            idempotency_key=data.idempotency_key,
        )
        return row.id


@activity.defn(name="sync_run_state")
async def sync_run_state(data: RunStateSync) -> None:
    """Mirror the workflow's live state into Postgres so the UI can read it.

    Temporal queries are the source of truth for a *running* workflow; this
    projection is what keeps completed runs, the runs list, and analytics
    queryable with plain SQL.
    """
    async with SessionLocal() as session:
        fields: dict = {
            "status": data.status,
            "next_wake_at": _parse(data.next_wake_at_iso),
            "sleep_reason": data.sleep_reason,
            "turn_count": data.turn_count,
            "event_count": data.event_count,
            "action_count": data.action_count,
            "wake_count": data.wake_count,
            "suppressed_event_count": data.suppressed_event_count,
        }
        if data.temporal_run_id:
            fields["temporal_run_id"] = data.temporal_run_id
        if data.started_at_iso:
            fields["started_at"] = _parse(data.started_at_iso)
        if data.last_agent_turn_at_iso:
            fields["last_agent_turn_at"] = _parse(data.last_agent_turn_at_iso)
        if data.completed_at_iso:
            fields["completed_at"] = _parse(data.completed_at_iso)
        if data.completion_reason:
            fields["completion_reason"] = data.completion_reason

        # Assigned directly rather than through run_repo.update, because
        # next_wake_at and sleep_reason must be *cleared* to NULL while the
        # agent is awake — a None-skipping updater would leave them stale.
        run = await session.get(Run, data.run_id)
        if run is None:
            return
        for key, value in fields.items():
            setattr(run, key, value)
        await session.commit()
