"""A one-time link for getting back into an account."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from outreach.db.base import Base, TimestampMixin


class PasswordReset(TimestampMixin, Base):
    """
    One password reset request.

    Its own table rather than columns on `app_user`, for the same reason a
    password is not stored in the row that reads it: a reset is an event
    with a lifetime, and events that expire and get used belong in rows you
    can count, expire and audit. Columns on the user would keep exactly one
    request and silently lose the rest.
    """

    __tablename__ = "password_reset"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )

    #: The sha256 of the token, never the token.
    #:
    #: The raw token goes in the link and nowhere else. Anyone reading this
    #: table - a backup, a leaked dump, a support query - gets hashes they
    #: cannot reverse, so a database copy is not a set of skeleton keys to
    #: every account on it.
    #:
    #: sha256 rather than argon2 on purpose. This is 32 bytes of randomness,
    #: not a human-chosen password, so there is no dictionary to slow down;
    #: and the lookup is *by* the hash, which a salted hash cannot do.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: Set the moment it is spent. A reset link that works twice is a reset
    #: link somebody else can still use out of an old email.
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_password_reset_user", "user_id"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PasswordReset user={self.user_id} used={bool(self.used_at)}>"
