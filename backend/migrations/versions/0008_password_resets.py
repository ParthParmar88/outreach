"""password resets

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-08

Getting back into an account without asking anybody.

Until now a forgotten password meant making a second account, which is what
actually happened at least once: the same person, the same product, two rows
and no way to join them.

`token_hash` is unique and holds a sha256, never the token itself. The raw
token exists only in the link. A copy of this table is therefore a list of
hashes rather than a set of skeleton keys, and the lookup still works
because a plain hash can be searched for - which is the reason it is not
argon2 here.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Deleting an account takes its pending resets with it. A live reset
        # link for a deleted account is a way back into nothing, and should
        # not outlive the row it points at.
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_token"),
    )
    op.create_index("ix_password_reset_user", "password_reset", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_user", table_name="password_reset")
    op.drop_table("password_reset")
