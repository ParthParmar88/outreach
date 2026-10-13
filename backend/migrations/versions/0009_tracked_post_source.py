"""tracked post source

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-17

Hacker News replies were stored as GitHub ones.

The draft endpoint defaulted `source` to "github" and the frontend never sent
it, so every reply written to a Hacker News post was counted on the GitHub
row of the activity page. The endpoint now requires the field; this fixes
the rows written before it did.

A Hacker News row is recognisable by its URL - the connector always links
the item on news.ycombinator.com, never the article a story points at.

Guarded by NOT EXISTS so the unique (product, source, source_id) key cannot
be broken by a row that was, somehow, already stored correctly.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE tracked_post AS t
           SET source = 'hackernews'
         WHERE t.source = 'github'
           AND t.url LIKE 'https://news.ycombinator.com/%'
           AND NOT EXISTS (
                 SELECT 1
                   FROM tracked_post AS o
                  WHERE o.product_id = t.product_id
                    AND o.source = 'hackernews'
                    AND o.source_id = t.source_id
               )
        """
    )


def downgrade() -> None:
    # Deliberately nothing. Putting these back under "github" would only
    # restore the miscount.
    pass
