"""Seed the hardcoded supervisor templates.  ``python -m app.seed``

Three templates that differ in the ways that actually matter — wake
aggressiveness, tool allowlist, and sleep cadence — so the difference is
visible in a demo rather than cosmetic.
"""

import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.db.models import Supervisor
from app.db.session import SessionLocal
from app.domain.enums import BUSINESS_ACTIONS

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("seed")

TEMPLATES = [
    {
        "name": "Standard Order Supervisor",
        "description": (
            "Balanced default. Watches the full order lifecycle, escalates real "
            "problems, and stays quiet on the happy path."
        ),
        "base_instruction": (
            "You supervise a single customer order end to end. Your goal is that "
            "the customer receives what they ordered, on time, without having to "
            "chase anyone.\n\n"
            "Escalate payment problems to the payments team, fulfilment problems "
            "to the fulfilment team, and carrier or delivery problems to the "
            "logistics team. Contact the customer proactively when something will "
            "visibly affect them — a delay, a cancellation, a refund — and when "
            "they have written in.\n\n"
            "Do not message anyone just to report that things are fine. Do not "
            "repeat an escalation you have already made unless the situation has "
            "materially changed."
        ),
        "allowed_actions": list(BUSINESS_ACTIONS),
        "default_wake_seconds": 900,
        "max_run_age_seconds": 60 * 60 * 24 * 7,
        "wake_aggressiveness": "balanced",
        "wake_guidance": (
            "Wake me for payment failures, shipment delays, refund requests, "
            "customer messages, and anything unrecognised. Routine progress "
            "updates can wait for my scheduled review."
        ),
        "is_default": True,
    },
    {
        "name": "High-Value Order Watchdog",
        "description": (
            "Paranoid mode for expensive orders. Wakes on almost everything and "
            "reviews frequently."
        ),
        "base_instruction": (
            "You supervise a HIGH VALUE order. The cost of a lost or unhappy "
            "customer here far exceeds the cost of your attention, so err "
            "decisively towards acting early.\n\n"
            "Escalate at the first sign of trouble rather than waiting for "
            "confirmation. Keep the customer informed proactively. Leave an "
            "internal note at every meaningful state change so a human can "
            "reconstruct what happened without reading the whole timeline."
        ),
        "allowed_actions": list(BUSINESS_ACTIONS),
        "default_wake_seconds": 300,
        "max_run_age_seconds": 60 * 60 * 24 * 14,
        "wake_aggressiveness": "high",
        "wake_guidance": (
            "Wake me for every event. This order is too valuable to batch "
            "anything, including routine progress updates."
        ),
        "is_default": False,
    },
    {
        "name": "Hands-Off Supervisor (internal only)",
        "description": (
            "Never contacts the customer. Observes, notes, and escalates "
            "internally only — useful when a human owns the customer relationship."
        ),
        "base_instruction": (
            "You supervise this order in an observe-and-escalate capacity only.\n\n"
            "You must NEVER contact the customer directly — a human account "
            "manager owns that relationship. Route everything through the "
            "internal teams and leave internal notes.\n\n"
            "Be conservative about waking: this order is monitored by a human "
            "during business hours, so only genuine exceptions need your "
            "attention."
        ),
        # message_customer is deliberately absent — the tool is not even
        # offered to the model, so the constraint is structural, not just a
        # line in the prompt.
        "allowed_actions": [
            "message_fulfillment_team",
            "message_payments_team",
            "message_logistics_team",
            "create_internal_note",
        ],
        "default_wake_seconds": 3600,
        "max_run_age_seconds": 60 * 60 * 24 * 30,
        "wake_aggressiveness": "low",
        "wake_guidance": (
            "Only wake me for hard failures: payment failure, cancellation, "
            "refund, or an unrecognised event. Everything else waits."
        ),
        "is_default": False,
    },
]


async def seed() -> None:
    """Insert the templates, and keep existing rows pointed at the configured
    models.

    The model columns are deliberately taken from settings rather than
    hardcoded here: a template row written under one provider's defaults
    would otherwise keep those model names forever, and every run started
    from it would address the wrong API.
    """
    models = {
        "model": settings.agent_model,
        "classifier_model": settings.classifier_model,
    }
    async with SessionLocal() as session:
        created = updated = 0
        for template in TEMPLATES:
            existing = (
                await session.execute(
                    select(Supervisor).where(Supervisor.name == template["name"])
                )
            ).scalars().first()
            if existing:
                stale = [
                    k for k, v in models.items() if getattr(existing, k) != v
                ]
                if stale:
                    for key, value in models.items():
                        setattr(existing, key, value)
                    updated += 1
                    log.info(
                        "  ~ %s (re-pointed %s)",
                        template["name"],
                        ", ".join(stale),
                    )
                else:
                    log.info("  = %s (already exists)", template["name"])
                continue
            session.add(Supervisor(**template, **models))
            created += 1
            log.info("  + %s", template["name"])
        await session.commit()
        log.info(
            "Seeded %d supervisor template(s); re-pointed %d.", created, updated
        )


if __name__ == "__main__":
    asyncio.run(seed())
