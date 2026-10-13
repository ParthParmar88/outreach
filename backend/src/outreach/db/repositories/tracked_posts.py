"""All SQL for tracked posts. Nothing above this layer writes SQL."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from outreach.db.models.tracked_post import TrackedPost, TrackState


async def get(session: AsyncSession, tracked_id: uuid.UUID) -> TrackedPost | None:
    """By id, with no ownership check. Routes must use `get_owned`."""
    return await session.get(TrackedPost, tracked_id)


async def get_owned(
    session: AsyncSession, tracked_id: uuid.UUID, user_id: uuid.UUID
) -> TrackedPost | None:
    """
    By id, but only if this account owns the product it belongs to.

    The join is the ownership check, in the query rather than after it. A
    separate `if post.product.user_id != user.id` is one forgotten line away
    from letting anybody read anybody else's drafts, and the forgotten line
    looks fine in review.
    """
    from outreach.db.models.product import Product

    stmt = (
        select(TrackedPost)
        .join(Product, Product.id == TrackedPost.product_id)
        .where(TrackedPost.id == tracked_id, Product.user_id == user_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_source(
    session: AsyncSession, product_id: uuid.UUID, source: str, source_id: str
) -> TrackedPost | None:
    """The row for one post, if this product is already tracking it."""
    stmt = select(TrackedPost).where(
        TrackedPost.product_id == product_id,
        TrackedPost.source == source,
        TrackedPost.source_id == source_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_product(
    session: AsyncSession, product_id: uuid.UUID, limit: int = 200
) -> list[TrackedPost]:
    """
    Newest first.

    By `created_at` rather than by state, because the screen groups by state
    itself and a post moving from drafted to posted should not jump to a
    different place in the list.
    """
    stmt = (
        select(TrackedPost)
        .where(TrackedPost.product_id == product_id)
        .order_by(TrackedPost.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def open_for_checking(
    session: AsyncSession,
    user_id: uuid.UUID,
    product_id: uuid.UUID | None = None,
    *,
    checked_before: datetime,
    limit: int = 25,
) -> list[TrackedPost]:
    """
    Posts a reply-check could tell us something new about.

    Only `posted`: a draft nobody sent cannot have been answered, and a post
    already marked answered has told us the thing we were waiting for. Only
    those not looked at since `checked_before`, so opening a screen twice
    does not fetch every thread twice. The limit is a rate-limit cap - every
    re-check spends from the GitHub allowance the search also needs.

    Scoped by the owning account in the query, one product or all of them.
    """
    from outreach.db.models.product import Product

    stmt = (
        select(TrackedPost)
        .join(Product, Product.id == TrackedPost.product_id)
        .where(
            Product.user_id == user_id,
            TrackedPost.state == TrackState.POSTED,
            or_(
                TrackedPost.last_checked_at.is_(None),
                TrackedPost.last_checked_at < checked_before,
            ),
        )
        .order_by(TrackedPost.last_checked_at.asc().nulls_first())
        .limit(limit)
    )
    if product_id is not None:
        stmt = stmt.where(TrackedPost.product_id == product_id)
    return list((await session.execute(stmt)).scalars())


async def funnel(session: AsyncSession, product_id: uuid.UUID) -> dict[str, int]:
    """
    How many posts are in each state.

    Counted in SQL rather than by loading every row and counting in Python:
    the list is capped at 200 for display, and a funnel that silently stops
    counting at 200 would be worse than no funnel.
    """
    stmt = (
        select(TrackedPost.state, func.count())
        .where(TrackedPost.product_id == product_id)
        .group_by(TrackedPost.state)
    )
    rows = (await session.execute(stmt)).all()
    counts = {state.value: 0 for state in TrackState}
    for state, total in rows:
        counts[state.value if hasattr(state, "value") else str(state)] = total
    return counts


async def add(session: AsyncSession, post: TrackedPost) -> TrackedPost:
    session.add(post)
    await session.flush()
    return post
