# Order Supervisor

A long-running AI supervisor that oversees a single order from creation to
completion. One Temporal workflow per order. Events arrive as signals. The agent
wakes when something matters, acts through logged business actions, updates its
memory, decides when to sleep next — and produces a final report with learnings
when the run ends.

```
Next.js (Tailwind, SWR)  →  FastAPI  →  Temporal  →  worker
                                ↓          ↓           ↓
                            PostgreSQL ←───┴───────────┘
                                                  Gemini 3.5 Flash + Flash Lite
```

- **Architecture note:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **API docs:** http://localhost:8000/docs once running
- **Temporal UI:** http://localhost:8233 once running

> **Runs without an API key.** With no `GEMINI_API_KEY`, the system falls
> back to a deterministic policy that drives the *same* tools, timeline, memory
> and reports. Everything below works either way — the header pill in the UI
> tells you which mode you're in. Set a key to run the real models.

---

## Quick start

Prerequisites: **Python 3.12+**, **Node 20+**, **Docker**.

```bash
# 1 — infrastructure (Postgres :5432, Temporal :7233, Temporal UI :8233)
docker compose up -d postgres temporal

# 2 — configuration
cp .env.example .env          # works as-is; add GEMINI_API_KEY for live models

# 3 — backend
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS / Linux

.venv/Scripts/python.exe -m alembic upgrade head    # create the schema
.venv/Scripts/python.exe -m app.seed                # 3 supervisor templates
```

Now run **three processes**, each in its own terminal:

```bash
# terminal 1 — API
cd backend && python main.py

# terminal 2 — Temporal worker (hosts the workflow + activities)
cd backend && .venv/Scripts/python.exe -m app.worker

# terminal 3 — UI
cd frontend && npm install && npm run dev
```

Open **http://localhost:3000**.

### Or run everything in Docker

```bash
docker compose --profile full up --build
```

Migrations and seeding run automatically. UI on :3000, API on :8000.

### Makefile shortcuts

```
make infra     make migrate    make api      make demo
make install   make seed       make worker   make web
```

---

## Two-minute demo

1. **http://localhost:3000/supervisors** — three seeded templates. They differ in
   ways you can see: wake aggressiveness, sleep cadence, and tool allowlist
   (the hands-off template has no `message_customer` tool at all).
2. **Start a run** → `/runs/new`. Pick a template, keep the generated order id,
   hit *Start supervision*. A Temporal workflow starts with id
   `order-supervisor::<order_id>`.
3. **Watch the first turn.** The agent opens supervision, writes an internal
   note, records a memory summary, and schedules its next wake-up. The
   countdown in the header ticks down live.
4. **Inject events** from the right-hand panel:
   - `payment_confirmed` → the wake gate says **stay asleep** (routine).
   - `shipment_delayed` → the gate says **WAKE**; the agent messages the
     logistics team *and* the customer, then shortens its next sleep.
   - Send an event type that isn't in the catalog (edit the payload panel or use
     the script) → **unknown-event escalation**: it wakes and files a risk note.
5. **Add an instruction** mid-flight: *"Do not contact the customer without
   human review."* It joins the run context permanently.
6. **Pause** → events keep queuing but no inference runs. **Resume** → the
   backlog drains in one turn. **Interrupt** → forces a turn immediately.
7. **Finish**: send `delivered` (or hit *Terminate*). The workflow's completion
   rule fires, the agent writes the **final report** — summary, important
   actions, key learnings, recommendations — and the workflow closes.

### Scripted event generator

```bash
python scripts/simulate_order.py --list
python scripts/simulate_order.py --create ORD-9001 --scenario delayed_delivery
python scripts/simulate_order.py --scenario payment_trouble --speed 3
python scripts/simulate_order.py --run-id <uuid> --event shipment_delayed
```

Scenarios: `happy_path`, `delayed_delivery`, `payment_trouble`, `refund_journey`,
`stalled_order`, `unknown_event`.

The generator exists in all three forms the brief allows — a **UI panel**, a
**REST endpoint** (`POST /api/runs/{id}/events`), and this **script**. All three
take the identical path: HTTP → Temporal signal → wake gate.

---

## How it works

### The three inference triggers

| Trigger | What releases the workflow |
|---|---|
| `workflow_start` | The run begins. The agent forms its plan and sets a first wake-up. |
| `signal` | An event arrived **and** the wake gate judged it important. |
| `scheduled_wakeup` | The sleep timer the agent set for itself expired. |

Operator `interrupt` and urgent instructions are additional explicit triggers.

The workflow spends its life parked in `workflow.wait_condition(...)`, released
by a signal or by the timer. There is no polling loop.

### The wake gate

Every event passes a cheap gate before the expensive agent runs:

1. Terminal events (`delivered`, `refund_completed`, `order_cancelled`) → always wake.
2. Known-critical (`payment_failed`, `shipment_delayed`, `refund_requested`) → always wake, **no model call**.
3. Known-benign (`shipment_created`) → never wake alone, **no model call**.
4. **Unrecognised event type → wake and flag it.** An unknown event is more
   likely to need judgement than a known-benign one.
5. Anything else → one small Flash Lite call with structured output.

Suppressed events are still **recorded and handed to the agent on its next
turn** — the gate decides whether to *wake*, not whether the agent ever sees
them. The run header shows the suppression rate, which is the whole point: it's
the inference you didn't spend.

The operator's `wake_aggressiveness` setting is applied *on top of* the model's
judgement, so the dial always wins. If the classifier call fails, the gate
**fails open** to the deterministic policy — a broken gate must never silence
the supervisor.

### Completion is workflow-owned

The agent can set `recommend_completion`, and that recommendation is written to
the timeline — but it **does not end the run**. Only these do:

- a terminal order event arrives,
- an operator terminates from the UI,
- the configured `max_run_age_seconds` is reached.

A terminated run still produces its final report before the workflow exits.

### Memory and compaction

The agent rewrites one rolling summary every turn; that summary is the only
long-term history sent to the model. Once the un-compacted tail passes a
threshold, the watermark advances and older entries stop being included in the
prompt — they remain in Postgres for the UI. Prompt size is therefore bounded
regardless of how long the order runs.

The agent can also write **wake guidance** for the gate, so it tunes its own
filtering as it learns what matters for this order.

### The five business actions

`message_fulfillment_team`, `message_payments_team`, `message_logistics_team`,
`message_customer`, `create_internal_note`.

Nothing is sent externally. Each call writes an **activity row** keyed on
`{run_id}:{turn_id}:{tool_use_id}`, so a retried Temporal activity updates its
row rather than sending the message twice. A template's allowlist is enforced by
**not offering the tool to the model at all** — a structural constraint, not a
prompt request.

---

## API

| Method | Path | |
|---|---|---|
| `GET/POST` | `/api/supervisors` | list / create templates |
| `GET/PATCH` | `/api/supervisors/{id}` | fetch / update |
| `GET/POST` | `/api/runs` | list / start a run |
| `GET` | `/api/runs/{id}` | full detail — merges the DB projection with a **live workflow query** |
| `POST` | `/api/runs/{id}/events` | inject an event (signal) |
| `POST` | `/api/runs/{id}/instructions` | add run-specific guidance |
| `POST` | `/api/runs/{id}/pause` · `/resume` · `/interrupt` · `/terminate` | controls |
| `GET` | `/api/event-catalog` | drives the injection panel |
| `GET` | `/api/health` | DB + Temporal + LLM mode |

`POST /api/orders/{order_id}/events` is the same signal addressed by business key.

---

## Configuration

All optional — `.env.example` works as-is against local Docker.

| Variable | Default | |
|---|---|---|
| `DATABASE_URL` | local Postgres | asyncpg URL; Supabase works (see below) |
| `TEMPORAL_HOST` | `localhost:7233` | |
| `LLM_MODE` | `auto` | `auto` \| `live` \| `mock` |
| `GEMINI_API_KEY` | — | unset ⇒ deterministic policy |
| `GROQ_API_KEY` | — | fallback provider; unset ⇒ no second tier |
| `AGENT_MODEL` | `gemini-3.5-flash` | main reasoning agent |
| `CLASSIFIER_MODEL` | `gemini-3.5-flash-lite` | wake gate |
| `FALLBACK_MODEL` | `openai/gpt-oss-120b` | retried once when the primary errors |
| `AGENT_EFFORT` | `medium` | `low`…`max` |
| `DEFAULT_WAKE_SECONDS` | `900` | |
| `MEMORY_COMPACTION_THRESHOLD` | `12` | tail length that triggers compaction |

### Supabase

```
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres?sslmode=require
```

`sslmode` is a libpq parameter that asyncpg rejects;
[`app/db/session.py`](backend/app/db/session.py) strips it and builds a real SSL
context instead. Alembic runs over psycopg2 via `settings.sync_database_url`.

---

## Layout

```
backend/app/
  domain/       shared vocabulary — imported everywhere, imports nothing
  api/routes/   FastAPI handlers
  db/models/    six tables
  repositories/ all database access
  temporal/
    workflows/  the workflow — deterministic, no I/O          ← start here
    activities/ every side effect, retried by Temporal
  agent/        LLM logic — no Temporal imports, testable standalone
    tools/      the 5 business actions + record_turn_outcome
frontend/src/
  app/          App Router pages
  components/   timeline, controls, event injector, memory, report
  lib/          API client + SWR hooks
scripts/        event generator
```

`workflows/` is physically separate from `activities/` because Temporal replays
workflow code deterministically — no I/O, no clock reads, no network. Keeping
them apart makes that constraint structural rather than a comment.

---

## Troubleshooting

**`No supervisor template found`** — run `python -m app.seed`.

**UI shows "API unreachable"** — the API isn't on :8000, or `CORS_ORIGINS`
doesn't include `http://localhost:3000`.

**Events accepted but nothing happens** — the worker isn't running. The API only
signals; the worker executes. Check terminal 2, and
[localhost:8233](http://localhost:8233) for the workflow's history.

**Run stuck in `running` / not responding to controls** — check the worker log.
A workflow task failure retries indefinitely by design; in most cases you fix
the code, restart the worker, and the workflow resumes from where it stopped
with no lost state.

The exception is **`NonDeterministicError`**, which you get if you edit
`workflows/order_supervisor.py` while a workflow is mid-flight: the recorded
history no longer matches what the new code produces on replay, so the workflow
can't advance and can't process signals (including *terminate*). Production
would use Temporal's versioning API; for a POC just clear the stale workflow:

```bash
docker compose exec temporal temporal workflow list --query 'ExecutionStatus="Running"'
docker compose exec temporal temporal workflow terminate --workflow-id "order-supervisor::<ORDER_ID>" --reason stale
```

Runs started *after* the edit are unaffected. Only workflow code has this
constraint — activities, agent logic, prompts and the UI can all be changed
freely while runs are live.

**`connect() got an unexpected keyword argument 'sslmode'`** — you're on a
pre-fix `session.py`; the current one handles it.

**Port 5432 already in use** — a local Postgres is running. Stop it, or change
the host port in `docker-compose.yml` and `DATABASE_URL`.

**Reset everything** — `docker compose down -v && docker compose up -d postgres
temporal`, then re-run migrate + seed.

---

## What's verified

Exercised end to end against the running stack:

- one workflow per order, id derived from the order id (duplicates rejected with 409)
- all three triggers: `workflow_start`, `signal`, `scheduled_wakeup`
- the gate suppressing routine events and waking on important ones
- unknown-event escalation
- the 5 business actions writing activity rows
- tool allowlist enforced structurally (hands-off template sends no customer message)
- instructions applied to a live run
- pause (queues without inference) / resume (drains) / interrupt (forces a turn)
- terminate → still produces a final report
- terminal event → workflow-owned completion → final report
- memory compaction advancing its watermark
- durability: a worker crash mid-run resumes on restart with no lost state
