"""Async engine / session factory.

Supabase (and most hosted Postgres) hand out URLs with ``?sslmode=require``.
asyncpg does not understand ``sslmode`` — it takes an ``ssl`` argument instead —
so we strip the libpq-style query params and translate them here. Without this
you get a confusing ``connect() got an unexpected keyword argument 'sslmode'``.
"""

import ssl
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding", "target_session_attrs"}


def _prepare_url(url: str) -> tuple[str, dict]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    connect_args: dict = {}

    sslmode = (query.get("sslmode") or [None])[0]
    if sslmode in ("require", "verify-ca", "verify-full"):
        context = ssl.create_default_context()
        if sslmode == "require":
            # Hosted Postgres proxies frequently use certs that don't verify
            # against the system trust store; encryption still applies.
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = context

    cleaned = {k: v for k, v in query.items() if k not in _LIBPQ_ONLY_PARAMS}
    parsed = parsed._replace(query=urlencode(cleaned, doseq=True))
    return urlunparse(parsed), connect_args


_url, _connect_args = _prepare_url(settings.database_url)

engine = create_async_engine(
    _url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args=_connect_args,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with SessionLocal() as session:
        yield session
