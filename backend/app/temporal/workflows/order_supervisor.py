"""The long-running supervisor workflow — one run per order.

Design notes
------------
* The workflow is **blocked, not spinning**. It parks in
  ``workflow.wait_condition`` and is released either by a signal or by the
  sleep timer expiring. There is no polling loop and no busy wait.

* Three inference triggers, exactly as the brief requires:
  ``workflow_start``, ``signal`` (an event the classifier judged important),
  and ``scheduled_wakeup``. Operator ``interrupt`` and urgent instructions are
  additional, explicitly-requested triggers.

* Every incoming event passes the cheap wake gate first. Unimportant events are
  recorded on the timeline and batched for the next scheduled turn — they do
  not spend a main-agent inference.

* **Completion is workflow-owned.** The agent can set ``recommend_completion``
  but only these end the run: a terminal order event, an operator terminate,
  or the configured max run age. That rule lives here, not in the prompt.

* This module runs inside Temporal's sandbox, so it contains no I/O and no
  wall-clock reads. ``workflow.now()`` and ``workflow.uuid4()`` are the only
  sources of time and randomness.
"""

import asyncio
from dataclasses import asdict
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.domain.enums import (
        ActivityKind,
        Actor,
        Importance,
        RunStatus,
        TriggerReason,
    )
    from app.temporal.shared import (
        AgentTurnInput,
        AgentTurnResult,
        ClassifyInput,
        ClassifyResult,
        ControlSignal,
        FinalizeInput,
        FinalizeResult,
        IncomingEvent,
        IncomingInstruction,
        LogActivityInput,
        RunParams,
        RunStateSync,
        WorkflowCarryOver,
        WorkflowStateView,
    )

# --- Activity timeouts / retries -----------------------------------------

DB_OPTS = dict(
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=RetryPolicy(maximum_attempts=5, initial_interval=timedelta(seconds=1)),
)
CLASSIFY_OPTS = dict(
    start_to_close_timeout=timedelta(seconds=90),
    retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=2)),
)
AGENT_OPTS = dict(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5)),
)

#: Never sleep longer than this in one hop; keeps the UI's "next wake-up"
#: honest and gives the max-age rule a chance to fire on schedule.
MAX_SLEEP = timedelta(hours=6)
MIN_SLEEP = timedelta(seconds=5)


@workflow.defn(name="OrderSupervisorWorkflow")
class OrderSupervisorWorkflow:
    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    def __init__(self) -> None:
        self._params: RunParams | None = None
        #: Inbox — raw events delivered by signal, not yet through the gate.
        self._pending_events: list[IncomingEvent] = []
        #: Events that have been through the gate but not yet shown to the
        #: agent. Suppressed events land here too: the gate decides whether to
        #: *wake* for them, not whether the agent ever sees them. They are
        #: handed over in a batch on the next turn, whatever triggers it.
        self._unprocessed_events: list[IncomingEvent] = []
        self._pending_instructions: list[IncomingInstruction] = []
        self._instructions: list[str] = []

        self._paused = False
        self._interrupt_requested = False
        self._terminate_requested: str | None = None

        self._status: str = RunStatus.PENDING
        self._awake = False
        self._next_wake_at = None
        self._sleep_reason = ""
        self._last_trigger = ""

        self._memory_summary = ""
        self._wake_guidance: str | None = None
        self._compacted_through_seq = 0

        self._turn_count = 0
        self._event_count = 0
        self._action_count = 0
        self._wake_count = 0
        self._suppressed_event_count = 0
        self._generation = 0

        self._started_at = None
        self._completion_reason: str | None = None
        #: Set by the wake gate when a terminal order event arrives.
        self._terminal_event: str | None = None

    # ------------------------------------------------------------------
    # Signals — events, instructions, and operator controls
    # ------------------------------------------------------------------
    @workflow.signal
    async def submit_event(self, event: IncomingEvent) -> None:
        """An order event. Queued here; classified by the main loop."""
        self._pending_events.append(event)

    @workflow.signal
    async def add_instruction(self, instruction: IncomingInstruction) -> None:
        """Run-specific guidance added after the workflow already started."""
        self._pending_instructions.append(instruction)

    @workflow.signal
    async def control(self, signal: ControlSignal) -> None:
        action = signal.action
        if action == "pause":
            self._paused = True
        elif action == "resume":
            self._paused = False
        elif action == "interrupt":
            self._interrupt_requested = True
        elif action == "terminate":
            self._terminate_requested = signal.reason or "operator_terminated"

    # ------------------------------------------------------------------
    # Query — the UI reads live state straight out of the workflow
    # ------------------------------------------------------------------
    @workflow.query
    def get_state(self) -> WorkflowStateView:
        params = self._params
        return WorkflowStateView(
            run_id=params.run_id if params else "",
            order_id=params.order_id if params else "",
            status=self._status,
            paused=self._paused,
            awake=self._awake,
            next_wake_at_iso=(
                self._next_wake_at.isoformat() if self._next_wake_at else None
            ),
            sleep_reason=self._sleep_reason,
            memory_summary=self._memory_summary,
            wake_guidance=self._wake_guidance,
            instructions=list(self._instructions),
            pending_event_count=len(self._pending_events)
            + len(self._unprocessed_events),
            turn_count=self._turn_count,
            event_count=self._event_count,
            action_count=self._action_count,
            wake_count=self._wake_count,
            suppressed_event_count=self._suppressed_event_count,
            generation=self._generation,
            started_at_iso=self._started_at.isoformat() if self._started_at else None,
            last_trigger=self._last_trigger,
            completion_reason=self._completion_reason,
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    @workflow.run
    async def run(self, params: RunParams) -> dict:
        self._params = params
        carry = params.carry_over

        if carry:
            # Resumed via continue_as_new — restore, do not re-initialise.
            self._memory_summary = carry.memory_summary
            self._wake_guidance = carry.wake_guidance
            self._instructions = list(carry.instructions)
            self._turn_count = carry.turn_count
            self._event_count = carry.event_count
            self._action_count = carry.action_count
            self._wake_count = carry.wake_count
            self._suppressed_event_count = carry.suppressed_event_count
            self._compacted_through_seq = carry.compacted_through_seq
            self._generation = carry.generation
            self._paused = carry.paused
            self._pending_events = [IncomingEvent(**e) for e in carry.pending_events]
            self._unprocessed_events = [
                IncomingEvent(**e) for e in carry.unprocessed_events
            ]
            # Age is measured from the ORIGINAL start, not this generation's,
            # so continue_as_new never resets the max-run-age clock.
            self._started_at = _parse_iso(carry.started_at_iso) or workflow.now()
        else:
            self._started_at = workflow.now()
            self._wake_guidance = params.config.wake_guidance

        await self._sync(RunStatus.RUNNING)

        if not carry:
            await self._log(
                ActivityKind.SYSTEM,
                f"Supervisor started for order {params.order_id}",
                body=params.config.base_instruction,
                payload={
                    "supervisor": params.config.name,
                    "order_context": params.order_context,
                    "model": params.config.model,
                    "classifier_model": params.config.classifier_model,
                },
                importance=Importance.HIGH,
                idempotency_key=f"{params.run_id}:start",
            )
            # Give the caller's seed event (usually order_created, signalled
            # immediately after start) a moment to land, so the very first turn
            # has something concrete to reason about instead of running blind
            # and then immediately running again.
            try:
                await workflow.wait_condition(
                    lambda: bool(self._pending_events), timeout=timedelta(seconds=3)
                )
                await self._process_pending_events()
            except asyncio.TimeoutError:
                pass

            # Trigger 1 of 3 — workflow start.
            await self._agent_turn(TriggerReason.WORKFLOW_START, "Workflow started")
        else:
            await self._log(
                ActivityKind.SYSTEM,
                f"Workflow continued as new (generation {self._generation})",
                body="History was rolled over to keep Temporal history bounded. "
                "Memory, instructions and counters were carried forward.",
                payload={"generation": self._generation},
                idempotency_key=f"{params.run_id}:can:{self._generation}",
            )

        # ---------------- main sleep / wake loop ----------------
        while True:
            reason = self._lifecycle_completion_reason()
            if reason:
                return await self._finalize(reason)

            trigger, detail = await self._sleep_until_something_happens()

            reason = self._lifecycle_completion_reason()
            if reason:
                return await self._finalize(reason)

            await self._drain_instructions()

            should_run, run_detail = await self._process_pending_events()
            if trigger in (
                TriggerReason.SCHEDULED_WAKEUP,
                TriggerReason.INTERRUPT,
                TriggerReason.INSTRUCTION,
            ):
                should_run = True
                run_detail = detail if not run_detail else f"{detail}; {run_detail}"

            if self._terminal_event:
                should_run = True
                run_detail = (
                    f"Terminal order event received: {self._terminal_event}"
                )

            if self._paused:
                # Operator halted the agent. Events keep queuing; we simply
                # do not spend inference until resume.
                await self._sync(RunStatus.PAUSED)
                continue

            if should_run:
                await self._agent_turn(trigger, run_detail)

            if self._should_continue_as_new():
                await self._roll_over()  # does not return

    # ------------------------------------------------------------------
    # Sleeping
    # ------------------------------------------------------------------
    async def _sleep_until_something_happens(self) -> tuple[str, str]:
        """Park until a signal arrives or the wake timer fires.

        Returns the trigger that released us and a human-readable detail.
        """
        self._awake = False
        now = workflow.now()

        if self._paused:
            self._status = RunStatus.PAUSED
            self._sleep_reason = "Paused by operator"
            self._next_wake_at = None
            await self._sync(RunStatus.PAUSED)
            await workflow.wait_condition(
                lambda: not self._paused or self._terminate_requested is not None
            )
            self._awake = True
            return TriggerReason.INTERRUPT, "Resumed by operator"

        target = self._next_wake_at or (now + timedelta(seconds=60))
        # Never overshoot the max-age deadline.
        deadline = self._max_age_deadline()
        if deadline and target > deadline:
            target = deadline
        timeout = target - now
        if timeout > MAX_SLEEP:
            timeout = MAX_SLEEP
        if timeout < MIN_SLEEP:
            timeout = MIN_SLEEP

        self._status = RunStatus.SLEEPING
        self._next_wake_at = now + timeout
        await self._sync(RunStatus.SLEEPING)

        try:
            await workflow.wait_condition(self._has_work, timeout=timeout)
        except asyncio.TimeoutError:
            self._awake = True
            self._wake_count += 1
            self._last_trigger = TriggerReason.SCHEDULED_WAKEUP
            await self._log(
                ActivityKind.WAKE,
                "Woke on schedule",
                body="Scheduled review timer expired.",
                payload={"trigger": TriggerReason.SCHEDULED_WAKEUP},
            )
            # Trigger 3 of 3 — scheduled wake-up.
            return TriggerReason.SCHEDULED_WAKEUP, "Scheduled review"

        self._awake = True
        self._wake_count += 1

        if self._terminate_requested:
            self._last_trigger = "terminate"
            return TriggerReason.INTERRUPT, "Terminate requested"
        if self._interrupt_requested:
            self._interrupt_requested = False
            self._last_trigger = TriggerReason.INTERRUPT
            await self._log(
                ActivityKind.CONTROL,
                "Interrupted by operator",
                body="Operator forced an immediate agent turn.",
                actor=Actor.USER,
                importance=Importance.HIGH,
            )
            return TriggerReason.INTERRUPT, "Operator interrupt"
        if any(i.urgent for i in self._pending_instructions):
            self._last_trigger = TriggerReason.INSTRUCTION
            return TriggerReason.INSTRUCTION, "Urgent instruction added"
        if self._pending_events:
            self._last_trigger = TriggerReason.SIGNAL
            # Trigger 2 of 3 — incoming signal (subject to the wake gate).
            return TriggerReason.SIGNAL, "Incoming event"

        self._last_trigger = TriggerReason.INSTRUCTION
        return TriggerReason.INSTRUCTION, "Instruction added"

    def _has_work(self) -> bool:
        return bool(
            self._pending_events
            or self._pending_instructions
            or self._interrupt_requested
            or self._terminate_requested
            or self._paused
        )

    # ------------------------------------------------------------------
    # Event ingestion + the wake gate
    # ------------------------------------------------------------------
    async def _process_pending_events(self) -> tuple[bool, str]:
        """Classify every queued event; report whether the agent should run."""
        if not self._pending_events:
            return False, ""

        batch, self._pending_events = self._pending_events, []
        should_wake = False
        reasons: list[str] = []

        for event in batch:
            self._event_count += 1
            decision: ClassifyResult = await workflow.execute_activity(
                "classify_event",
                ClassifyInput(
                    run_id=self._params.run_id,
                    event=event,
                    config=self._params.config,
                    wake_guidance=self._wake_guidance,
                    memory_summary=self._memory_summary,
                    seconds_since_last_turn=self._seconds_since_start(),
                    is_asleep=not self._awake,
                ),
                # result_type is required for the SDK to decode the payload
                # into the dataclass instead of handing back a raw dict.
                result_type=ClassifyResult,
                **CLASSIFY_OPTS,
            )

            if decision.is_terminal_event:
                self._terminal_event = event.event_type

            # Queued for the agent either way — a suppressed event is deferred,
            # not dropped.
            self._unprocessed_events.append(event)

            if decision.wake:
                should_wake = True
                reasons.append(f"{event.event_type}: {decision.reason}")
            else:
                self._suppressed_event_count += 1

        return should_wake, "; ".join(reasons)

    async def _drain_instructions(self) -> None:
        while self._pending_instructions:
            instruction = self._pending_instructions.pop(0)
            self._instructions.append(instruction.text)
            await self._log(
                ActivityKind.INSTRUCTION_ADDED,
                "Run instruction added",
                body=instruction.text,
                actor=Actor.USER,
                importance=Importance.HIGH,
                payload={"urgent": instruction.urgent},
                idempotency_key=f"{self._params.run_id}:instr:{instruction.instruction_id}",
            )

    # ------------------------------------------------------------------
    # Agent turn
    # ------------------------------------------------------------------
    async def _agent_turn(self, trigger: str, detail: str) -> None:
        self._status = RunStatus.RUNNING
        self._awake = True
        await self._sync(RunStatus.RUNNING)

        turn_id = str(workflow.uuid4())
        # Hand over everything the gate has cleared since the last turn —
        # including events it judged unimportant enough to sleep through.
        pending, self._unprocessed_events = self._unprocessed_events, []

        result: AgentTurnResult = await workflow.execute_activity(
            "run_agent_turn",
            AgentTurnInput(
                run_id=self._params.run_id,
                turn_id=turn_id,
                order_id=self._params.order_id,
                order_context=self._params.order_context,
                config=self._params.config,
                trigger=trigger,
                trigger_detail=detail,
                memory_summary=self._memory_summary,
                wake_guidance=self._wake_guidance,
                instructions=list(self._instructions),
                pending_events=pending,
                compacted_through_seq=self._compacted_through_seq,
                run_age_seconds=self._seconds_since_start(),
                seconds_until_max_age=self._seconds_until_max_age(),
                turn_count=self._turn_count,
            ),
            result_type=AgentTurnResult,
            **AGENT_OPTS,
        )

        self._turn_count += 1
        self._action_count += len(result.actions)
        if result.memory_summary:
            self._memory_summary = result.memory_summary
        if result.wake_guidance:
            self._wake_guidance = result.wake_guidance
        if result.compacted:
            self._compacted_through_seq = result.compacted_through_seq

        # The agent proposes a sleep duration; the workflow bounds it.
        seconds = max(int(result.sleep_seconds or 0), 5)
        sleep_for = timedelta(seconds=seconds)
        if sleep_for > MAX_SLEEP:
            sleep_for = MAX_SLEEP
        self._next_wake_at = workflow.now() + sleep_for
        self._sleep_reason = result.sleep_reason or "Routine review"

        await self._log(
            ActivityKind.SLEEP_SCHEDULED,
            f"Sleeping for {_humanize(sleep_for)}",
            body=self._sleep_reason,
            payload={
                "sleep_seconds": int(sleep_for.total_seconds()),
                "next_wake_at": self._next_wake_at.isoformat(),
                "recommend_completion": result.recommend_completion,
            },
            actor=Actor.AGENT,
        )

        if result.recommend_completion:
            # Recorded, but NOT acted on — completion is workflow-owned.
            await self._log(
                ActivityKind.AGENT_TURN,
                "Agent recommends completing the run",
                body=result.completion_rationale
                or "Agent believes the order lifecycle is finished.",
                payload={"advisory_only": True},
                actor=Actor.AGENT,
                importance=Importance.HIGH,
            )

        await self._sync(RunStatus.SLEEPING)

    # ------------------------------------------------------------------
    # Completion — workflow-owned rules only
    # ------------------------------------------------------------------
    def _lifecycle_completion_reason(self) -> str | None:
        if self._terminate_requested:
            return f"operator_terminated:{self._terminate_requested}"
        if self._terminal_event:
            return f"terminal_event:{self._terminal_event}"
        deadline = self._max_age_deadline()
        if deadline and workflow.now() >= deadline:
            return "max_run_age_reached"
        return None

    async def _finalize(self, reason: str) -> dict:
        self._completion_reason = reason
        terminated = reason.startswith("operator_terminated")
        final_status = RunStatus.TERMINATED if terminated else RunStatus.COMPLETED
        self._status = RunStatus.RUNNING
        self._next_wake_at = None
        self._sleep_reason = ""
        await self._sync(RunStatus.RUNNING)

        await self._log(
            ActivityKind.SYSTEM,
            f"Run ending — {reason}",
            body="Completion rule fired. Generating the final report.",
            importance=Importance.HIGH,
            idempotency_key=f"{self._params.run_id}:ending",
        )

        stats = {
            "turns": self._turn_count,
            "events": self._event_count,
            "actions": self._action_count,
            "wakes": self._wake_count,
            "suppressed_events": self._suppressed_event_count,
            "generations": self._generation + 1,
            "run_age_seconds": self._seconds_since_start(),
        }

        # Final agent step: summary, learnings, feedback.
        await workflow.execute_activity(
            "finalize_run",
            FinalizeInput(
                run_id=self._params.run_id,
                order_id=self._params.order_id,
                order_context=self._params.order_context,
                config=self._params.config,
                memory_summary=self._memory_summary,
                instructions=list(self._instructions),
                completion_reason=reason,
                final_status=str(final_status),
                stats=stats,
            ),
            result_type=FinalizeResult,
            **AGENT_OPTS,
        )

        self._status = final_status
        self._awake = False
        await self._sync(
            final_status,
            completed_at_iso=workflow.now().isoformat(),
            completion_reason=reason,
        )
        return {
            "run_id": self._params.run_id,
            "order_id": self._params.order_id,
            "status": str(final_status),
            "completion_reason": reason,
            "stats": stats,
        }

    # ------------------------------------------------------------------
    # continue_as_new
    # ------------------------------------------------------------------
    def _should_continue_as_new(self) -> bool:
        """Roll over when Temporal says history is getting large, or every 40
        turns as a belt-and-braces fallback for very chatty orders."""
        if self._turn_count == 0 or self._terminal_event or self._terminate_requested:
            return False
        try:
            suggested = workflow.info().is_continue_as_new_suggested()
        except Exception:  # older server / SDK without the hint
            suggested = False
        return suggested or self._turn_count % 40 == 0

    async def _roll_over(self) -> None:
        carry = WorkflowCarryOver(
            memory_summary=self._memory_summary,
            wake_guidance=self._wake_guidance,
            instructions=list(self._instructions),
            turn_count=self._turn_count,
            event_count=self._event_count,
            action_count=self._action_count,
            wake_count=self._wake_count,
            suppressed_event_count=self._suppressed_event_count,
            compacted_through_seq=self._compacted_through_seq,
            started_at_iso=self._started_at.isoformat() if self._started_at else None,
            generation=self._generation + 1,
            pending_events=[asdict(e) for e in self._pending_events],
            unprocessed_events=[asdict(e) for e in self._unprocessed_events],
            paused=self._paused,
        )
        workflow.continue_as_new(
            RunParams(
                run_id=self._params.run_id,
                order_id=self._params.order_id,
                order_context=self._params.order_context,
                config=self._params.config,
                carry_over=carry,
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _max_age_deadline(self):
        if not self._started_at:
            return None
        max_age = self._params.config.max_run_age_seconds
        if not max_age or max_age <= 0:
            return None
        return self._started_at + timedelta(seconds=max_age)

    def _seconds_since_start(self) -> int:
        if not self._started_at:
            return 0
        return int((workflow.now() - self._started_at).total_seconds())

    def _seconds_until_max_age(self) -> int:
        deadline = self._max_age_deadline()
        if not deadline:
            return -1
        return max(int((deadline - workflow.now()).total_seconds()), 0)

    async def _log(
        self,
        kind: str,
        title: str,
        *,
        body: str | None = None,
        payload: dict | None = None,
        actor: str = Actor.SYSTEM,
        importance: str = Importance.NORMAL,
        idempotency_key: str | None = None,
    ) -> None:
        await workflow.execute_activity(
            "log_activity",
            LogActivityInput(
                run_id=self._params.run_id,
                kind=str(kind),
                title=title,
                body=body,
                payload=payload or {},
                actor=str(actor),
                importance=str(importance),
                idempotency_key=idempotency_key,
            ),
            **DB_OPTS,
        )

    async def _sync(
        self,
        status: str,
        *,
        completed_at_iso: str | None = None,
        completion_reason: str | None = None,
    ) -> None:
        self._status = str(status)
        await workflow.execute_activity(
            "sync_run_state",
            RunStateSync(
                run_id=self._params.run_id,
                status=str(status),
                next_wake_at_iso=(
                    self._next_wake_at.isoformat() if self._next_wake_at else None
                ),
                sleep_reason=self._sleep_reason,
                turn_count=self._turn_count,
                event_count=self._event_count,
                action_count=self._action_count,
                wake_count=self._wake_count,
                suppressed_event_count=self._suppressed_event_count,
                temporal_run_id=workflow.info().run_id,
                started_at_iso=(
                    self._started_at.isoformat() if self._started_at else None
                ),
                completed_at_iso=completed_at_iso,
                completion_reason=completion_reason,
            ),
            **DB_OPTS,
        )


def _parse_iso(value: str | None):
    if not value:
        return None
    from datetime import datetime

    return datetime.fromisoformat(value)


def _humanize(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds / 3600:.1f}h"
