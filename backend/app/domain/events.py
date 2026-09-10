"""Catalog of simulated order events used by the generator and the UI."""

from app.domain.enums import EventType

#: Human-readable label + a sensible default payload for each event type.
#: The UI renders this catalog as the event-injection panel.
EVENT_CATALOG: dict[str, dict] = {
    EventType.ORDER_CREATED: {
        "label": "Order created",
        "default_payload": {"note": "Order placed by customer"},
    },
    EventType.PAYMENT_CONFIRMED: {
        "label": "Payment confirmed",
        "default_payload": {"amount": 129.99, "currency": "USD"},
    },
    EventType.PAYMENT_FAILED: {
        "label": "Payment failed",
        "default_payload": {"reason": "card_declined", "attempt": 1},
    },
    EventType.SHIPMENT_CREATED: {
        "label": "Shipment created",
        "default_payload": {"carrier": "DHL", "tracking": "DH-88213771"},
    },
    EventType.SHIPMENT_DELAYED: {
        "label": "Shipment delayed",
        "default_payload": {"delay_hours": 48, "reason": "carrier_backlog"},
    },
    EventType.DELIVERED: {
        "label": "Delivered",
        "default_payload": {"signed_by": "customer"},
    },
    EventType.REFUND_REQUESTED: {
        "label": "Refund requested",
        "default_payload": {"reason": "item_damaged", "amount": 129.99},
    },
    EventType.REFUND_COMPLETED: {
        "label": "Refund completed",
        "default_payload": {"amount": 129.99},
    },
    EventType.ORDER_CANCELLED: {
        "label": "Order cancelled",
        "default_payload": {"reason": "customer_request"},
    },
    EventType.CUSTOMER_MESSAGE_RECEIVED: {
        "label": "Customer message received",
        "default_payload": {"message": "Where is my order? It's been a week."},
    },
    EventType.NO_UPDATE_FOR_N_HOURS: {
        "label": "No update for N hours",
        "default_payload": {"hours": 24},
    },
}


def describe_event(event_type: str, payload: dict | None) -> str:
    """One-line rendering of an event, used in prompts and the timeline."""
    label = EVENT_CATALOG.get(event_type, {}).get("label", event_type)
    if not payload:
        return label
    bits = ", ".join(f"{k}={v}" for k, v in payload.items() if v is not None)
    return f"{label} ({bits})" if bits else label
