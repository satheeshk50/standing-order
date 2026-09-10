"""Shared Temporal client. One connection per process, created lazily."""

import logging

from temporalio.client import Client

from app.config import settings

log = logging.getLogger(__name__)

_client: Client | None = None


async def get_client() -> Client:
    global _client
    if _client is None:
        log.info("connecting to Temporal at %s", settings.temporal_host)
        _client = await Client.connect(
            settings.temporal_host, namespace=settings.temporal_namespace
        )
    return _client


def workflow_id_for(order_id: str) -> str:
    """One workflow per order, enforced by a deterministic workflow id.

    Temporal rejects a second start with the same id while one is running, so
    duplicate order creation cannot spawn a second supervisor.
    """
    return f"order-supervisor::{order_id}"
