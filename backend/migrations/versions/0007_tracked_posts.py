"""tracked posts

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-01

The reply funnel: drafted -> posted -> answered -> outcome.

Numbered after `0006_leads` rather than beside it. Both were written as
0006 on separate branches, which left alembic with two heads and made
`upgrade head` ambiguous - the failure a second person hits on a fresh
clone, not the person whose database is already stamped.

Its own table rather than a field on `search_run`. A run is a snapshot of one
search; a tracked post outlives every search that finds it, which is the
whole point of tracking it. Put on the run, the second search for a product
would lose everything the first one taught you.

`our_comment_url` is the field the feature rests on. Without a permalink to
our own comment, "did anyone reply" degrades into "did the comment count go
up", which on a busy issue is true regardless of anything we did.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: VARCHAR with a CHECK rather than a native PostgreSQL enum, matching
#: crawl_state. A native enum needs its own ALTER TYPE migration to gain a
#: value, and these will gain values.
_STATE = sa.Enum(
    "DRAFTED", "POSTED", "ANSWERED", "SKIPPED",
    name="track_state", native_enum=False, length=16,
)
_OUTCOME = sa.Enum(
    "IGNORED", "CONVERSATION", "LEAD", "CUSTOMER",
    name="track_outcome", native_enum=False, length=16,
)


def upgrade() -> None:
    op.create_table(
        "tracked_post",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("container", sa.String(length=400), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),

        sa.Column("first_run_id", sa.String(length=12), nullable=True),
        sa.Column("score_when_found", sa.Integer(), nullable=False),

        sa.Column("state", _STATE, nullable=False),
        sa.Column("draft", sa.Text(), nullable=True),
        sa.Column("draft_version", sa.String(length=40), nullable=True),
        sa.Column("draft_mentions_product", sa.Boolean(), nullable=False),
        sa.Column("drafted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skip_reason", sa.Text(), nullable=True),

        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("our_comment_url", sa.String(length=2048), nullable=True),
        sa.Column("our_comment_id", sa.String(length=64), nullable=True),
        sa.Column("comments_when_posted", sa.Integer(), nullable=False),
        sa.Column("replies_after", sa.Integer(), nullable=False),
        sa.Column("author_replied", sa.Boolean(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("outcome", _OUTCOME, nullable=True),
        sa.Column("outcome_note", sa.Text(), nullable=True),

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

        # Deleting a product takes its tracked posts with it. A draft written
        # against a product that no longer exists is not worth keeping.
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Drafting the same post twice updates the draft rather than starting
        # a second, competing history for one thread.
        sa.UniqueConstraint(
            "product_id", "source", "source_id", name="uq_tracked_post_identity"
        ),
    )
    op.create_index(
        "ix_tracked_post_product_state", "tracked_post", ["product_id", "state"]
    )


def downgrade() -> None:
    op.drop_index("ix_tracked_post_product_state", table_name="tracked_post")
    op.drop_table("tracked_post")
