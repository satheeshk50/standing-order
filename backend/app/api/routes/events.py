"""Event ingestion — the backend half of the event generator."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domain.enums import ALWAYS_WAKE_EVENTS, TERMINAL_EVENTS, RunStatus
from app.domain.events import EVENT_CATALOG
from app.repositories import run_repo
from app.schemas.event import EventCatalogEntry, EventCreate
from app.temporal.client import get_client
from app.temporal.shared import IncomingEvent

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/event-catalog", response_model=list[EventCatalogEntry])
async def event_catalog():
    """Drives the event-injection panel in the UI."""
    return [
        EventCatalogEntry(
            event_type=event_type,
            label=spec["label"],
            default_payload=spec["default_payload"],
            is_terminal=event_type in TERMINAL_EVENTS,
            always_wakes=event_type in ALWAYS_WAKE_EVENTS,
        )
        for event_type, spec in EVENT_CATALOG.items()
    ]


@router.post("/runs/{run_id}/events", status_code=202)
async def submit_event(
    run_id: str, body: EventCreate, session: AsyncSession = Depends(get_session)
):
    """Deliver an order event into the running workflow as a Temporal signal.

    The API does not classify or persist the event itself — it hands it to the
    workflow, which owns ingestion ordering. That keeps a single writer for the
    timeline and means a signal delivered while the worker is down is still
    processed once the worker returns.
    """
    run = await run_repo.get(session, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if RunStatus(run.status).is_terminal:
        raise HTTPException(409, f"Run is {run.status}; it no longer accepts events.")

    event = IncomingEvent(
        event_id=str(uuid.uuid4()),
        event_type=body.event_type,
        payload=body.payload,
        source=body.source,
    )
    handle = (await get_client()).get_workflow_handle(run.workflow_id)
    await handle.signal("submit_event", event)
    return {
        "status": "accepted",
        "event_id": event.event_id,
        "event_type": event.event_type,
    }


@router.post("/orders/{order_id}/events", status_code=202)
async def submit_event_by_order(
    order_id: str, body: EventCreate, session: AsyncSession = Depends(get_session)
):
    """Same as above, addressed by business key — handy for the simulator."""
    run = await run_repo.get_by_order(session, order_id)
    if run is None:
        raise HTTPException(404, f"No run for order '{order_id}'")
    return await submit_event(run.id, body, session)
