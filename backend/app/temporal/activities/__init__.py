"""Every side effect the workflow performs lives behind one of these."""

from app.temporal.activities.agent_activities import (
    classify_event,
    finalize_run,
    run_agent_turn,
)
from app.temporal.activities.persistence_activities import (
    log_activity,
    sync_run_state,
)

ALL_ACTIVITIES = [
    classify_event,
    run_agent_turn,
    finalize_run,
    log_activity,
    sync_run_state,
]

__all__ = [
    "ALL_ACTIVITIES",
    "classify_event",
    "finalize_run",
    "log_activity",
    "run_agent_turn",
    "sync_run_state",
]
