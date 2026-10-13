"""Liveness and readiness. Readiness must actually touch the database."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from outreach.api.deps import DbSession

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: DbSession) -> dict[str, str]:
    """A readiness check that does not query the database is a lie."""
    await session.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}
