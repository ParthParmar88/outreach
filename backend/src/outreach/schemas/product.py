"""Pydantic contracts for products. The shared vocabulary between layers."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from outreach.db.models.product import CrawlMode, CrawlState
from outreach.planner import MarketingPlan


class ProductCreate(BaseModel):
    """Body of POST /api/v1/products. Exactly what the user typed."""

    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=3, max_length=2048)

    #: What the product does, in the owner's words. The crawl describes the
    #: website; this describes the product, and the two disagree more often
    #: than you would expect.
    description: str | None = Field(default=None, max_length=4000)

    #: What they are trying to achieve. Different goals make completely
    #: different posts valuable, so this reaches the scorer rather than
    #: sitting unused in a form.
    goal: str | None = Field(default=None, max_length=2000)


class ProductUpdate(BaseModel):
    """
    Body of PATCH /api/v1/products/{id}. Every field optional.

    Only three fields, and deliberately not the URL. Changing the address
    means a different website, so it is a different product - allowing it
    here would leave a row whose crawl, profile and plan all describe
    somewhere else, with nothing to say so.

    Changing `description` or `goal` makes the plan stale, because both are
    hashed into `plan_source_hash`. That is the point: the two are what the
    planner reads, so editing them and keeping the old plan would mean the
    search still hunts for whatever the first draft said.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    goal: str | None = Field(default=None, max_length=2000)


class ProductPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    title: str | None
    word_count: int
    is_thin: bool
    order_index: int
    fetched_at: datetime


class ProductOut(BaseModel):
    """
    Everything except the markdown.

    The combined document can be hundreds of kilobytes, so it has its own
    endpoint rather than riding along on every status poll.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    goal: str | None = None
    input_url: str
    canonical_url: str
    domain: str

    mode: CrawlMode | None
    state: CrawlState
    docs_root: str | None

    page_count: int
    word_count: int
    bytes_fetched: int
    truncated: bool
    stop_reason: str | None
    failure_reason: str | None
    content_hash: str | None

    crawl_started_at: datetime | None
    crawl_finished_at: datetime | None
    created_at: datetime

    #: What the website means, once read. None until the crawl finishes and
    #: the extraction runs. This is the part the search actually uses.
    profile: dict | None = None


class ProductDetail(ProductOut):
    pages: list[ProductPageOut] = []


class PlanOut(BaseModel):
    """
    The marketing plan, plus whether it still matches the product.

    `stale` is shown rather than acted on: silently rewriting a plan because
    the goal changed would replace something the user may have been working
    from, and costs money without being asked.
    """

    plan: MarketingPlan
    stale: bool = False
    made_at: datetime | None = None
