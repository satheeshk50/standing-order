"""FastAPI entrypoint.

Run directly:
    python main.py

Or with uvicorn:
    uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.api.routes import events, health, runs, supervisors
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "API starting — temporal=%s  llm=%s",
        settings.temporal_host,
        "live" if settings.llm_live else "mock (no API key configured)",
    )
    yield


app = FastAPI(
    title="Order Supervisor",
    description=(
        "A long-running AI supervisor that oversees a single order from "
        "creation to completion, one Temporal workflow per order."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(supervisors.router)
app.include_router(runs.router)
app.include_router(events.router)


@app.get("/")
async def root():
    return {"service": "order-supervisor", "docs": "/docs"}


if __name__ == "__main__":
    import os

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
