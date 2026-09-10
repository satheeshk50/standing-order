"""Shared vocabulary. Imported by every layer; imports nothing itself."""

from enum import StrEnum


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"  # agent is actively reasoning / acting
    SLEEPING = "sleeping"  # waiting on a timer or a signal
    PAUSED = "paused"  # operator halted the agent; events still queue
    COMPLETED = "completed"  # ended by a workflow-owned lifecycle rule
    TERMINATED = "terminated"  # ended by an operator
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (RunStatus.COMPLETED, RunStatus.TERMINATED, RunStatus.FAILED)


class EventType(StrEnum):
    ORDER_CREATED = "order_created"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_FAILED = "payment_failed"
    SHIPMENT_CREATED = "shipment_created"
    SHIPMENT_DELAYED = "shipment_delayed"
    DELIVERED = "delivered"
    REFUND_REQUESTED = "refund_requested"
    REFUND_COMPLETED = "refund_completed"
    ORDER_CANCELLED = "order_cancelled"
    CUSTOMER_MESSAGE_RECEIVED = "customer_message_received"
    NO_UPDATE_FOR_N_HOURS = "no_update_for_n_hours"


#: Events that end the order lifecycle. Completion is workflow-owned: the agent
#: may *recommend* finishing, but only these (or an operator, or max age) do it.
TERMINAL_EVENTS: frozenset[str] = frozenset(
    {
        EventType.DELIVERED,
        EventType.REFUND_COMPLETED,
        EventType.ORDER_CANCELLED,
    }
)

#: Events that always wake the agent, without spending a classifier call.
ALWAYS_WAKE_EVENTS: frozenset[str] = frozenset(
    {
        EventType.PAYMENT_FAILED,
        EventType.REFUND_REQUESTED,
        EventType.SHIPMENT_DELAYED,
        EventType.ORDER_CANCELLED,
    }
    | set(TERMINAL_EVENTS)
)

#: Low-signal events that never justify waking the agent on their own.
NEVER_WAKE_EVENTS: frozenset[str] = frozenset({EventType.SHIPMENT_CREATED})


class ActivityKind(StrEnum):
    """Every row in the unified activity log is one of these."""

    EVENT_RECEIVED = "event_received"
    CLASSIFIER_DECISION = "classifier_decision"
    AGENT_TURN = "agent_turn"
    AGENT_ACTION = "agent_action"  # one of the 5 business actions
    SLEEP_SCHEDULED = "sleep_scheduled"
    WAKE = "wake"
    INSTRUCTION_ADDED = "instruction_added"
    MEMORY_UPDATED = "memory_updated"
    CONTROL = "control"  # pause / resume / interrupt / terminate
    FINAL_OUTPUT = "final_output"
    SYSTEM = "system"


class Importance(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Actor(StrEnum):
    SYSTEM = "system"
    AGENT = "agent"
    CLASSIFIER = "classifier"
    USER = "user"


class WakeAggressiveness(StrEnum):
    """How eagerly the classifier should wake the main agent."""

    LOW = "low"  # only critical events
    BALANCED = "balanced"
    HIGH = "high"  # wake on anything ambiguous


class TriggerReason(StrEnum):
    """The three inference triggers required by the brief, plus operator ones."""

    WORKFLOW_START = "workflow_start"
    SIGNAL = "signal"
    SCHEDULED_WAKEUP = "scheduled_wakeup"
    INSTRUCTION = "instruction"
    INTERRUPT = "interrupt"
    FINALIZING = "finalizing"


#: The 5 business actions the agent may execute. Each produces an activity row.
BUSINESS_ACTIONS: tuple[str, ...] = (
    "message_fulfillment_team",
    "message_payments_team",
    "message_logistics_team",
    "message_customer",
    "create_internal_note",
)
