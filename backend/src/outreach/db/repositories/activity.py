"""
What has been done, counted per platform.

All SQL, no loading rows. The point of this screen is totals, and a total
that quietly stops counting at whatever the display limit happens to be is
worse than no total at all.

Every function takes an optional `product_id`. Given, it narrows to that one
product; omitted, it covers the whole account. The ownership join stays in
place either way - narrowing is a filter on top of it, never instead of it,
so a product id belonging to somebody else simply matches nothing.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from outreach.db.models.product import Product
from outreach.db.models.search_run import SearchRun
from outreach.db.models.tracked_post import TrackedPost, TrackState


def _scope(
    user_id: uuid.UUID, product_id: uuid.UUID | None
) -> list[ColumnElement[bool]]:
    """The account, and optionally one product inside it."""
    where: list[ColumnElement[bool]] = [Product.user_id == user_id]
    if product_id is not None:
        where.append(Product.id == product_id)
    return where


async def searches_by_platform(
    session: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID | None = None
) -> dict[str, dict[str, int]]:
    """
    Searches run and opportunities found, per platform.

    The join to product is the ownership check: totals are computed over this
    account's products only, in the query, rather than filtered afterwards.
    """
    stmt = (
        select(
            SearchRun.platform,
            func.count().label("searches"),
            func.coalesce(func.sum(SearchRun.result_count), 0).label("results"),
        )
        .join(Product, Product.id == SearchRun.product_id)
        .where(*_scope(user_id, product_id))
        .group_by(SearchRun.platform)
    )
    rows = (await session.execute(stmt)).all()
    return {
        platform: {"searches": int(searches), "results": int(results)}
        for platform, searches, results in rows
    }


async def replies_by_platform(
    session: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID | None = None
) -> dict[str, dict[str, int]]:
    """Replies written, posted, answered and skipped, per platform."""
    stmt = (
        select(TrackedPost.source, TrackedPost.state, func.count())
        .join(Product, Product.id == TrackedPost.product_id)
        .where(*_scope(user_id, product_id))
        .group_by(TrackedPost.source, TrackedPost.state)
    )
    rows = (await session.execute(stmt)).all()

    out: dict[str, dict[str, int]] = {}
    for source, state, total in rows:
        bucket = out.setdefault(
            source, {"written": 0, "posted": 0, "answered": 0, "skipped": 0}
        )
        name = state.value if hasattr(state, "value") else str(state).lower()

        # Every row that is not a skip had a reply written for it, whatever
        # happened next. Counting only the ones still sitting at "drafted"
        # would make the number go *down* as things went well, which is the
        # kind of metric that teaches people to distrust the whole screen.
        if name != TrackState.SKIPPED.value:
            bucket["written"] += int(total)
        if name in (TrackState.POSTED.value, TrackState.ANSWERED.value):
            bucket["posted"] += int(total)
        if name == TrackState.ANSWERED.value:
            bucket["answered"] += int(total)
        if name == TrackState.SKIPPED.value:
            bucket["skipped"] += int(total)

    return out


async def outcomes(
    session: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID | None = None
) -> dict[str, int]:
    """
    What replies were actually worth, as counted by the person who replied.

    The only numbers on the screen that are not a by-product of using the
    tool. Everything else says what happened; these say whether it mattered.
    """
    stmt = (
        select(TrackedPost.outcome, func.count())
        .join(Product, Product.id == TrackedPost.product_id)
        .where(*_scope(user_id, product_id), TrackedPost.outcome.is_not(None))
        .group_by(TrackedPost.outcome)
    )
    rows = (await session.execute(stmt)).all()
    return {
        (outcome.value if hasattr(outcome, "value") else str(outcome).lower()): int(n)
        for outcome, n in rows
    }


async def product_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Product).where(Product.user_id == user_id)
    return int((await session.execute(stmt)).scalar_one())
