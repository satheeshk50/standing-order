"""The wake-up gate.

Every incoming event passes through here before the expensive agent is allowed
to run. Cheap deterministic rules answer most cases outright; only genuinely
ambiguous events cost a (small, fast) model call.

Order of resolution:
  1. Terminal events   -> always wake (the run is about to end).
  2. Known-critical    -> always wake, no model call.
  3. Known-benign      -> never wake on their own, no model call.
  4. Unknown type      -> wake, and flag it (unknown-event escalation).
  5. Everything else   -> one Haiku call with structured output.
"""

from __future__ import annotations

import logging

from app.agent import llm
from app.agent.prompts import (
    CLASSIFIER_SCHEMA,
    CLASSIFIER_SYSTEM,
    classifier_user_prompt,
)
from app.domain.enums import (
    ALWAYS_WAKE_EVENTS,
    NEVER_WAKE_EVENTS,
    TERMINAL_EVENTS,
    EventType,
    Importance,
    WakeAggressiveness,
)
from app.temporal.shared import ClassifyInput, ClassifyResult

log = logging.getLogger(__name__)

_KNOWN_EVENTS = {str(e) for e in EventType}


async def classify(data: ClassifyInput) -> ClassifyResult:
    event_type = data.event.event_type
    is_terminal = event_type in TERMINAL_EVENTS

    if is_terminal:
        return ClassifyResult(
            wake=True,
            importance=Importance.CRITICAL,
            reason="Terminal order event — the supervisor must close the run out.",
            is_terminal_event=True,
        )

    if event_type in ALWAYS_WAKE_EVENTS:
        return ClassifyResult(
            wake=True,
            importance=Importance.HIGH,
            reason=f"'{event_type}' is always escalated by policy.",
        )

    if event_type not in _KNOWN_EVENTS:
        # Unknown-event escalation: an unrecognised event is more likely to
        # need judgement than a known-benign one, so we wake rather than guess.
        return ClassifyResult(
            wake=True,
            importance=Importance.HIGH,
            reason=f"Unrecognised event type '{event_type}' — escalating to the agent.",
            is_unknown_event=True,
        )

    aggressiveness = data.config.wake_aggressiveness

    if event_type in NEVER_WAKE_EVENTS and aggressiveness != WakeAggressiveness.HIGH:
        return ClassifyResult(
            wake=False,
            importance=Importance.LOW,
            reason="Routine progress update — batched for the next scheduled review.",
        )

    if not llm.is_live():
        return _heuristic(data)

    try:
        result = await llm.complete_json(
            model=data.config.classifier_model,
            system=CLASSIFIER_SYSTEM,
            user=classifier_user_prompt(data),
            schema=CLASSIFIER_SCHEMA,
            max_tokens=300,
        )
        wake = bool(result.get("wake"))
        # The aggressiveness dial is applied on top of the model's judgement,
        # so the operator's setting always has the final say.
        if aggressiveness == WakeAggressiveness.HIGH and result.get("importance") in (
            "normal",
            "high",
            "critical",
        ):
            wake = True
        if aggressiveness == WakeAggressiveness.LOW and result.get("importance") in (
            "low",
            "normal",
        ):
            wake = False
        return ClassifyResult(
            wake=wake,
            importance=result.get("importance", Importance.NORMAL),
            reason=result.get("reason", ""),
        )
    except Exception as exc:
        # A failing gate must not silence the supervisor — fail open.
        log.warning("classifier call failed, falling back to heuristic: %s", exc)
        fallback = _heuristic(data)
        fallback.reason = f"{fallback.reason} (classifier unavailable: {exc})"
        return fallback


def _heuristic(data: ClassifyInput) -> ClassifyResult:
    """Deterministic policy — also the mock-mode implementation."""
    event_type = data.event.event_type
    aggressiveness = data.config.wake_aggressiveness

    if event_type == EventType.ORDER_CREATED:
        return ClassifyResult(
            wake=True,
            importance=Importance.NORMAL,
            reason="Order created — the supervisor needs to establish its plan.",
        )
    if event_type == EventType.CUSTOMER_MESSAGE_RECEIVED:
        return ClassifyResult(
            wake=True,
            importance=Importance.HIGH,
            reason="A customer is waiting on a reply.",
        )
    if event_type == EventType.NO_UPDATE_FOR_N_HOURS:
        hours = int(data.event.payload.get("hours", 0) or 0)
        wake = hours >= 12 or aggressiveness == WakeAggressiveness.HIGH
        return ClassifyResult(
            wake=wake,
            importance=Importance.NORMAL if wake else Importance.LOW,
            reason=(
                f"Order has been silent for {hours}h — worth a look."
                if wake
                else f"Only {hours}h of silence; will review on schedule."
            ),
        )
    if event_type == EventType.PAYMENT_CONFIRMED:
        wake = aggressiveness == WakeAggressiveness.HIGH
        return ClassifyResult(
            wake=wake,
            importance=Importance.LOW,
            reason=(
                "Aggressive wake policy — reviewing every state change."
                if wake
                else "Expected happy-path progress; batched for the next review."
            ),
        )

    wake = aggressiveness != WakeAggressiveness.LOW
    return ClassifyResult(
        wake=wake,
        importance=Importance.NORMAL,
        reason=(
            "Unclassified event under a non-conservative wake policy."
            if wake
            else "Low wake policy — deferring to the next scheduled review."
        ),
    )
