"""One opportunity, tracked across every search that finds it."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from outreach.db.base import Base, TimestampMixin

#: What can be done with a lead, and nothing else.
#:
#: Deliberately short. Every extra state is one more decision at the moment
#: somebody is trying to get through a list, and the ones here are the only
#: distinctions that change what you do next: it is waiting, you spoke, you
#: decided not to, or it turned into something.
STATES = ("new", "replied", "ignored", "won")


class Lead(TimestampMixin, Base):
    """
    A post worth replying to, remembered between runs.

    ── Why this exists ──────────────────────────────────────────────────

    Results used to live only inside `search_run.results`, as JSON. That
    made every run a fresh start: the same GitHub issue found on Monday and
    again on Friday was two unrelated blobs, with nowhere to record that
    somebody had already replied to it. A list you cannot mark off is a
    list you re-read rather than work.

    The identity was there the whole time and simply had no home.
    `source_id` is GitHub's node id - stable forever, identical in every
    run that returns the post - so this table is mostly plumbing around a
    key that already existed.

    ── What is stored, and what is not ──────────────────────────────────

    Enough to show a row without opening a run: title, url, repository, and
    the best score any search has given it. Everything else - the evidence
    quote, the intent, the reasoning - stays in the run, because that is a
    judgement made at a point in time and copying it here would produce two
    versions of the same opinion, ageing apart.
    """

    __tablename__ = "lead"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )

    #: GitHub's node id. The reason this table works at all.
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)

    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    container: Mapped[str | None] = mapped_column(String(255), nullable=True)

    state: Mapped[str] = mapped_column(String(20), nullable=False, default="new")

    #: Whatever the person wants to remember. Never shown to a model.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: The best score any run has given this post.
    #:
    #: Highest rather than latest on purpose: prompts change, and a lead
    #: that scored 81 last week should not quietly become a 20 because a
    #: rubric moved underneath it. The run always holds the current answer.
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: When it first turned up, and when a search last returned it. The
    #: pair is what "new since your last search" is counted from.
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    #: When somebody last moved it out of `new`. Null while untouched.
    acted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # The whole point of the table. Without it the same post inserts
        # again on every run and nothing can be marked off.
        UniqueConstraint("product_id", "source_id", name="uq_lead_product_source"),
        # Every read is "this product's leads, best first".
        Index("ix_lead_product_score", "product_id", "score"),
        Index("ix_lead_product_state", "product_id", "state"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Lead {self.source_id} {self.state} {self.score}>"
