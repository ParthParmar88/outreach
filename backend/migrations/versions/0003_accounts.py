"""accounts

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20

Products now belong to somebody.

`product.user_id` is nullable only because rows exist from before accounts
did. Those rows belong to nobody and are therefore visible to nobody, which
is the correct outcome without deleting anyone's data or inventing a fake
owner to attach them to.

The domain uniqueness constraint moves from global to per owner. Two
customers may both be tracking the same website, and one of them being told
"already registered" because a stranger added it first would be absurd.
Postgres treats NULLs as distinct in a unique index, so the pre-account rows
cannot collide with anything.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_app_user_email"),
    )

    op.add_column(
        "product",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("product", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("product", sa.Column("goal", sa.Text(), nullable=True))

    op.create_foreign_key(
        "fk_product_user",
        "product",
        "app_user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_product_user", "product", ["user_id"])

    op.drop_constraint("uq_product_domain", "product", type_="unique")
    op.create_unique_constraint(
        "uq_product_user_domain", "product", ["user_id", "domain"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_product_user_domain", "product", type_="unique")
    op.create_unique_constraint("uq_product_domain", "product", ["domain"])
    op.drop_index("ix_product_user", table_name="product")
    op.drop_constraint("fk_product_user", "product", type_="foreignkey")
    op.drop_column("product", "goal")
    op.drop_column("product", "description")
    op.drop_column("product", "user_id")
    op.drop_table("app_user")
