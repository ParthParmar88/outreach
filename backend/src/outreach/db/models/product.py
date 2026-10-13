"""product profile rows and their content version hash."""

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from outreach.db.base import Base, TimestampMixin, uuid_pk


class CrawlMode(enum.StrEnum):
    """Which path discovery took. See connectors/website/discovery.py."""

    DOCS = "docs"
    SITE = "site"


class CrawlState(enum.StrEnum):
    QUEUED = "queued"
    CRAWLING = "crawling"
    READY = "ready"
    #: Fetched fine, but almost every page came back empty. Usually a
    #: JavaScript-rendered site that plain HTTP cannot read.
    THIN = "thin"
    FAILED = "failed"


class Product(TimestampMixin, Base):
    """
    One product, identified by the website the user gave us.

    Crawled once. Never re-crawled automatically: a refresh only happens
    when a person presses the button.
    """

    __tablename__ = "product"

    id: Mapped[uuid.UUID] = uuid_pk()

    #: Nullable only because products existed before accounts did. Anything
    #: created from now on has an owner, and a NULL row belongs to nobody and
    #: is therefore visible to nobody.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    #: What it does, in the owner's words. The crawl describes the website;
    #: this describes the product, and the two disagree more often than you
    #: would expect.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: What they are trying to achieve. "First hundred users" and "find design
    #: partners" and "hire engineers" make completely different posts
    #: valuable, so this has to reach the scorer rather than sit in a form.
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Exactly what the user typed, kept so we can show it back to them.
    input_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    #: Normalised origin, e.g. https://example.com
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    #: Host without www. The identity of a product.
    domain: Mapped[str] = mapped_column(String(255), nullable=False)

    mode: Mapped[CrawlMode | None] = mapped_column(
        Enum(CrawlMode, name="crawl_mode", native_enum=False, length=16),
        nullable=True,
    )
    state: Mapped[CrawlState] = mapped_column(
        Enum(CrawlState, name="crawl_state", native_enum=False, length=16),
        nullable=False,
        default=CrawlState.QUEUED,
    )

    #: Where discovery decided the documentation lives, when mode is DOCS.
    docs_root: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    #: Every page joined into one document. This is the file the AI reads.
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: sha256 of markdown, so we can tell whether a re-crawl changed anything.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    #: What the website means, extracted once: domain, problems, pain words.
    #: This is what the search actually uses - the markdown above is only the
    #: raw material it was read from.
    profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    #: The content_hash the profile was built from. A re-crawl that changes
    #: nothing leaves this matching, so the extraction is not paid for twice.
    profile_source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    #: The planner agent's marketing plan: strategy, audience, platforms.
    plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    #: Covers the profile, the description and the goal together, so editing
    #: the goal produces a new plan and a no-op re-crawl does not.
    plan_source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plan_made_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bytes_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: True when a seatbelt stopped the crawl early. We say so rather than
    #: pretending we read the whole site.
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stop_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    crawl_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    crawl_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    pages: Mapped[list[ProductPage]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductPage.order_index",
        lazy="selectin",
    )

    __table_args__ = (
        # Per owner, not global. Two customers may both be tracking the same
        # website, and one of them getting "already registered" because a
        # stranger added it first would be absurd.
        UniqueConstraint("user_id", "domain", name="uq_product_user_domain"),
        Index("ix_product_state", "state"),
        Index("ix_product_user", "user_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Product {self.name} {self.domain} {self.state.value}>"


class ProductPage(TimestampMixin, Base):
    """
    One crawled page, as markdown.

    Kept separately from Product.markdown so that every sentence can be
    traced back to the page it came from, and so a single page can be
    re-fetched without crawling the whole site again.
    """

    __tablename__ = "product_page"

    id: Mapped[uuid.UUID] = uuid_pk()

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")

    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False, default=200)

    #: Under settings.thin_page_words. Stored anyway, excluded from the
    #: combined document, so the failure is visible instead of silent.
    is_thin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Crawl order, so the combined document reads in a sensible sequence.
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    product: Mapped[Product] = relationship(back_populates="pages")

    __table_args__ = (
        UniqueConstraint("product_id", "url", name="uq_product_page_url"),
        Index("ix_product_page_product", "product_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ProductPage {self.url} {self.word_count}w>"
