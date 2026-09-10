"""Temporal worker process.

Run alongside the API:  ``python -m app.worker``

The worker hosts the workflow and every activity. It is a separate process from
FastAPI so that a slow agent turn can never block an HTTP request, and so the
two can be scaled and restarted independently.
"""

import asyncio
import logging

from temporalio.worker import Worker

from app.config import settings
from app.temporal.activities import ALL_ACTIVITIES
from app.temporal.client import get_client
from app.temporal.workflows.order_supervisor import OrderSupervisorWorkflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("worker")


async def main() -> None:
    client = await get_client()
    log.info(
        "worker starting — queue=%s  agent=%s  classifier=%s  llm=%s",
        settings.temporal_task_queue,
        settings.agent_model,
        settings.classifier_model,
        "live" if settings.llm_live else "mock (no API key)",
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[OrderSupervisorWorkflow],
        activities=ALL_ACTIVITIES,
        # Agent turns are long and I/O bound; a handful in flight is plenty.
        max_concurrent_activities=20,
    )
    await worker.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("worker stopped")
