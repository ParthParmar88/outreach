"""An account. One person, many products."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from outreach.db.base import Base, TimestampMixin, uuid_pk


class User(TimestampMixin, Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = uuid_pk()

    #: Stored lowercased and stripped. The unique index is on this column, so
    #: normalising on the way in is what actually prevents duplicate accounts
    #: for "Nisarg@x.com" and "nisarg@x.com".
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    #: argon2id. The full encoded string, which carries its own parameters,
    #: so raising the cost later does not invalidate existing passwords.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email}>"
