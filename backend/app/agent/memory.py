"""Timeline rendering and context compaction.

The strategy is deliberately simple, as the brief allows:

* The agent rewrites a single rolling summary every turn — that summary is the
  only long-term memory carried into future prompts.
* Timeline entries older than the compaction watermark are dropped from the
  prompt entirely; they live on in Postgres for the UI, but the model only
  ever sees the summary plus the recent tail.
* The watermark advances once the un-compacted tail grows past a threshold,
  which bounds prompt growth no matter how long the order runs.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Activity
from app.repositories import activity_repo


def render_activity(activity: Activity) -> str:
    when = activity.created_at.strftime("%Y-%m-%d %H:%M") if activity.created_at else "?"
    line = f"[{when}] {activity.kind}: {activity.title}"
    if activity.body:
        body = activity.body.strip().replace("\n", " ")
        if len(body) > 220:
            body = body[:217] + "..."
        line = f"{line} — {body}"
    return line


async def timeline_for_prompt(
    session: AsyncSession, run_id: str, *, after_seq: int, limit: int = 30
) -> tuple[list[str], int]:
    """Recent timeline lines plus the highest seq included."""
    rows = await activity_repo.recent_for_prompt(
        session, run_id, after_seq=after_seq, limit=limit
    )
    highest = rows[-1].seq if rows else after_seq
    return [render_activity(r) for r in rows], highest


async def full_timeline(session: AsyncSession, run_id: str, limit: int = 400) -> list[str]:
    """Everything, for the end-of-run report."""
    rows = await activity_repo.list_for_run(session, run_id, limit=limit)
    return [render_activity(r) for r in rows]


def should_compact(tail_length: int) -> bool:
    return tail_length >= settings.memory_compaction_threshold


def compaction_note(tail_length: int, watermark: int) -> str:
    return (
        f"Folded {tail_length} timeline entries into the rolling summary "
        f"(watermark now at seq {watermark}). Older detail stays in the "
        f"activity log but is no longer sent to the model."
    )
