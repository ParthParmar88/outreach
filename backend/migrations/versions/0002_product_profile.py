"""product profile

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-19

What the crawled website means, extracted once: the domain, the problems it
solves, and the words a frustrated user would type. Before this, the crawl
produced a markdown document that nothing read.

Stored as JSONB rather than columns because the shape is still moving, and
`profile_source_hash` records which version of the page content it came from
so a re-crawl that changed nothing does not pay for it again.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product",
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "product",
        sa.Column("profile_source_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product", "profile_source_hash")
    op.drop_column("product", "profile")
