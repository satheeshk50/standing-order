"""End-of-run output: summary, important actions, learnings, feedback."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import llm, memory
from app.agent.prompts import FINALIZE_SCHEMA, FINALIZE_SYSTEM, finalize_user_prompt
from app.domain.enums import ActivityKind
from app.repositories import activity_repo
from app.temporal.shared import FinalizeInput, FinalizeResult

log = logging.getLogger(__name__)


async def build_report(session: AsyncSession, data: FinalizeInput) -> FinalizeResult:
    timeline = await memory.full_timeline(session, data.run_id)

    if llm.is_live():
        try:
            result = await llm.complete_json(
                model=data.config.model,
                system=FINALIZE_SYSTEM,
                user=finalize_user_prompt(data, timeline),
                schema=FINALIZE_SCHEMA,
                max_tokens=4000,
            )
            return FinalizeResult(
                summary=result.get("summary", ""),
                important_actions=result.get("important_actions", []),
                learnings=result.get("learnings", []),
                recommendations=result.get("recommendations", []),
            )
        except Exception as exc:
            log.exception("final report generation failed; using derived report")
            derived = await _derive(session, data)
            derived.summary = f"{derived.summary}\n\n(LLM report unavailable: {exc})"
            return derived

    return await _derive(session, data)


async def _derive(session: AsyncSession, data: FinalizeInput) -> FinalizeResult:
    """Report assembled from the activity log — no model required."""
    rows = await activity_repo.list_for_run(session, data.run_id, limit=500)
    actions = [r for r in rows if r.kind == ActivityKind.AGENT_ACTION]
    events = [r for r in rows if r.kind == ActivityKind.EVENT_RECEIVED]
    stats = data.stats

    reason = data.completion_reason
    outcome = (
        "delivered successfully"
        if "delivered" in reason
        else "cancelled" if "cancelled" in reason
        else "refunded" if "refund" in reason
        else "ended by an operator" if reason.startswith("operator_terminated")
        else "closed after reaching its maximum supervised age"
    )

    summary = (
        f"Order {data.order_id} was supervised for "
        f"{_duration(stats.get('run_age_seconds', 0))} and {outcome}. "
        f"The supervisor woke {stats.get('wakes', 0)} times across "
        f"{stats.get('turns', 0)} agent turns, processed "
        f"{stats.get('events', 0)} events, and executed "
        f"{stats.get('actions', 0)} business actions. "
        f"{stats.get('suppressed_events', 0)} events were judged unimportant by "
        f"the wake gate and batched rather than waking the agent.\n\n"
        f"Final memory state: {data.memory_summary or '(empty)'}"
    )

    important = [f"{a.title}: {(a.body or '')[:160]}" for a in actions[:12]] or [
        "No business actions were required during this run."
    ]

    learnings: list[str] = []
    total_events = len(events) or 1
    suppressed = stats.get("suppressed_events", 0)
    ratio = suppressed / total_events

    # Wake-gate calibration — always worth stating, since it is the main
    # cost/coverage tradeoff an operator would want to tune.
    if suppressed == 0 and total_events > 3:
        learnings.append(
            f"All {total_events} events woke the agent. A less aggressive wake "
            f"policy would let routine progress updates batch into scheduled "
            f"reviews instead of each buying a full agent turn."
        )
    elif ratio > 0.4:
        learnings.append(
            f"The wake gate suppressed {suppressed} of {total_events} events "
            f"({ratio:.0%}), so inference went almost entirely to events that "
            f"needed judgement. This wake policy is well calibrated for this "
            f"order shape."
        )
    else:
        learnings.append(
            f"The wake gate suppressed {suppressed} of {total_events} events "
            f"({ratio:.0%}) and woke for {stats.get('wakes', 0)}. The balance "
            f"looks reasonable, but a larger sample would show whether the "
            f"woken events each justified their turn."
        )

    # What the supervisor actually did, by team.
    by_team: dict[str, int] = {}
    for row in actions:
        by_team[str(row.payload.get("action", "unknown"))] = (
            by_team.get(str(row.payload.get("action", "unknown")), 0) + 1
        )
    if by_team:
        breakdown = ", ".join(f"{name} ×{count}" for name, count in by_team.items())
        learnings.append(f"Actions taken this run: {breakdown}.")
    else:
        learnings.append(
            "The supervisor never needed to intervene — this order ran clean "
            "and cost nothing beyond routine reviews."
        )

    customer_msgs = by_team.get("message_customer", 0)
    if customer_msgs > 2:
        learnings.append(
            f"The customer was contacted {customer_msgs} times. Worth checking "
            f"whether each message was independently useful or whether some "
            f"could have been consolidated into one update."
        )

    turns = stats.get("turns", 0)
    if turns and stats.get("actions", 0) == 0 and turns > 3:
        learnings.append(
            f"{turns} agent turns produced no actions at all — the review "
            f"cadence is shorter than this order needed."
        )

    if data.instructions:
        learnings.append(
            f"{len(data.instructions)} run-specific instruction(s) were added "
            f"mid-flight and applied from the following turn onward: "
            f"\"{data.instructions[0][:90]}\""
            + (f" (+{len(data.instructions) - 1} more)" if len(data.instructions) > 1 else "")
        )

    recommendations: list[str] = []
    if any(r.kind == ActivityKind.EVENT_RECEIVED and "delayed" in (r.title or "").lower() for r in rows):
        recommendations.append(
            "Shipment delays drove the escalations here. Feeding carrier ETA data "
            "in as events would let the supervisor act before the delay lands."
        )
    if stats.get("turns", 0) > 10:
        recommendations.append(
            f"{stats.get('turns')} agent turns is high for one order. Lengthening "
            f"the default sleep interval would cut cost with little risk."
        )
    recommendations.append(
        "Wake guidance refined during the run should be promoted into the "
        "supervisor template if the same pattern recurs across orders."
    )

    return FinalizeResult(
        summary=summary,
        important_actions=important,
        learnings=learnings,
        recommendations=recommendations,
    )


def _duration(seconds: int) -> str:
    seconds = int(seconds or 0)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"
