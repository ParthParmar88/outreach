"""One search, kept so it is still there tomorrow."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from outreach.db.base import Base, TimestampMixin


class SearchRun(TimestampMixin, Base):
    """
    A completed run of the opportunity search.

    Runs used to live in a module-level dict and nothing else, so every one
    of them died with the process. The service still uses that dict while a
    run is in flight - a row per progress tick would be a write every two
    seconds for nothing - but the run is written here when it starts and
    again when it reaches a final state.

    That leaves one gap on purpose: a run interrupted by a restart stays
    "running" in this table with nobody working on it. `is_lost()` is how
    the read path tells that apart from a run that is genuinely in progress,
    the same way `product_service.is_stale` does it for a dead crawl.
    """

    __tablename__ = "search_run"

    #: The service's own 12-character handle, not a UUID.
    #:
    #: It is already in URLs the frontend holds, so inventing a second
    #: identifier here would mean translating between them on every call for
    #: no gain.
    id: Mapped[str] = mapped_column(String(12), primary_key=True)

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )

    platform: Mapped[str] = mapped_column(String(40), nullable=False, default="github")

    #: queued | running | succeeded | failed
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")

    #: What was actually searched, when the user overrode the plan. NULL
    #: means "whatever the plan said at the time", which is not recoverable
    #: later - the plan may since have been rewritten. Worth storing exactly
    #: because of that.
    terms: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    repos: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    results: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    stages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Denormalised from `results` so the home page can list recent searches
    #: without reading a megabyte of JSONB to print two numbers.
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # Every read of this table is "the newest runs for one product".
        Index("ix_search_run_product_started", "product_id", "started_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SearchRun {self.id} {self.state} {self.result_count} results>"
