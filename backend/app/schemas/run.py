from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunCreate(BaseModel):
    order_id: str = Field(min_length=1, max_length=120)
    supervisor_id: str | None = None
    order_context: dict[str, Any] = Field(default_factory=dict)
    #: Convenience: fire an ``order_created`` signal right after starting.
    seed_order_created_event: bool = True


class InstructionCreate(BaseModel):
    text: str = Field(min_length=1)
    #: Wake the agent now rather than letting it land on the next turn.
    urgent: bool = False


class ControlRequest(BaseModel):
    reason: str | None = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    seq: int
    kind: str
    actor: str
    importance: str
    title: str
    body: str | None
    payload: dict[str, Any]
    created_at: datetime


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    summary: str
    key_facts: dict[str, Any]
    open_issues: list[Any]
    wake_guidance: str | None
    compacted_through_seq: int
    compaction_count: int
    updated_at: datetime | None = None


class OutputOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary: str
    important_actions: list[Any]
    learnings: list[Any]
    recommendations: list[Any]
    stats: dict[str, Any]
    created_at: datetime


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    supervisor_id: str
    workflow_id: str
    status: str
    next_wake_at: datetime | None
    turn_count: int
    event_count: int
    action_count: int
    wake_count: int
    suppressed_event_count: int
    started_at: datetime | None
    completed_at: datetime | None
    completion_reason: str | None
    created_at: datetime


class LiveState(BaseModel):
    """Queried straight from the running workflow."""

    status: str
    paused: bool
    awake: bool
    next_wake_at: str | None
    sleep_reason: str
    memory_summary: str
    wake_guidance: str | None
    instructions: list[str]
    pending_event_count: int
    turn_count: int
    generation: int
    last_trigger: str


class RunDetail(RunSummary):
    order_context: dict[str, Any]
    supervisor_snapshot: dict[str, Any]
    sleep_reason: str | None
    instructions: list[str]
    live: LiveState | None = None
    memory: MemoryOut | None = None
    output: OutputOut | None = None
    activities: list[ActivityOut] = Field(default_factory=list)
