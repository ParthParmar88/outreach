"""All SQL for password resets. Nothing above this layer writes SQL."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from outreach.db.models.password_reset import PasswordReset


async def invalidate_open(session: AsyncSession, user_id: uuid.UUID) -> None:
    """
    Spend every unused reset this account already has.

    Asking for a second link must kill the first. Otherwise every request
    somebody makes while flustered leaves another working key lying in
    another email, and the oldest one outlives the reason it was sent.
    """
    await session.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user_id, PasswordReset.used_at.is_(None))
        .values(used_at=datetime.now(UTC))
    )


async def add(
    session: AsyncSession, user_id: uuid.UUID, token_hash: str, expires_at: datetime
) -> PasswordReset:
    row = PasswordReset(
        user_id=user_id, token_hash=token_hash, expires_at=expires_at
    )
    session.add(row)
    await session.flush()
    return row


async def get_usable(session: AsyncSession, token_hash: str) -> PasswordReset | None:
    """
    The reset this token opens, if it is still good.

    Unused and unexpired are both part of the query rather than checked
    afterwards. A caller that forgets one of those two checks has written a
    reset link that works forever, and the missing line looks fine in
    review.
    """
    stmt = select(PasswordReset).where(
        PasswordReset.token_hash == token_hash,
        PasswordReset.used_at.is_(None),
        PasswordReset.expires_at > datetime.now(UTC),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def mark_used(session: AsyncSession, reset: PasswordReset) -> None:
    reset.used_at = datetime.now(UTC)
