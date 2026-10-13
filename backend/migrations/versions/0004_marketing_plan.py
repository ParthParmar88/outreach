"""marketing plan

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-21

The planner agent's output, stored on the product it was written for.

`plan_source_hash` covers the profile, the description and the goal together.
Changing the goal should produce a new plan; re-crawling a website that did
not change should not. Hashing all three is what makes both true.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product",
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "product",
        sa.Column("plan_source_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "product",
        sa.Column("plan_made_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product", "plan_made_at")
    op.drop_column("product", "plan_source_hash")
    op.drop_column("product", "plan")
