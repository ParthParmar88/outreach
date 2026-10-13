"""All SQL for accounts lives here."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from outreach.db.models.user import User


def normalise_email(email: str) -> str:
    """
    Lowercased and stripped.

    Applied on every read and every write, because the unique index cannot
    tell "Nisarg@x.com" from "nisarg@x.com" unless the value arrives already
    normalised.
    """
    return email.strip().lower()


async def get(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(
        select(User).where(User.email == normalise_email(email))
    )
    return result.scalar_one_or_none()


async def add(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user
