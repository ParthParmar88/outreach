"""All SQL for products lives here. Nothing above this layer writes SQL."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from outreach.db.models.product import Product, ProductPage


async def get(session: AsyncSession, product_id: uuid.UUID) -> Product | None:
    """
    By id, with no ownership check.

    For the background crawl, which runs outside any request and has no
    signed-in user. Anything reachable from an HTTP route must use
    `get_owned` instead.
    """
    return await session.get(Product, product_id)


async def get_owned(
    session: AsyncSession, product_id: uuid.UUID, user_id: uuid.UUID
) -> Product | None:
    """
    By id, but only if this account owns it.

    Ownership is part of the query rather than a check afterwards. A separate
    `if product.user_id != user.id` is one forgotten line away from letting
    anybody read anybody else's data, and the forgotten line looks fine in
    review.
    """
    stmt = select(Product).where(Product.id == product_id, Product.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_owned_with_pages(
    session: AsyncSession, product_id: uuid.UUID, user_id: uuid.UUID
) -> Product | None:
    stmt = (
        select(Product)
        .where(Product.id == product_id, Product.user_id == user_id)
        .options(selectinload(Product.pages))
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_domain(
    session: AsyncSession, domain: str, user_id: uuid.UUID
) -> Product | None:
    """Per owner. Two accounts may legitimately track the same website."""
    stmt = select(Product).where(Product.domain == domain, Product.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_user(
    session: AsyncSession, user_id: uuid.UUID, limit: int = 50
) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.user_id == user_id)
        .order_by(Product.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def add(session: AsyncSession, product: Product) -> Product:
    session.add(product)
    await session.flush()
    return product


async def clear_pages(session: AsyncSession, product_id: uuid.UUID) -> None:
    """Called before a re-crawl so a shrinking site does not leave orphans."""
    await session.execute(delete(ProductPage).where(ProductPage.product_id == product_id))


async def add_pages(session: AsyncSession, pages: list[ProductPage]) -> None:
    session.add_all(pages)
    await session.flush()
