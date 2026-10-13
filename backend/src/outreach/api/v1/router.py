"""Mounts all v1 routes under /v1."""

from __future__ import annotations

from fastapi import APIRouter

from outreach.api.v1 import (
    activity,
    auth,
    flow,
    health,
    leads,
    opportunities,
    products,
    sources,
    tracking,
)

router = APIRouter(prefix="/v1")

router.include_router(health.router)
router.include_router(auth.router)
router.include_router(activity.router)
router.include_router(products.router)
router.include_router(opportunities.router)
router.include_router(leads.router)
router.include_router(tracking.router)
router.include_router(sources.router)
router.include_router(flow.router)

# briefs, plans, runs, results, exports and events join here as they are
# built.
