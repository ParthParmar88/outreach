"""leads

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-02

Opportunities become things you can act on, rather than rows inside a run.

Until now a result existed only inside `search_run.results` as JSON, so the
same GitHub issue found on Monday and again on Friday was two unrelated
blobs and there was nowhere to record that somebody had already replied.
The identity needed to fix that was always present - GitHub's node id is
stable and appears in every run that returns the post - it simply had no
table to live in.

The unique constraint on (product_id, source_id) is the whole design. It is
what makes a second search update a lead instead of duplicating it, and
therefore what makes "new since your last search" a query rather than a
guess.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        # GitHub's node id, and the reason this table works.
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("container", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        # Highest score any run has given it, not the latest: a rubric
        # change should not silently demote a lead somebody is working.
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
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
        # Deleting a product takes its leads with it. A lead means nothing
        # apart from the product it was scored against.
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "source_id", name="uq_lead_product_source"),
    )
    op.create_index("ix_lead_product_score", "lead", ["product_id", "score"])
    op.create_index("ix_lead_product_state", "lead", ["product_id", "state"])


def downgrade() -> None:
    op.drop_index("ix_lead_product_state", table_name="lead")
    op.drop_index("ix_lead_product_score", table_name="lead")
    op.drop_table("lead")
