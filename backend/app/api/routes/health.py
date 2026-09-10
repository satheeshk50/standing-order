"""Health + environment introspection, so the UI can show what mode it's in."""

from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.db.session import engine
from app.temporal.client import get_client

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    checks: dict[str, str] = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    try:
        await get_client()
        checks["temporal"] = "ok"
    except Exception as exc:
        checks["temporal"] = f"error: {exc}"

    return {
        "status": "ok" if all(v == "ok" for v in checks.values()) else "degraded",
        "checks": checks,
        "llm": {
            "mode": "live" if settings.llm_live else "mock",
            "agent_model": settings.agent_model,
            "classifier_model": settings.classifier_model,
        },
        "temporal": {
            "host": settings.temporal_host,
            "task_queue": settings.temporal_task_queue,
        },
    }
