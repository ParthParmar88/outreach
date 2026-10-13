"""A post we decided was worth answering, and what came of it."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from outreach.db.base import Base, TimestampMixin


class TrackState(enum.StrEnum):
    """
    Where a post has got to. The order is the funnel, and the gap between
    any two of these says more than either number on its own.
    """

    #: We drafted a reply. There is no row before this: being found by a
    #: search is already recorded in `search_run.results`, and a row here
    #: means a person judged this one worth answering.
    DRAFTED = "drafted"
    #: The user says they posted it.
    POSTED = "posted"
    #: Somebody replied after our comment.
    ANSWERED = "answered"
    #: Not worth replying to - either the user decided that or the model did.
    SKIPPED = "skipped"


class Outcome(enum.StrEnum):
    """What the reply was actually worth. Only a person can say."""

    IGNORED = "ignored"
    CONVERSATION = "conversation"
    LEAD = "lead"
    CUSTOMER = "customer"


class TrackedPost(TimestampMixin, Base):
    """
    One post, followed from draft to outcome.

    Its own table rather than a field on the run, and that is the whole
    design. `search_run.results` is a snapshot of one search; a tracked post
    outlives every search that finds it. Storing it on the run would mean
    the second search for a product loses everything the first one taught
    you, which is exactly the thing this feature exists to stop.
    """

    __tablename__ = "tracked_post"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ------------------------------------------------------------ the post
    #: The platform: "github" or "hackernews". With `source_id`, the identity -
    #: the same pair the conversation schema and the de-dup key already use.
    #: No default, so a caller that forgets it fails instead of saying GitHub.
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False)

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: "run-llama/llama_index". Needed to fetch the thread again later.
    container: Mapped[str | None] = mapped_column(String(400), nullable=True)
    #: "issue" or "discussion" - they are re-fetched through different APIs.
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="issue")

    #: Which run first surfaced it, and what it scored then. Kept so a later
    #: change to the scoring cannot rewrite what you were actually looking at
    #: when you decided this one was worth answering.
    first_run_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    score_when_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ----------------------------------------------------------- the draft
    state: Mapped[TrackState] = mapped_column(
        Enum(TrackState, name="track_state", native_enum=False, length=16),
        nullable=False,
        default=TrackState.DRAFTED,
    )

    draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Which prompt wrote it, so an old draft is recognisable as old rather
    #: than passing for something the current prompt would produce.
    draft_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    draft_mentions_product: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    drafted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Why not to reply. Set when the model recommended silence, which is a
    #: real answer worth keeping rather than an empty result to discard.
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # -------------------------------------------------------- what happened
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: The permalink to our own comment. This is the anchor the whole feature
    #: rests on: without it, "did anyone reply" degrades into "did the
    #: comment count go up", which on a busy issue is true regardless of
    #: anything we did.
    our_comment_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    our_comment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    #: The thread's comment count when we posted, so a re-check can still
    #: tell new from old when the comment id is unknown.
    comments_when_posted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    replies_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: The person who wrote the original post answered us. Its own field
    #: because a stranger arguing underneath is not the same event.
    author_replied: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    outcome: Mapped[Outcome | None] = mapped_column(
        Enum(Outcome, name="track_outcome", native_enum=False, length=16),
        nullable=True,
    )
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # One row per post per product. Drafting twice updates the draft
        # rather than starting a second history for the same thread.
        UniqueConstraint(
            "product_id", "source", "source_id", name="uq_tracked_post_identity"
        ),
        Index("ix_tracked_post_product_state", "product_id", "state"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TrackedPost {self.source}:{self.source_id} {self.state}>"
