"""One agent turn: reason, act through tools, update memory, choose a sleep.

This module is deliberately free of Temporal imports — it is a plain async
function you can call from a test or a REPL. The Temporal activity is a thin
wrapper around it.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import llm, memory
from app.agent.prompts import agent_system_blocks, agent_user_prompt
from app.agent.tools.registry import build_tools, summarize_action
from app.config import settings
from app.domain.enums import (
    ActivityKind,
    Actor,
    EventType,
    Importance,
    TriggerReason,
)
from app.domain.events import describe_event
from app.repositories import activity_repo, memory_repo
from app.temporal.shared import AgentTurnInput, AgentTurnResult, ExecutedAction

log = logging.getLogger(__name__)

_OUTCOME_TOOL = "record_turn_outcome"


async def run_turn(session: AsyncSession, data: AgentTurnInput) -> AgentTurnResult:
    timeline, highest_seq = await memory.timeline_for_prompt(
        session, data.run_id, after_seq=data.compacted_through_seq
    )

    outcome: dict = {}
    actions: list[ExecutedAction] = []

    async def execute_tool(name: str, payload: dict, tool_use_id: str) -> str:
        if name == _OUTCOME_TOOL:
            outcome.update(payload)
            return "Turn outcome recorded."

        title, body = summarize_action(name, payload)
        await activity_repo.log(
            session,
            run_id=data.run_id,
            kind=ActivityKind.AGENT_ACTION,
            title=title,
            body=body,
            payload={"action": name, **payload},
            actor=Actor.AGENT,
            importance=payload.get("urgency", Importance.NORMAL),
            # Derived from the workflow-generated turn id, so an activity retry
            # updates this row instead of sending the message twice.
            idempotency_key=f"{data.run_id}:{data.turn_id}:{tool_use_id}",
        )
        actions.append(
            ExecutedAction(name=name, target=title, summary=(body or "")[:400])
        )
        return f"Recorded: {title}"

    if llm.is_live():
        try:
            reasoning, _ = await llm.run_tool_loop(
                model=data.config.model,
                system=agent_system_blocks(data),
                messages=[{"role": "user", "content": agent_user_prompt(data, timeline)}],
                tools=build_tools(data.config.allowed_actions),
                effort=data.config.effort or settings.agent_effort,
                max_tokens=settings.agent_max_tokens,
                max_iterations=settings.agent_max_tool_iterations,
                execute_tool=execute_tool,
            )
        except Exception as exc:
            # A failed LLM turn must not kill a multi-day workflow. Log it,
            # fall back to the deterministic policy, and keep supervising.
            log.exception("agent turn failed, falling back to heuristic policy")
            await activity_repo.log(
                session,
                run_id=data.run_id,
                kind=ActivityKind.SYSTEM,
                title=(
                    "Agent turn partially completed, then failed"
                    if actions
                    else "Agent turn fell back to the deterministic policy"
                ),
                body=str(exc),
                importance=Importance.HIGH,
            )
            if actions:
                # The model already executed business actions this turn before
                # it died. Running the deterministic policy now would repeat
                # them from scratch — a second apology to the same customer,
                # under a different tool_use_id so the idempotency key cannot
                # catch it. Keep what was done and let the turn close out.
                reasoning = (
                    f"Turn interrupted after {len(actions)} action(s) had "
                    f"already been taken: {', '.join(a.name for a in actions)}. "
                    "The deterministic policy was skipped to avoid repeating "
                    "them."
                )
            else:
                reasoning = await _heuristic_turn(data, execute_tool, outcome)
    else:
        reasoning = await _heuristic_turn(data, execute_tool, outcome)

    if not outcome:
        # The model finished without the mandatory closing call. Fill in a safe
        # default rather than losing the turn.
        outcome = _default_outcome(data, reasoning)

    # --- memory + compaction ------------------------------------------
    tail_length = len(timeline)
    compacted = memory.should_compact(tail_length)
    watermark = highest_seq if compacted else data.compacted_through_seq

    summary = (outcome.get("memory_summary") or data.memory_summary or "").strip()
    wake_guidance = (outcome.get("wake_guidance") or "").strip() or None

    await memory_repo.save(
        session,
        data.run_id,
        summary=summary,
        wake_guidance=wake_guidance,
        compacted_through_seq=watermark,
        compacted=compacted,
    )

    assessment = outcome.get("assessment") or reasoning or "No assessment recorded."
    sleep_seconds = int(outcome.get("sleep_seconds") or data.config.default_wake_seconds)
    sleep_reason = outcome.get("sleep_reason") or "Routine scheduled review."

    await activity_repo.log(
        session,
        run_id=data.run_id,
        kind=ActivityKind.AGENT_TURN,
        title=f"Agent turn #{data.turn_count + 1} ({data.trigger})",
        body=assessment,
        payload={
            "trigger": data.trigger,
            "trigger_detail": data.trigger_detail,
            "actions": [a.name for a in actions],
            "sleep_seconds": sleep_seconds,
            "reasoning": reasoning[:4000] if reasoning else "",
            "llm_mode": llm.mode(),
            "model": data.config.model if llm.is_live() else "heuristic-policy",
        },
        actor=Actor.AGENT,
        importance=Importance.HIGH if actions else Importance.NORMAL,
        idempotency_key=f"{data.run_id}:{data.turn_id}:turn",
    )

    if compacted:
        await activity_repo.log(
            session,
            run_id=data.run_id,
            kind=ActivityKind.MEMORY_UPDATED,
            title="Memory compacted",
            body=memory.compaction_note(tail_length, watermark),
            payload={"watermark": watermark, "folded_entries": tail_length},
            actor=Actor.AGENT,
            idempotency_key=f"{data.run_id}:{data.turn_id}:compact",
        )
    else:
        await activity_repo.log(
            session,
            run_id=data.run_id,
            kind=ActivityKind.MEMORY_UPDATED,
            title="Memory summary updated",
            body=summary,
            payload={"length": len(summary)},
            actor=Actor.AGENT,
            importance=Importance.LOW,
            idempotency_key=f"{data.run_id}:{data.turn_id}:memory",
        )

    return AgentTurnResult(
        reasoning=reasoning or "",
        assessment=assessment,
        actions=actions,
        memory_summary=summary,
        wake_guidance=wake_guidance,
        sleep_seconds=sleep_seconds,
        sleep_reason=sleep_reason,
        recommend_completion=bool(outcome.get("recommend_completion")),
        completion_rationale=outcome.get("completion_rationale"),
        compacted=compacted,
        compacted_through_seq=watermark,
        llm_mode=llm.mode(),
    )


def _default_outcome(data: AgentTurnInput, reasoning: str) -> dict:
    return {
        "assessment": reasoning or "Turn completed without an explicit assessment.",
        "memory_summary": data.memory_summary,
        "sleep_seconds": data.config.default_wake_seconds,
        "sleep_reason": "Default interval — the agent did not set one.",
    }


# --------------------------------------------------------------------------
# Deterministic policy
#
# Used in mock mode (no API key) and as the fallback when a live call fails.
# It exercises exactly the same tool-execution path as the model does, so the
# timeline, memory and UI behave identically either way.
# --------------------------------------------------------------------------


async def _heuristic_turn(data: AgentTurnInput, execute_tool, outcome: dict) -> str:
    allowed = set(data.config.allowed_actions or [])
    notes: list[str] = []
    actions_taken: list[str] = []
    sleep = data.config.default_wake_seconds
    recommend_completion = False

    async def act(name: str, payload: dict) -> None:
        # A tool the template does not grant is silently skipped — the same
        # constraint the model sees, since it is never offered the tool.
        if allowed and name not in allowed:
            return
        await execute_tool(name, payload, f"heuristic-{name}-{len(actions_taken)}")
        actions_taken.append(name)

    if data.trigger == TriggerReason.WORKFLOW_START:
        await act(
            "create_internal_note",
            {
                "note": (
                    f"Supervision started for order {data.order_id}. Watching for "
                    "payment confirmation, shipment creation and delivery. Will "
                    "escalate on payment failure, delay or customer contact."
                ),
                "category": "observation",
            },
        )
        notes.append("Opened supervision and set the initial watch list.")

    for event in data.pending_events:
        etype = event.event_type
        detail = describe_event(etype, event.payload)

        if etype == EventType.PAYMENT_FAILED:
            await act(
                "message_payments_team",
                {
                    "message": (
                        f"Payment failed on order {data.order_id} "
                        f"({event.payload.get('reason', 'unknown reason')}). "
                        "Please retry or contact the customer for an alternative "
                        "method before we lose the order."
                    ),
                    "reason": "Revenue at risk; the order cannot ship unpaid.",
                    "urgency": "high",
                },
            )
            notes.append(f"Escalated to payments: {detail}.")
            sleep = min(sleep, 600)

        elif etype == EventType.SHIPMENT_DELAYED:
            hours = event.payload.get("delay_hours", "unknown")
            await act(
                "message_logistics_team",
                {
                    "message": (
                        f"Shipment for order {data.order_id} is delayed by {hours}h "
                        f"({event.payload.get('reason', 'no reason given')}). "
                        "Please confirm a revised delivery date."
                    ),
                    "reason": "Delivery promise is at risk.",
                    "urgency": "high",
                },
            )
            await act(
                "message_customer",
                {
                    "message": (
                        "We're sorry — your delivery is running behind schedule. "
                        "We're chasing the carrier and will confirm a new date "
                        "shortly. No action is needed from you."
                    ),
                    "reason": "Proactive contact prevents an inbound complaint.",
                    "urgency": "normal",
                },
            )
            notes.append(f"Chased logistics and notified the customer: {detail}.")
            sleep = min(sleep, 1800)

        elif etype == EventType.REFUND_REQUESTED:
            await act(
                "message_payments_team",
                {
                    "message": (
                        f"Refund requested on order {data.order_id}: "
                        f"{event.payload.get('reason', 'no reason given')}. "
                        "Please process and confirm."
                    ),
                    "reason": "Customer has requested their money back.",
                    "urgency": "high",
                },
            )
            notes.append(f"Routed refund request to payments: {detail}.")
            sleep = min(sleep, 900)

        elif etype == EventType.CUSTOMER_MESSAGE_RECEIVED:
            await act(
                "message_customer",
                {
                    "message": (
                        "Thanks for getting in touch — I've picked this up and I'm "
                        "checking your order status now. I'll come back to you "
                        "with a concrete update shortly."
                    ),
                    "reason": "A customer is waiting; acknowledge before investigating.",
                    "urgency": "normal",
                },
            )
            notes.append("Acknowledged the customer's inbound message.")
            sleep = min(sleep, 900)

        elif etype == EventType.NO_UPDATE_FOR_N_HOURS:
            await act(
                "message_fulfillment_team",
                {
                    "message": (
                        f"Order {data.order_id} has had no status change for "
                        f"{event.payload.get('hours', '?')}h. Please confirm it is "
                        "still progressing."
                    ),
                    "reason": "Silent orders are usually stuck orders.",
                    "urgency": "normal",
                },
            )
            notes.append("Chased fulfillment about the stalled order.")

        elif etype == EventType.DELIVERED:
            await act(
                "create_internal_note",
                {
                    "note": "Order delivered. Closing out supervision.",
                    "category": "resolution",
                },
            )
            notes.append("Order was delivered.")
            recommend_completion = True

        elif etype in (EventType.REFUND_COMPLETED, EventType.ORDER_CANCELLED):
            await act(
                "create_internal_note",
                {
                    "note": f"Order reached a terminal state: {detail}.",
                    "category": "resolution",
                },
            )
            notes.append(f"Terminal state reached: {detail}.")
            recommend_completion = True

        elif etype == EventType.ORDER_CREATED:
            notes.append(
                "Order created and acknowledged — awaiting payment confirmation."
            )

        elif etype == EventType.PAYMENT_CONFIRMED:
            notes.append("Payment confirmed — happy path, no action needed.")

        elif etype == EventType.SHIPMENT_CREATED:
            notes.append(
                f"Shipment created ({event.payload.get('carrier', 'carrier')}) — "
                "tracking normally."
            )

        else:
            await act(
                "create_internal_note",
                {
                    "note": (
                        f"Unrecognised event '{etype}' received: {detail}. "
                        "Flagging for human review — no automated handling exists."
                    ),
                    "category": "risk",
                },
            )
            notes.append(f"Escalated unknown event '{etype}' for human review.")

    if not notes:
        notes.append("Scheduled review — nothing new since the last turn.")

    escalated = len(actions_taken) > 0
    if escalated:
        # Something needed chasing; come back sooner than the default.
        sleep = min(sleep, max(data.config.default_wake_seconds // 2, 60))

    assessment = " ".join(notes)
    summary = _fold_summary(data.memory_summary or "", notes, data)

    outcome.update(
        {
            "assessment": assessment,
            "memory_summary": summary,
            "sleep_seconds": sleep,
            "sleep_reason": (
                "Shortened interval — waiting on a reply to an open escalation."
                if escalated
                else "Order looks healthy; next routine review."
            ),
            "recommend_completion": recommend_completion,
            "completion_rationale": (
                "A terminal order event was observed." if recommend_completion else None
            ),
        }
    )
    return assessment


_HEADER_PREFIX = "ORDER"
_MAX_SUMMARY_LINES = 10


def _fold_summary(previous: str, notes: list[str], data: AgentTurnInput) -> str:
    """Rolling summary as a bounded bullet list.

    Kept as discrete lines rather than one growing paragraph so that
    de-duplication actually works and the oldest entries can be dropped
    cleanly — concatenating prose just accumulates repeated fragments.
    """
    header = (
        f"{_HEADER_PREFIX} {data.order_id} — "
        f"{data.order_context.get('customer_name', 'customer')}, "
        f"value {data.order_context.get('value', 'n/a')}, "
        f"{data.order_context.get('priority', 'standard')} priority."
    )

    existing = [
        line.strip().lstrip("- ").strip()
        for line in previous.splitlines()
        if line.strip() and not line.startswith(_HEADER_PREFIX)
    ]

    for note in notes:
        if note not in existing:
            existing.append(note)

    if len(existing) > _MAX_SUMMARY_LINES:
        dropped = len(existing) - _MAX_SUMMARY_LINES
        existing = [
            f"(+{dropped} earlier step(s) folded away)"
        ] + existing[-_MAX_SUMMARY_LINES:]

    return "\n".join([header] + [f"- {line}" for line in existing])
