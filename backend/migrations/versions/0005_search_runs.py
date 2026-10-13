"""search runs

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-31

Searches survive a restart from here on.

They lived in a module-level dict, which meant "show me the last search"
had no answer to give: every run died with the process, and the run id
sitting in somebody's browser URL pointed at nothing. This is the table
behind the last-search card on the home page.

`result_count` and `top_score` duplicate what is inside `results`. That is
deliberate: listing recent runs should not have to parse a JSONB blob per
row to print two integers.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_run",
        # The service's own 12-character handle, already present in URLs.
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("terms", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("repos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("top_score", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        # Deleting a product takes its searches with it. Results are only
        # meaningful next to the product they were scored against.
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_run_product_started", "search_run", ["product_id", "started_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_search_run_product_started", table_name="search_run")
    op.drop_table("search_run")
