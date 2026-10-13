"""
Response shapes for the web app.

Separate from `Conversation` on purpose. `Conversation` is what a source
returned and what the pipeline works on; these are what a screen needs. Tying
the two together means every change to one breaks the other, and the frontend
has already been written against these names.

Everything here serialises to camelCase, because that is what the existing
frontend types expect. Requests stay snake_case, which is what it sends.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(word.capitalize() for word in rest)


class Out(BaseModel):
    """Base for anything the frontend reads."""

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True)


# ---------------------------------------------------------------- 1. Brief


class BriefIn(BaseModel):
    """What the form posts. snake_case, matching the frontend's request body."""

    product_name: str = Field(min_length=1, max_length=200)
    product_url: str = ""
    #: Links this brief to a crawled product. When set, the search uses that
    #: product's extracted profile instead of only the typed description -
    #: which is the whole reason the website gets read.
    product_id: str | None = None
    description: str = Field(min_length=1)
    keywords: list[str] = []
    sources: list[str] = ["github"]
    days_back: int = 30


class BriefOut(Out):
    id: str
    product_name: str
    product_url: str
    product_id: str | None = None
    description: str
    keywords: list[str]
    sources: list[str]
    days_back: int
    created_at: datetime
    latest_plan_id: str | None = None
    latest_run_id: str | None = None
    latest_run_state: str | None = None
    result_count: int | None = None


# ---------------------------------------------------------------- 2. Plan


class PlanTerm(Out):
    term: str
    origin: str
    """"user" if they typed it, "expansion" if we added it."""
    reason: str | None = None


class PlanPredicates(Out):
    sources: list[str]
    date_from: str
    date_to: str
    language: str = "en"
    min_engagement: int = 0
    excluded_terms: list[str] = []


class ExamplePost(Out):
    source: str
    title: str
    body: str


class PlanOut(Out):
    id: str
    brief_id: str
    plan_hash: str
    version: int
    terms: list[PlanTerm]
    predicates: PlanPredicates
    stages: list[str]
    estimated_documents: int
    estimated_cost_usd: float
    example_posts: list[ExamplePost]


class AmendIn(BaseModel):
    terms: list[str]


# ---------------------------------------------------------------- 3. Run


class StageProgress(Out):
    id: str
    label: str
    state: str
    """waiting, running, done or skipped."""
    detail: str | None = None


class RunOut(Out):
    id: str
    plan_id: str
    state: str
    stages: list[StageProgress]
    percent: int
    cost_usd: float
    calls_used: int
    call_budget: int
    error: str | None = None


# ---------------------------------------------------------------- Results


class ConversationOut(Out):
    source: str
    url: str
    title: str
    author: str
    created_at: datetime
    engagement: str
    """Pre-formatted for display: "12 comments · 7 reactions"."""


class ScoreComponent(Out):
    name: str
    raw: float
    weight: float
    points: int
    note: str | None = None


class ScoreDetail(Out):
    components: list[ScoreComponent]
    relevance: float
    subtotal: int
    final: int
    explain: str | None = None


class ResultOut(Out):
    id: str
    rank: int
    score: int
    band: str
    conversation: ConversationOut
    problem: str
    actively_looking: bool
    pain_severity: int
    product_fit: float
    evidence_quote: str
    score_detail: ScoreDetail
    feedback: str | None = None
    #: Shown so a wrong domain judgement is visible on the card rather than
    #: buried in a score.
    domain: str | None = None
    intent: str | None = None
    reason: str | None = None


class FeedbackIn(BaseModel):
    useful: bool


class ReplyDraftIn(BaseModel):
    allow_mention: bool = True


class ReplyDraftOut(Out):
    text: str
    mentions_product: bool
