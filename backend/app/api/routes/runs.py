"""Run management: create, inspect, instruct, control."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.service import RPCError

from app.db.session import get_session
from app.domain.enums import ActivityKind, Actor, Importance, RunStatus
from app.repositories import activity_repo, memory_repo, run_repo, supervisor_repo
from app.schemas.run import (
    ActivityOut,
    ControlRequest,
    InstructionCreate,
    LiveState,
    MemoryOut,
    OutputOut,
    RunCreate,
    RunDetail,
    RunSummary,
)
from app.temporal.client import get_client, workflow_id_for
from app.temporal.shared import (
    ControlSignal,
    IncomingEvent,
    IncomingInstruction,
    RunParams,
    SupervisorConfig,
    WorkflowStateView,
)
from app.config import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/runs", tags=["runs"])


def _config_from(supervisor) -> SupervisorConfig:
    return SupervisorConfig(
        supervisor_id=supervisor.id,
        name=supervisor.name,
        base_instruction=supervisor.base_instruction,
        allowed_actions=list(supervisor.allowed_actions or []),
        default_wake_seconds=supervisor.default_wake_seconds,
        max_run_age_seconds=supervisor.max_run_age_seconds,
        wake_aggressiveness=supervisor.wake_aggressiveness,
        wake_guidance=supervisor.wake_guidance,
        model=supervisor.model,
        classifier_model=supervisor.classifier_model,
        effort=supervisor.effort,
    )


@router.post("", response_model=RunDetail, status_code=201)
async def create_run(body: RunCreate, session: AsyncSession = Depends(get_session)):
    """Start a supervisor workflow for one order."""
    if await run_repo.get_by_order(session, body.order_id):
        raise HTTPException(409, f"Order '{body.order_id}' already has a run.")

    supervisor = (
        await supervisor_repo.get(session, body.supervisor_id)
        if body.supervisor_id
        else await supervisor_repo.get_default(session)
    )
    if supervisor is None:
        raise HTTPException(
            400, "No supervisor template found. Seed one via POST /api/supervisors."
        )

    config = _config_from(supervisor)
    workflow_id = workflow_id_for(body.order_id)

    run = await run_repo.create(
        session,
        supervisor_id=supervisor.id,
        order_id=body.order_id,
        workflow_id=workflow_id,
        status=RunStatus.PENDING,
        order_context=body.order_context,
        supervisor_snapshot=config.__dict__,
    )
    await memory_repo.ensure(session, run.id)

    client = await get_client()
    handle = await client.start_workflow(
        "OrderSupervisorWorkflow",
        RunParams(
            run_id=run.id,
            order_id=body.order_id,
            order_context=body.order_context,
            config=config,
        ),
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )
    await run_repo.update(
        session, run.id, temporal_run_id=handle.result_run_id, status=RunStatus.RUNNING
    )

    if body.seed_order_created_event:
        await handle.signal(
            "submit_event",
            IncomingEvent(
                event_id=str(uuid.uuid4()),
                event_type="order_created",
                payload={"note": "Order placed", **body.order_context},
                source="api",
            ),
        )

    return await _build_detail(session, run.id)


@router.get("", response_model=list[RunSummary])
async def list_runs(
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    return await run_repo.list_runs(session, status=status)


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)):
    detail = await _build_detail(session, run_id)
    if detail is None:
        raise HTTPException(404, "Run not found")
    return detail


@router.post("/{run_id}/instructions", status_code=202)
async def add_instruction(
    run_id: str,
    body: InstructionCreate,
    session: AsyncSession = Depends(get_session),
):
    """Add run-specific guidance to a workflow that is already running."""
    run = await _require_active(session, run_id)
    row = await run_repo.add_instruction(
        session, run_id, body.text, urgent=body.urgent
    )
    handle = (await get_client()).get_workflow_handle(run.workflow_id)
    await handle.signal(
        "add_instruction",
        IncomingInstruction(
            instruction_id=row.id, text=body.text, urgent=body.urgent
        ),
    )
    return {"status": "accepted", "instruction_id": row.id, "urgent": body.urgent}


async def _control(
    session: AsyncSession, run_id: str, action: str, reason: str | None, title: str
):
    run = await _require_active(session, run_id)
    handle = (await get_client()).get_workflow_handle(run.workflow_id)
    await handle.signal("control", ControlSignal(action=action, reason=reason))
    await activity_repo.log(
        session,
        run_id=run_id,
        kind=ActivityKind.CONTROL,
        title=title,
        body=reason,
        payload={"action": action},
        actor=Actor.USER,
        importance=Importance.HIGH,
    )
    return {"status": "accepted", "action": action}


@router.post("/{run_id}/pause", status_code=202)
async def pause_run(
    run_id: str, body: ControlRequest, session: AsyncSession = Depends(get_session)
):
    """Stop spending inference. Events keep queueing on the workflow."""
    return await _control(session, run_id, "pause", body.reason, "Run paused")


@router.post("/{run_id}/resume", status_code=202)
async def resume_run(
    run_id: str, body: ControlRequest, session: AsyncSession = Depends(get_session)
):
    return await _control(session, run_id, "resume", body.reason, "Run resumed")


@router.post("/{run_id}/interrupt", status_code=202)
async def interrupt_run(
    run_id: str, body: ControlRequest, session: AsyncSession = Depends(get_session)
):
    """Force an agent turn immediately, without waiting for the wake timer."""
    return await _control(
        session, run_id, "interrupt", body.reason, "Run interrupted — forcing a turn"
    )


@router.post("/{run_id}/terminate", status_code=202)
async def terminate_run(
    run_id: str, body: ControlRequest, session: AsyncSession = Depends(get_session)
):
    """Graceful stop: the workflow still produces its final report first."""
    return await _control(
        session,
        run_id,
        "terminate",
        body.reason or "Terminated from the UI",
        "Run termination requested",
    )


# --------------------------------------------------------------------------


async def _require_active(session: AsyncSession, run_id: str):
    run = await run_repo.get(session, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if RunStatus(run.status).is_terminal:
        raise HTTPException(409, f"Run is already {run.status}.")
    return run


async def _build_detail(session: AsyncSession, run_id: str) -> RunDetail | None:
    run = await run_repo.get(session, run_id)
    if run is None:
        return None

    activities = await activity_repo.list_for_run(session, run_id)
    memory = await memory_repo.get(session, run_id)
    output = await run_repo.get_output(session, run_id)
    instructions = await run_repo.list_instructions(session, run_id)

    live: LiveState | None = None
    if not RunStatus(run.status).is_terminal:
        # Query the workflow itself — it holds the authoritative live state.
        try:
            handle = (await get_client()).get_workflow_handle(run.workflow_id)
            # result_type is required, otherwise the SDK hands back raw JSON
            # instead of decoding into the dataclass.
            state = await handle.query("get_state", result_type=WorkflowStateView)
            live = LiveState(
                status=state.status,
                paused=state.paused,
                awake=state.awake,
                next_wake_at=state.next_wake_at_iso,
                sleep_reason=state.sleep_reason,
                memory_summary=state.memory_summary,
                wake_guidance=state.wake_guidance,
                instructions=state.instructions,
                pending_event_count=state.pending_event_count,
                turn_count=state.turn_count,
                generation=state.generation,
                last_trigger=state.last_trigger,
            )
        except (RPCError, RuntimeError) as exc:
            log.debug("live query unavailable for %s: %s", run_id, exc)

    return RunDetail(
        **{
            **{
                key: getattr(run, key)
                for key in RunSummary.model_fields
                if hasattr(run, key)
            },
            "order_context": run.order_context,
            "supervisor_snapshot": run.supervisor_snapshot,
            "sleep_reason": run.sleep_reason,
            "instructions": [i.text for i in instructions],
            "live": live,
            "memory": MemoryOut.model_validate(memory) if memory else None,
            "output": OutputOut.model_validate(output) if output else None,
            "activities": [ActivityOut.model_validate(a) for a in activities],
        }
    )
