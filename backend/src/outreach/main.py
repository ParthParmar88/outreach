"""FastAPI application. Wiring only, no business logic."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from outreach.api.v1.router import router as v1_router
from outreach.config import settings
from outreach.db import bootstrap

logging.basicConfig(level=settings.log_level)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(settings.log_level)
    ),
)

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """
    Startup and shutdown.

    With AUTO_MIGRATE on, the database is created if missing and brought up
    to the latest migration before the first request is served. That is what
    lets a second person clone the repository and run one command.
    """
    if settings.auto_migrate:
        try:
            await bootstrap.prepare_database()
        except bootstrap.DatabaseUnavailable as exc:
            # Refuse to start rather than serve 500s on every request. The
            # message says what to do; a traceback would not.
            log.error("startup.database_unavailable", detail=str(exc))
            raise SystemExit(f"\nCannot start.\n\n{exc}\n") from exc
    else:
        log.info("startup.auto_migrate_disabled")

    yield


app = FastAPI(
    title="Outreach",
    version="0.1.0",
    description=(
        "Finds public developer conversations where someone has the problem "
        "our product solves."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Final paths are /api/v1/...
app.include_router(v1_router, prefix="/api")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "outreach", "docs": "/docs", "api": "/api/v1"}
