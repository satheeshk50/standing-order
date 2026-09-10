"""Dataclasses that cross the workflow <-> activity boundary.

Everything here must be JSON-serialisable and must not pull in the DB, the
LLM client, or anything else with side effects — the workflow sandbox imports
this module directly.
"""

from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------
# Workflow input
# --------------------------------------------------------------------------


@dataclass
class SupervisorConfig:
    """Snapshot of a supervisor template, frozen at run start."""

    supervisor_id: str
    name: str
    base_instruction: str
    allowed_actions: list[str]
    default_wake_seconds: int
    max_run_age_seconds: int
    wake_aggressiveness: str
    wake_guidance: str | None
    model: str
    classifier_model: str
    effort: str


@dataclass
class WorkflowCarryOver:
    """State handed forward across a ``continue_as_new`` boundary."""

    memory_summary: str = ""
    wake_guidance: str | None = None
    instructions: list[str] = field(default_factory=list)
    turn_count: int = 0
    event_count: int = 0
    action_count: int = 0
    wake_count: int = 0
    suppressed_event_count: int = 0
    compacted_through_seq: int = 0
    started_at_iso: str | None = None
    generation: int = 0
    pending_events: list[dict] = field(default_factory=list)
    unprocessed_events: list[dict] = field(default_factory=list)
    paused: bool = False


@dataclass
class RunParams:
    run_id: str
    order_id: str
    order_context: dict[str, Any]
    config: SupervisorConfig
    carry_over: WorkflowCarryOver | None = None


# --------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------


@dataclass
class IncomingEvent:
    event_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "generator"
    received_at_iso: str | None = None


@dataclass
class IncomingInstruction:
    instruction_id: str
    text: str
    urgent: bool = False


@dataclass
class ControlSignal:
    action: str  # pause | resume | interrupt | terminate
    reason: str | None = None


# --------------------------------------------------------------------------
# Activity inputs / outputs
# --------------------------------------------------------------------------


@dataclass
class ClassifyInput:
    run_id: str
    event: IncomingEvent
    config: SupervisorConfig
    wake_guidance: str | None
    memory_summary: str
    seconds_since_last_turn: int
    is_asleep: bool


@dataclass
class ClassifyResult:
    wake: bool
    importance: str
    reason: str
    is_terminal_event: bool = False
    is_unknown_event: bool = False


@dataclass
class AgentTurnInput:
    run_id: str
    turn_id: str
    order_id: str
    order_context: dict[str, Any]
    config: SupervisorConfig
    trigger: str
    trigger_detail: str
    memory_summary: str
    wake_guidance: str | None
    instructions: list[str]
    pending_events: list[IncomingEvent]
    compacted_through_seq: int
    run_age_seconds: int
    seconds_until_max_age: int
    turn_count: int


@dataclass
class ExecutedAction:
    name: str
    target: str
    summary: str


@dataclass
class AgentTurnResult:
    reasoning: str
    assessment: str
    actions: list[ExecutedAction] = field(default_factory=list)
    memory_summary: str = ""
    wake_guidance: str | None = None
    sleep_seconds: int = 900
    sleep_reason: str = ""
    recommend_completion: bool = False
    completion_rationale: str | None = None
    compacted: bool = False
    compacted_through_seq: int = 0
    llm_mode: str = "mock"


@dataclass
class FinalizeInput:
    run_id: str
    order_id: str
    order_context: dict[str, Any]
    config: SupervisorConfig
    memory_summary: str
    instructions: list[str]
    completion_reason: str
    final_status: str
    stats: dict[str, Any]


@dataclass
class FinalizeResult:
    summary: str
    important_actions: list[str] = field(default_factory=list)
    learnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class RunStateSync:
    """Pushes the workflow's live state down into Postgres for the UI."""

    run_id: str
    status: str
    next_wake_at_iso: str | None = None
    sleep_reason: str | None = None
    last_agent_turn_at_iso: str | None = None
    turn_count: int = 0
    event_count: int = 0
    action_count: int = 0
    wake_count: int = 0
    suppressed_event_count: int = 0
    temporal_run_id: str | None = None
    started_at_iso: str | None = None
    completed_at_iso: str | None = None
    completion_reason: str | None = None


@dataclass
class LogActivityInput:
    run_id: str
    kind: str
    title: str
    body: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    actor: str = "system"
    importance: str = "normal"
    idempotency_key: str | None = None


# --------------------------------------------------------------------------
# Query result
# --------------------------------------------------------------------------


@dataclass
class WorkflowStateView:
    """What ``get_state`` returns to the API — the live in-workflow truth."""

    run_id: str
    order_id: str
    status: str
    paused: bool
    awake: bool
    next_wake_at_iso: str | None
    sleep_reason: str
    memory_summary: str
    wake_guidance: str | None
    instructions: list[str]
    pending_event_count: int
    turn_count: int
    event_count: int
    action_count: int
    wake_count: int
    suppressed_event_count: int
    generation: int
    started_at_iso: str | None
    last_trigger: str
    completion_reason: str | None
