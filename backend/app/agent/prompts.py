"""Prompt construction.

Prefix stability matters here: the base instruction, the tool list and the
order context are identical on every wake-up, so they go first and get a cache
breakpoint. Volatile content (the event batch, elapsed time, the current
trigger) goes last, after the breakpoint.
"""

from app.domain.events import describe_event
from app.temporal.shared import AgentTurnInput, ClassifyInput, FinalizeInput

CLASSIFIER_SYSTEM = """You are a lightweight wake-up gate for an AI order supervisor.

The main supervisor agent is expensive and is currently asleep. Your only job is
to decide whether THIS event justifies waking it right now, or whether it can be
recorded and reviewed at the next scheduled wake-up.

Wake the agent when the event suggests: money at risk, a customer waiting on a
reply, a broken or stalled fulfilment path, an explicit complaint or refund, or
anything the run's wake guidance calls out.

Do NOT wake for routine progress updates that need no decision.

If the event type is unfamiliar, prefer waking — an unknown event is more likely
to need judgement than a known-benign one.

Answer with the JSON object only."""

CLASSIFIER_SCHEMA = {
    "type": "object",
    "properties": {
        "wake": {"type": "boolean"},
        "importance": {"enum": ["low", "normal", "high", "critical"]},
        "reason": {"type": "string", "maxLength": 240},
    },
    "required": ["wake", "importance", "reason"],
    "additionalProperties": False,
}


def classifier_user_prompt(data: ClassifyInput) -> str:
    guidance = data.wake_guidance or "(no specific guidance yet)"
    memory = data.memory_summary or "(no memory yet — run just started)"
    return f"""<wake_aggressiveness>{data.config.wake_aggressiveness}</wake_aggressiveness>

<wake_guidance>
{guidance}
</wake_guidance>

<current_memory>
{memory}
</current_memory>

<event>
type: {data.event.event_type}
detail: {describe_event(data.event.event_type, data.event.payload)}
source: {data.event.source}
</event>

<context>
agent_is_asleep: {data.is_asleep}
seconds_since_run_start: {data.seconds_since_last_turn}
</context>

Should the main supervisor agent be woken now?"""


# --------------------------------------------------------------------------
# Main agent
# --------------------------------------------------------------------------

AGENT_ROLE = """You are an autonomous order supervisor. You oversee a single
customer order from creation to completion.

You are not running continuously. You wake on one of three triggers — the
workflow starting, an important incoming event, or your own scheduled review —
you act, you update your memory, you choose when to wake next, and then you go
back to sleep. Token spend and needless messaging both have a cost, so only act
when acting actually helps.

How to work a turn:
1. Read the memory summary and the new events. Decide whether anything is
   actually wrong or newly actionable.
2. If it is, use your tools. Every tool call is a real, logged business action —
   the recipient team or the customer will see it. Do not send duplicate
   messages about a problem you have already escalated; the memory summary
   tells you what you already did.
3. If nothing needs doing, take no action. That is a valid and often correct
   outcome.
4. Then call `record_turn_outcome` exactly once. This is mandatory and must be
   your final tool call. It carries your assessment, your rewritten memory
   summary, and how long to sleep.

Choosing a sleep duration: short (minutes) when you are actively waiting on
something you expect imminently, long (hours) when the order is healthy and
progressing normally. There is no benefit to waking up to find nothing changed.

Run-specific instructions from the operator override your default judgement.
Honour them literally — including instructions that forbid you from acting."""


def agent_system_blocks(data: AgentTurnInput) -> list[dict]:
    """Stable prefix first, cache breakpoint at the end of it."""
    ctx = _render_kv(data.order_context)
    instructions = (
        "\n".join(f"- {t}" for t in data.instructions)
        if data.instructions
        else "(none yet)"
    )
    return [
        {
            "type": "text",
            "text": (
                f"{AGENT_ROLE}\n\n"
                f"<supervisor_instruction>\n{data.config.base_instruction}\n"
                f"</supervisor_instruction>\n\n"
                f"<order id=\"{data.order_id}\">\n{ctx}\n</order>"
            ),
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": f"<run_specific_instructions>\n{instructions}\n"
            f"</run_specific_instructions>",
        },
    ]


def agent_user_prompt(data: AgentTurnInput, timeline: list[str]) -> str:
    memory = data.memory_summary or "(this is the first turn — no memory yet)"
    events = (
        "\n".join(
            f"- {describe_event(e.event_type, e.payload)}" for e in data.pending_events
        )
        or "(no new events since your last turn)"
    )
    recent = "\n".join(f"- {line}" for line in timeline) or "(nothing recorded yet)"
    max_age = (
        f"{data.seconds_until_max_age}s until this run hits its configured max age"
        if data.seconds_until_max_age >= 0
        else "no max age configured"
    )
    return f"""<trigger>
reason: {data.trigger}
detail: {data.trigger_detail}
</trigger>

<memory_summary>
{memory}
</memory_summary>

<recent_timeline>
{recent}
</recent_timeline>

<new_events>
{events}
</new_events>

<run_state>
turn_number: {data.turn_count + 1}
run_age_seconds: {data.run_age_seconds}
{max_age}
</run_state>

Work this turn, then call record_turn_outcome once as your final tool call."""


# --------------------------------------------------------------------------
# Final report
# --------------------------------------------------------------------------

FINALIZE_SYSTEM = """You are closing out an AI order supervision run. Write the
post-run report a human operations lead would actually want to read.

Be specific and honest. If the supervisor over-messaged, missed something, or
woke up more than it needed to, say so — the learnings are the point of this
report, not a victory lap. Reference what actually happened, not generalities."""

FINALIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "important_actions": {"type": "array", "items": {"type": "string"}},
        "learnings": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "important_actions", "learnings", "recommendations"],
    "additionalProperties": False,
}


def finalize_user_prompt(data: FinalizeInput, timeline: list[str]) -> str:
    instructions = (
        "\n".join(f"- {t}" for t in data.instructions) if data.instructions else "(none)"
    )
    lines = "\n".join(f"- {line}" for line in timeline) or "(empty)"
    return f"""<order id="{data.order_id}">
{_render_kv(data.order_context)}
</order>

<final_memory_summary>
{data.memory_summary or "(empty)"}
</final_memory_summary>

<operator_instructions>
{instructions}
</operator_instructions>

<full_timeline>
{lines}
</full_timeline>

<outcome>
final_status: {data.final_status}
completion_reason: {data.completion_reason}
stats: {_render_kv(data.stats)}
</outcome>

Produce the final report as JSON."""


def _render_kv(data: dict) -> str:
    if not data:
        return "(empty)"
    return "\n".join(f"{k}: {v}" for k, v in data.items())
