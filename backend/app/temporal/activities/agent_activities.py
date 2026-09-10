"""Activities that involve the LLM. Thin wrappers over ``app.agent``."""

import logging

from temporalio import activity

from app.agent import classifier, final_report, supervisor_agent
from app.db.session import SessionLocal
from app.domain.enums import ActivityKind, Actor, Importance, RunStatus
from app.domain.events import describe_event
from app.repositories import activity_repo, memory_repo, run_repo
from app.temporal.shared import (
    AgentTurnInput,
    AgentTurnResult,
    ClassifyInput,
    ClassifyResult,
    FinalizeInput,
    FinalizeResult,
)

log = logging.getLogger(__name__)


@activity.defn(name="classify_event")
async def classify_event(data: ClassifyInput) -> ClassifyResult:
    """Record the incoming event, then decide whether it wakes the agent.

    Both writes are keyed on the event id, so a Temporal retry of this activity
    refreshes the existing rows instead of duplicating the timeline.
    """
    async with SessionLocal() as session:
        event = data.event
        await activity_repo.log(
            session,
            run_id=data.run_id,
            kind=ActivityKind.EVENT_RECEIVED,
            title=describe_event(event.event_type, event.payload),
            body=None,
            payload={
                "event_type": event.event_type,
                "source": event.source,
                **event.payload,
            },
            actor=Actor.SYSTEM,
            idempotency_key=f"{data.run_id}:event:{event.event_id}",
        )

        decision = await classifier.classify(data)

        await activity_repo.log(
            session,
            run_id=data.run_id,
            kind=ActivityKind.CLASSIFIER_DECISION,
            title=(
                f"Wake gate: WAKE — {event.event_type}"
                if decision.wake
                else f"Wake gate: stay asleep — {event.event_type}"
            ),
            body=decision.reason,
            payload={
                "wake": decision.wake,
                "importance": decision.importance,
                "event_type": event.event_type,
                "is_terminal_event": decision.is_terminal_event,
                "is_unknown_event": decision.is_unknown_event,
            },
            actor=Actor.CLASSIFIER,
            importance=(
                Importance.HIGH if decision.wake else Importance.LOW
            ),
            idempotency_key=f"{data.run_id}:classify:{event.event_id}",
        )
        return decision


@activity.defn(name="run_agent_turn")
async def run_agent_turn(data: AgentTurnInput) -> AgentTurnResult:
    async with SessionLocal() as session:
        result = await supervisor_agent.run_turn(session, data)
        await run_repo.update(
            session, data.run_id, last_agent_turn_at=run_repo.utcnow()
        )
        return result


@activity.defn(name="finalize_run")
async def finalize_run(data: FinalizeInput) -> FinalizeResult:
    """Final agent step, then persist the report and close the run record."""
    async with SessionLocal() as session:
        report = await final_report.build_report(session, data)

        await run_repo.save_output(
            session,
            data.run_id,
            summary=report.summary,
            important_actions=report.important_actions,
            learnings=report.learnings,
            recommendations=report.recommendations,
            stats=data.stats,
        )

        body = "\n\n".join(
            filter(
                None,
                [
                    report.summary,
                    _bullets("Important actions", report.important_actions),
                    _bullets("Key learnings", report.learnings),
                    _bullets("Recommendations", report.recommendations),
                ],
            )
        )
        await activity_repo.log(
            session,
            run_id=data.run_id,
            kind=ActivityKind.FINAL_OUTPUT,
            title="Final report",
            body=body,
            payload={
                "completion_reason": data.completion_reason,
                "final_status": data.final_status,
                "stats": data.stats,
            },
            actor=Actor.AGENT,
            importance=Importance.CRITICAL,
            idempotency_key=f"{data.run_id}:final",
        )

        await run_repo.update(
            session,
            data.run_id,
            status=data.final_status,
            completed_at=run_repo.utcnow(),
            completion_reason=data.completion_reason,
        )
        # Freeze the last memory state alongside the report.
        memory = await memory_repo.get(session, data.run_id)
        if memory and not memory.summary:
            await memory_repo.save(session, data.run_id, summary=data.memory_summary)
        return report


def _bullets(heading: str, items: list[str]) -> str:
    if not items:
        return ""
    lines = "\n".join(f"• {item}" for item in items)
    return f"{heading}:\n{lines}"
