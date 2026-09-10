# Architecture note

## The shape of the problem

An order supervisor is a process that is *mostly idle* and *occasionally
urgent*, over a horizon of days. That combination is what drives every decision
here:

- It must survive process restarts, deploys and crashes without losing where it
  was — so state lives in a durable workflow, not in a scheduler row or a cron job.
- It must not spend inference on a routine progress ping — so a cheap gate sits
  in front of the expensive agent.
- It must not accumulate unbounded context over a week — so memory is a rewritten
  rolling summary, not a transcript.
- It must not stop supervising because one model call failed — so every LLM path
  has a deterministic fallback.

## Component map

```
┌────────────┐   HTTP    ┌────────────┐  signal/query  ┌──────────────────┐
│  Next.js   │ ────────► │  FastAPI   │ ─────────────► │ Temporal Server  │
│  (SWR)     │ ◄──────── │            │ ◄───────────── │                  │
└────────────┘   JSON    └────────────┘   live state   └──────────────────┘
                              │                                 │ task queue
                              │ read projection                 ▼
                              ▼                        ┌──────────────────┐
                        ┌──────────┐    writes         │  Worker process  │
                        │ Postgres │ ◄──────────────── │ workflow + acts  │
                        └──────────┘                   └──────────────────┘
                                                                │
                                                                ▼
                                                 Gemini 3.5 Flash (agent)
                                                 Gemini 3.5 Flash Lite (gate)
```

Two backend processes share one codebase. **FastAPI** never runs agent logic —
it starts workflows, sends signals, and reads state. **The worker** hosts the
workflow and every activity. A ten-minute agent turn therefore cannot block an
HTTP request, and the two scale and restart independently.

## Temporal usage

**One workflow per order, id = `order-supervisor::<order_id>`.** Temporal
rejects a duplicate start while one is running, so the "exactly one supervisor
per order" invariant is enforced by the orchestrator rather than by application
locking.

**The workflow is blocked, not spinning.** Its entire life is:

```python
while True:
    if lifecycle_completion_reason(): finalize(); return
    trigger = await sleep_until_something_happens()   # signal OR timer
    drain_instructions()
    should_run = process_pending_events()             # the wake gate
    if paused: continue
    if should_run: await agent_turn(trigger)
    if should_continue_as_new(): roll_over()
```

`workflow.wait_condition(predicate, timeout=…)` is the single primitive doing
the sleep/wake work: it returns when a signal mutates state *or* when the timer
fires, whichever comes first. Sleeping for six hours costs a Temporal timer, not
a held thread.

**Signals** — `submit_event`, `add_instruction`, `control` (pause/resume/
interrupt/terminate). Handlers only mutate state; classification and reasoning
happen on the main loop, so there is exactly one writer and event ordering is
deterministic.

**Query** — `get_state` returns the authoritative live view: status, next
wake-up, memory, pending events, instructions. The UI merges this with the
Postgres projection, which is what keeps *completed* runs and the runs list
queryable in plain SQL after the workflow is gone.

**Activities** wrap every side effect: LLM calls, DB writes, tool execution.
Each has its own timeout and retry policy — 30s for DB, 90s for the gate, 10min
for an agent turn.

**`continue_as_new`** fires when Temporal signals history is growing (or every
40 turns), carrying memory, instructions, counters, both event queues and the
**original** `started_at` forward — so a rollover never resets the max-run-age
clock.

### Two determinism decisions worth naming

Workflow code is replayed, so it holds no I/O, no `datetime.now()`, no
`uuid4()`. `workflow.now()` and `workflow.uuid4()` are the only sources of time
and randomness. Putting `workflows/` in a different directory from
`activities/` makes that constraint structural rather than a comment someone
might not read.

The turn id comes from `workflow.uuid4()` and is passed *into* the activity,
where it becomes the idempotency key for every row that turn writes
(`{run_id}:{turn_id}:{tool_use_id}`). Because that value is stable across
replays and retries, a retried activity **updates** its rows instead of sending
the customer a second apology. This is the main correctness hazard in an
at-least-once execution model, and it is handled at the data layer rather than
hoped away.

## Agent orchestration

### Two tiers

| | Model | Runs |
|---|---|---|
| Wake gate | `gemini-3.5-flash-lite` | at most once per event, ~300 output tokens |
| Supervisor | `gemini-3.5-flash` | only when the gate (or a timer) says so |

Most events never reach the second tier. Rules resolve terminal, known-critical,
known-benign and unknown events with **no model call at all**; the classifier is
the fallback for the genuinely ambiguous middle. The run header reports the
suppression rate, which is a direct readout of inference avoided.

### One turn

Context assembled → reason → 0..n tool calls → mandatory `record_turn_outcome`
→ memory rewritten → next wake-up set → sleep.

The loop is driven by hand rather than the SDK's tool runner for two concrete
reasons: every tool call must be persisted with a workflow-derived idempotency
key, and the loop needs a hard iteration budget so one turn can never run away
inside a Temporal activity. Both are easier to guarantee when you own the loop.

`record_turn_outcome` is a tool rather than a parsed text convention, which
means the sleep interval, the rewritten memory and the completion
recommendation arrive as schema-validated arguments (`strict: true`) instead of
something to regex out of prose. If the model somehow ends a turn without
calling it, a safe default is substituted rather than losing the turn.

### Prompt construction

The stable prefix — role, base instruction, order context, tool definitions — is
identical on every wake-up and carries the cache breakpoint. Volatile content —
the event batch, elapsed time, trigger — comes after it. Over a week-long run
that is the difference between paying full price for the preamble on every wake
and paying for it once.

### Failure behaviour

Every LLM path degrades instead of failing:

- Gate call fails → deterministic policy, **fails open** (wake rather than
  silently sleep through something).
- Agent turn fails → logged to the timeline, deterministic policy takes the
  turn, the run continues.
- Final report fails → report derived from the activity log.
- A model refusal or a transport error → the deterministic policy takes the
  turn, so one bad call cannot strand a multi-day workflow.

The same fallback policy is what runs in mock mode, so a no-API-key install
exercises the identical tool path, timeline, memory and reports. The demo is
reproducible without credentials, and the fallback is continuously exercised
rather than being untested code that only runs during an incident.

## Memory and timeline

Two structures, deliberately separate:

- **`activities`** — the append-only unified log. Events, gate decisions, agent
  turns, business actions, sleep decisions, instructions, controls, final
  output. One table, ordered by a per-run `seq` because wall-clock timestamps
  collide when a turn writes several rows in the same millisecond. This is the
  audit trail and the UI's timeline.
- **`run_memory`** — one row, rewritten every turn. The rolling summary, key
  facts, open issues, and agent-authored wake guidance. This is what the *model*
  sees.

Compaction is the watermark between them. The prompt carries the summary plus
the tail after `compacted_through_seq`; once that tail exceeds a threshold the
watermark advances and older entries stop being sent. Prompt size stays bounded
no matter how long the order runs, and nothing is lost — the full history is
still in Postgres for a human.

The agent is told explicitly that the summary *replaces* the previous one and
that anything omitted is forgotten. That framing matters: a model that thinks it
is appending will write deltas that make no sense on their own three turns later.

## Completion is a workflow rule, not a model decision

The agent may set `recommend_completion`; it is written to the timeline as
advisory and then ignored by the control flow. Only a terminal order event, an
operator terminate, or max run age ends the workflow.

This is the one place where refusing to trust the model is the whole design.
Order lifecycle is a business fact, not a judgement call — and "the agent
decided the order was finished" is not an acceptable reason for a supervisor to
stop watching a live order. A terminated run still generates its report on the
way out, so the operator never loses the analysis by stopping the run.

## Data model

| Table | |
|---|---|
| `supervisors` | templates: instruction, tool allowlist, wake policy, model config |
| `runs` | one per order; status, live sleep state, counters, completion reason |
| `activities` | the unified log; unique `idempotency_key` |
| `run_memory` | rolling summary, wake guidance, compaction watermark |
| `run_instructions` | operator guidance added mid-run |
| `run_outputs` | final summary, actions, learnings, recommendations, stats |

`runs.supervisor_snapshot` freezes the template at start, so editing a template
never rewrites how a historical run is interpreted.

Status and kind columns are `VARCHAR`, not Postgres `ENUM`s — values are
validated by `StrEnum`s in `app/domain/enums.py`. Adding a new activity kind is
then a code change rather than a migration containing `ALTER TYPE`.

## Frontend

Polling, not WebSockets. Temporal queries are pull-only, so a socket layer would
just wrap a poll the server still has to perform — while adding reconnect
handling and cross-worker fanout. SWR's stale-while-revalidate is what makes the
poll usable: the timeline keeps its data on screen and grows a row, instead of
flashing a spinner every two seconds.

The poll interval is derived from run status — 1.5s while the agent is running,
3s asleep, 5s paused, and **stopped entirely** once terminal. Mutations call
`mutate()` so the UI reacts on click rather than on the next tick.

## What was cut, and why

- **No LangChain/LangGraph.** Temporal already owns state, retries, durability
  and scheduling. A second orchestration framework would duplicate all four and
  fight the first over which one owns control flow.
- **No vector store.** Memory here is one bounded summary per order. Retrieval
  would be machinery without a question to answer.
- **No auth, no multi-tenancy.** Explicitly out of scope.
- **Single-writer timeline.** The API signals; only the workflow writes. Slightly
  more indirection, but event ordering is deterministic and a signal delivered
  while the worker is down is still processed once it returns.

## Known limits

- The gate is per-event, so a burst of ten events costs ten small calls. Batching
  them into one gate call would be the next optimisation.
- `sync_run_state` writes the projection on every state change; at high run
  counts that would want batching or a change-feed.
- `max_concurrent_activities=20` per worker is a POC number, not a tuned one.
- Compaction drops old entries from the prompt rather than summarising them
  separately. A second-tier "archive summary" would preserve more nuance on runs
  lasting weeks.
