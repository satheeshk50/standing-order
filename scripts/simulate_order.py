#!/usr/bin/env python
"""Event generator — the scripted half of the simulator.

Drives a realistic, timed sequence of order events into a live workflow so you
can watch the supervisor wake, act, sleep, and finally close out. Useful for
the walkthrough video, where you want a delay to land on cue.

    python scripts/simulate_order.py --list
    python scripts/simulate_order.py --scenario delayed_delivery
    python scripts/simulate_order.py --scenario happy_path --speed 4
    python scripts/simulate_order.py --run-id <uuid> --event shipment_delayed

Every event goes through POST /api/runs/{id}/events, which signals the
workflow — exactly the same path the UI panel uses.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# Windows consoles default to cp1252; make output encoding-proof.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_API = "http://localhost:8000"

# (delay_seconds_before_sending, event_type, payload)
SCENARIOS: dict[str, list[tuple[int, str, dict]]] = {
    "happy_path": [
        (0, "payment_confirmed", {"amount": 129.99, "currency": "USD"}),
        (8, "shipment_created", {"carrier": "DHL", "tracking": "DH-88213771"}),
        (10, "delivered", {"signed_by": "customer"}),
    ],
    "delayed_delivery": [
        (0, "payment_confirmed", {"amount": 129.99, "currency": "USD"}),
        (6, "shipment_created", {"carrier": "DHL", "tracking": "DH-88213771"}),
        (
            10,
            "shipment_delayed",
            {"delay_hours": 48, "reason": "carrier_backlog"},
        ),
        (
            14,
            "customer_message_received",
            {"message": "Where is my order? It was due yesterday."},
        ),
        (12, "delivered", {"signed_by": "neighbour", "late_by_hours": 46}),
    ],
    "payment_trouble": [
        (0, "payment_failed", {"reason": "card_declined", "attempt": 1}),
        (10, "payment_failed", {"reason": "insufficient_funds", "attempt": 2}),
        (10, "payment_confirmed", {"amount": 129.99, "method": "paypal"}),
        (8, "shipment_created", {"carrier": "UPS", "tracking": "1Z-4471"}),
        (10, "delivered", {"signed_by": "customer"}),
    ],
    "refund_journey": [
        (0, "payment_confirmed", {"amount": 129.99}),
        (6, "shipment_created", {"carrier": "FedEx"}),
        (8, "delivered", {"signed_by": "customer"}),
    ],
    "stalled_order": [
        (0, "payment_confirmed", {"amount": 129.99}),
        (8, "no_update_for_n_hours", {"hours": 24}),
        (10, "no_update_for_n_hours", {"hours": 48}),
        (10, "order_cancelled", {"reason": "unfulfillable"}),
    ],
    "unknown_event": [
        (0, "payment_confirmed", {"amount": 129.99}),
        # Not in the catalog — exercises unknown-event escalation.
        (8, "customs_hold_placed", {"country": "DE", "duty_owed": 22.40}),
        (10, "delivered", {"signed_by": "customer"}),
    ],
}


def call(api: str, path: str, body: dict | None = None, method: str = "GET"):
    url = f"{api}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read() or "null")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"HTTP {exc.code} on {method} {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Could not reach the API at {api}. Is it running?\n  {exc}"
        ) from exc


def resolve_run(api: str, run_id: str | None, order_id: str | None) -> dict:
    if run_id:
        return call(api, f"/api/runs/{run_id}")
    runs = call(api, "/api/runs")
    if order_id:
        for run in runs:
            if run["order_id"] == order_id:
                return run
        raise SystemExit(f"No run found for order '{order_id}'.")
    active = [
        r for r in runs if r["status"] not in ("completed", "terminated", "failed")
    ]
    if not active:
        raise SystemExit(
            "No active runs. Start one in the UI (http://localhost:3000/runs/new) "
            "or pass --create."
        )
    return active[0]


def create_run(api: str, order_id: str) -> dict:
    print(f"-> creating run for order {order_id}")
    return call(
        api,
        "/api/runs",
        {
            "order_id": order_id,
            "order_context": {
                "customer_name": "Priya Raman",
                "value": 129.99,
                "items": "1x Noise-cancelling headphones",
                "priority": "standard",
            },
            "seed_order_created_event": True,
        },
        method="POST",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--run-id", help="target run id")
    parser.add_argument("--order-id", help="target order id")
    parser.add_argument(
        "--create", metavar="ORDER_ID", help="create a fresh run first"
    )
    parser.add_argument("--scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--event", help="send one event and exit")
    parser.add_argument("--payload", help="JSON payload for --event")
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="time multiplier; 2 = twice as fast (default 1)",
    )
    parser.add_argument("--list", action="store_true", help="list scenarios")
    args = parser.parse_args()

    if args.list:
        print("Scenarios:\n")
        for name, steps in SCENARIOS.items():
            total = sum(d for d, _, _ in steps)
            print(f"  {name:<20} {len(steps)} events over ~{total}s")
            for delay, event_type, _ in steps:
                print(f"      +{delay:>3}s  {event_type}")
            print()
        return

    if not args.scenario and not args.event:
        parser.error("pass --scenario or --event (or --list)")

    run = create_run(args.api, args.create) if args.create else resolve_run(
        args.api, args.run_id, args.order_id
    )
    run_id, order_id = run["id"], run["order_id"]
    print(f"-> target: order {order_id}  (run {run_id})")

    if args.event:
        payload = json.loads(args.payload) if args.payload else {}
        call(
            args.api,
            f"/api/runs/{run_id}/events",
            {"event_type": args.event, "payload": payload, "source": "simulator"},
            method="POST",
        )
        print(f"  OK sent {args.event}")
        return

    steps = SCENARIOS[args.scenario]
    print(f"-> scenario '{args.scenario}' — {len(steps)} events\n")
    for delay, event_type, payload in steps:
        wait = delay / max(args.speed, 0.1)
        if wait:
            print(f"  ... waiting {wait:.0f}s (agent is asleep)")
            time.sleep(wait)
        call(
            args.api,
            f"/api/runs/{run_id}/events",
            {"event_type": event_type, "payload": payload, "source": "simulator"},
            method="POST",
        )
        print(f"  OK {event_type}  {json.dumps(payload)}")

    print(f"\nDone. Watch it at {args.api.replace(':8000', ':3000')}/runs/{run_id}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
