"""Tool definitions handed to the model.

Five business actions (each writes an activity row and nothing else — no real
integrations, per the brief) plus one runtime capability, `record_turn_outcome`,
which is how the agent records its reasoning, refreshes memory, and sets its own
next wake-up.
"""

from typing import Any

from app.domain.enums import BUSINESS_ACTIONS

#: Which team each messaging action addresses. Used for the activity title.
ACTION_TARGETS: dict[str, str] = {
    "message_fulfillment_team": "Fulfillment team",
    "message_payments_team": "Payments team",
    "message_logistics_team": "Logistics team",
    "message_customer": "Customer",
    "create_internal_note": "Internal note",
}

_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "description": "The message body. Write it as you would actually send it.",
        },
        "reason": {
            "type": "string",
            "description": "Why this message is necessary right now.",
        },
        "urgency": {"enum": ["low", "normal", "high", "critical"]},
    },
    "required": ["message", "reason"],
    "additionalProperties": False,
}

_BUSINESS_TOOL_SPECS: dict[str, dict[str, Any]] = {
    "message_fulfillment_team": {
        "description": (
            "Message the fulfillment team about picking, packing, stock or "
            "order preparation problems."
        ),
        "input_schema": _MESSAGE_SCHEMA,
    },
    "message_payments_team": {
        "description": (
            "Message the payments team about failed charges, refunds, "
            "chargebacks or billing discrepancies."
        ),
        "input_schema": _MESSAGE_SCHEMA,
    },
    "message_logistics_team": {
        "description": (
            "Message the logistics team about carriers, shipment delays, "
            "routing or delivery exceptions."
        ),
        "input_schema": _MESSAGE_SCHEMA,
    },
    "message_customer": {
        "description": (
            "Send a message directly to the customer. Use sparingly and only "
            "when the customer genuinely needs to hear from us."
        ),
        "input_schema": _MESSAGE_SCHEMA,
    },
    "create_internal_note": {
        "description": (
            "Record an internal note on the order for human operators. Use for "
            "observations that need a paper trail but no immediate action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {"type": "string"},
                "category": {
                    "enum": ["observation", "risk", "escalation", "resolution"]
                },
            },
            "required": ["note"],
            "additionalProperties": False,
        },
    },
}

RECORD_OUTCOME_TOOL: dict[str, Any] = {
    "name": "record_turn_outcome",
    "description": (
        "MANDATORY final tool call for every turn. Records your assessment, "
        "rewrites the compact memory summary, and sets when you wake next. "
        "Call this exactly once, after any business actions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "assessment": {
                "type": "string",
                "description": "One or two sentences on the order's current health.",
            },
            "memory_summary": {
                "type": "string",
                "description": (
                    "The COMPLETE rewritten memory summary — this replaces the "
                    "previous one. Keep it under ~200 words. It must carry "
                    "everything a future turn needs: order state, what you have "
                    "already done and told whom, open issues, and what you are "
                    "waiting on. Anything you leave out is forgotten."
                ),
            },
            "sleep_seconds": {
                "type": "integer",
                "description": (
                    "Seconds until your next scheduled review. Use minutes when "
                    "actively waiting on something, hours when the order is "
                    "healthy. Important events wake you sooner regardless."
                ),
                "minimum": 5,
            },
            "sleep_reason": {
                "type": "string",
                "description": "Why this interval, and what you expect to find.",
            },
            "wake_guidance": {
                "type": "string",
                "description": (
                    "Optional. Instructions for the cheap wake-up gate about "
                    "what should or should not wake you from here on."
                ),
            },
            "recommend_completion": {
                "type": "boolean",
                "description": (
                    "Set true if you believe the order lifecycle is finished. "
                    "This is advisory only — the workflow decides when to end."
                ),
            },
            "completion_rationale": {"type": "string"},
        },
        "required": [
            "assessment",
            "memory_summary",
            "sleep_seconds",
            "sleep_reason",
        ],
        "additionalProperties": False,
    },
}


def build_tools(allowed_actions: list[str]) -> list[dict[str, Any]]:
    """Tool list for one supervisor template.

    ``strict: true`` guarantees the arguments validate against the schema, so
    downstream code can index the payload without defensive parsing.
    """
    tools: list[dict[str, Any]] = []
    for name in BUSINESS_ACTIONS:
        if allowed_actions and name not in allowed_actions:
            continue
        spec = _BUSINESS_TOOL_SPECS[name]
        tools.append(
            {
                "name": name,
                "description": spec["description"],
                "input_schema": spec["input_schema"],
                "strict": True,
            }
        )
    tools.append({**RECORD_OUTCOME_TOOL, "strict": True})
    return tools


def summarize_action(name: str, payload: dict) -> tuple[str, str]:
    """(title, body) for the activity row a business action produces."""
    target = ACTION_TARGETS.get(name, name)
    if name == "create_internal_note":
        category = payload.get("category", "observation")
        return f"Internal note ({category})", payload.get("note", "")
    urgency = payload.get("urgency", "normal")
    body = payload.get("message", "")
    reason = payload.get("reason")
    if reason:
        body = f"{body}\n\n— Reason: {reason}"
    return f"Message to {target} [{urgency}]", body
