"""FastAPI dependencies: db session, current user."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from outreach import security
from outreach.db.models.user import User
from outreach.db.repositories import users as user_repo
from outreach.db.session import SessionFactory


async def get_session() -> AsyncIterator[AsyncSession]:
    """One session per request. Commits on success, rolls back on failure."""
    session = SessionFactory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(request: Request, session: DbSession) -> User:
    """
    The signed-in account, or 401.

    Every failure returns the same 401 with the same wording. Distinguishing
    "no cookie" from "expired" from "user deleted" would tell an attacker
    which of those they are looking at, and tells a real user nothing they
    can act on beyond "sign in again".
    """
    unauthorised = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not signed in.",
    )

    token = request.cookies.get(security.COOKIE_NAME)
    if not token:
        raise unauthorised

    user_id = security.read_session_token(token)
    if user_id is None:
        raise unauthorised

    user = await user_repo.get(session, user_id)
    if user is None:
        raise unauthorised

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_optional_user(request: Request, session: DbSession) -> User | None:
    """For endpoints that behave differently when signed in, but do not require it."""
    token = request.cookies.get(security.COOKIE_NAME)
    if not token:
        return None
    user_id = security.read_session_token(token)
    if user_id is None:
        return None
    return await user_repo.get(session, user_id)


OptionalUser = Annotated["User | None", Depends(get_optional_user)]
