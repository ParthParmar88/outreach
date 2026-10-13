"""
The reply funnel: draft, mark posted, record what it was worth.

Every route is scoped to the signed-in account, and ownership is decided
inside the query rather than checked afterwards. A draft is something a
person wrote under their own name; handing one to the wrong account would be
worse than leaking a search result.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from outreach import planner
from outreach.api.deps import CurrentUser, DbSession
from outreach.db.models.tracked_post import Outcome
from outreach.db.repositories import products as product_repo
from outreach.db.repositories import tracked_posts as repo
from outreach.services import reply_check, reply_service

router = APIRouter(tags=["tracking"])

#: Same message whether it does not exist or belongs to somebody else.
NOT_FOUND = "No tracked post with that id."


class DraftIn(BaseModel):
    """Everything about the post, taken from the search result on screen."""

    #: The platform the post is on, as the run named it. Required: this was
    #: `= "github"`, the frontend never sent it, and every Hacker News reply
    #: was counted on the GitHub row of the activity page.
    source: str
    source_id: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)
    title: str = ""
    #: The post's own text. The results screen has the quote but not the full
    #: body, so this may be short - the prompt is written to cope.
    body: str = ""
    author: str = ""
    container: str = ""
    kind: str = "issue"
    score: int = 0
    run_id: str | None = None

    #: Whether the reply may name the product. Off gives a purely helpful
    #: answer, which is often the right first move in a repository nobody
    #: there has heard of you.
    allow_mention: bool = True


@router.post("/products/{product_id}/tracking/draft", status_code=status.HTTP_201_CREATED)
async def draft_reply(
    product_id: uuid.UUID,
    payload: DraftIn,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    """
    Write a reply to one post and start tracking it.

    Takes 5 to 15 seconds. Synchronous on purpose, unlike the crawl and the
    plan: the user is looking at the post and waiting for the words, so a
    background job plus polling would add machinery and no benefit.
    """
    product = await product_repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No product with that id.")

    # Before the reply is written, which is the part that costs money.
    if payload.source not in planner.SEARCHABLE:
        known = ", ".join(sorted(planner.SEARCHABLE))
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown source {payload.source!r}. Expected one of: {known}.",
        )

    try:
        post = await reply_service.draft_for_post(
            session,
            product,
            source=payload.source,
            source_id=payload.source_id,
            url=payload.url,
            title=payload.title,
            body=payload.body,
            author=payload.author,
            container=payload.container,
            kind=payload.kind,
            score=payload.score,
            run_id=payload.run_id,
            allow_mention=payload.allow_mention,
        )
    except reply_service.ReplyError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    await session.commit()
    return reply_service.as_dict(post)


@router.get("/products/{product_id}/tracking")
async def list_tracking(
    product_id: uuid.UUID, user: CurrentUser, session: DbSession
) -> dict:
    """
    The funnel counts and the tracked posts behind them.

    Counts come from SQL over every row; the list is capped. A funnel that
    silently stopped counting at the display limit would be worse than no
    funnel at all.
    """
    product = await product_repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No product with that id.")

    counts = await repo.funnel(session, product_id)
    rows = await repo.list_for_product(session, product_id)
    return {
        "funnel": counts,
        "posts": [reply_service.as_dict(row) for row in rows],
    }


@router.post("/tracking/check-replies")
async def check_replies(user: CurrentUser, product_id: uuid.UUID | None = None) -> dict:
    """
    Look at posted replies' threads again, and mark the answered ones.

    Called by the screens that show the funnel when they open, for one
    product or the whole account. Cheap to call often: a post is fetched at
    most once every few minutes however many times this runs. `changed`
    tells the screen whether its numbers are now out of date.
    """
    return await reply_check.check_due(user.id, product_id)


class PostedIn(BaseModel):
    #: The permalink to your own comment, ending `#issuecomment-456789`.
    #: Optional, and the difference between a real answer and a guess.
    comment_url: str | None = Field(default=None, max_length=2048)
    #: How many comments the thread had when you posted.
    thread_comments: int = 0


@router.post("/tracking/{tracked_id}/posted")
async def mark_posted(
    tracked_id: uuid.UUID,
    payload: PostedIn,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    """Record that you actually replied. We never post anything ourselves."""
    post = await repo.get_owned(session, tracked_id, user.id)
    if post is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    await reply_service.mark_posted(
        session,
        post,
        comment_url=payload.comment_url,
        thread_comments=payload.thread_comments,
    )
    await session.commit()
    return reply_service.as_dict(post)


class OutcomeIn(BaseModel):
    outcome: Outcome
    note: str | None = Field(default=None, max_length=2000)


@router.post("/tracking/{tracked_id}/outcome")
async def set_outcome(
    tracked_id: uuid.UUID,
    payload: OutcomeIn,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    """
    What the reply was worth. The only number here that means anything.

    Everything else in the funnel is a leading indicator we get for free.
    This one costs a click, and it is the one a person can defend.
    """
    post = await repo.get_owned(session, tracked_id, user.id)
    if post is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    await reply_service.set_outcome(session, post, payload.outcome, payload.note)
    await session.commit()
    return reply_service.as_dict(post)


class SkipIn(BaseModel):
    reason: str = Field(default="", max_length=2000)


@router.post("/tracking/{tracked_id}/skip")
async def skip(
    tracked_id: uuid.UUID, payload: SkipIn, user: CurrentUser, session: DbSession
) -> dict:
    """
    Decide not to reply. Kept rather than deleted, so a later search knows
    this one was already looked at and turned down.
    """
    post = await repo.get_owned(session, tracked_id, user.id)
    if post is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    await reply_service.skip(session, post, payload.reason)
    await session.commit()
    return reply_service.as_dict(post)
