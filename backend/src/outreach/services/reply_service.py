"""
Draft a reply for one post, and start tracking it. Never posts anything.

Sits between the API and `outreach.reply`. Its real job is that drafting and
tracking are the same act: asking for a reply is the first moment a person
judged a post worth answering, and that judgement is the only thing in the
funnel we get for free. Writing the row here rather than on a separate
"track this" button means the tab fills itself.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from outreach import reply as reply_llm
from outreach.db.models.product import Product
from outreach.db.models.tracked_post import TrackedPost, TrackState
from outreach.db.repositories import tracked_posts as repo
from outreach.profile import Profile
from outreach.services import reply_check

log = structlog.get_logger(__name__)


class ReplyError(Exception):
    """Something the user needs to know about, phrased for a person."""


def _product_words(product: Product) -> tuple[str, list[str]]:
    """
    What the model is told the product is.

    Prefers the crawled profile and falls back to what the owner typed. The
    profile is written for matching posts to products, which is exactly the
    job here; the description is what exists before a crawl has finished.
    """
    summary = product.description or ""
    problems: list[str] = []

    if product.profile:
        try:
            profile = Profile(**product.profile)
            summary = profile.summary or summary
            problems = list(profile.problems)
        except Exception:
            log.warning("reply.profile_unreadable", product_id=str(product.id))

    return summary, problems


async def draft_for_post(
    session: AsyncSession,
    product: Product,
    *,
    source: str,
    source_id: str,
    url: str,
    title: str,
    body: str,
    author: str,
    container: str,
    kind: str,
    score: int = 0,
    run_id: str | None = None,
    allow_mention: bool = True,
) -> TrackedPost:
    """
    Write a reply and record the post. Returns the tracked row either way.

    A skip is stored, not discarded. "Do not reply to this, because the
    thread is already solved" is the most valuable thing the model can say,
    and throwing it away means the next search offers the same post again
    with nothing learned.
    """
    summary, problems = _product_words(product)

    try:
        written = await reply_llm.draft(
            title=title,
            body=body,
            author=author,
            container=container,
            kind=kind,
            product_name=product.name,
            product_summary=summary,
            product_problems=problems,
            allow_mention=allow_mention,
        )
    except reply_llm.MentionLeaked as exc:
        # A real, specific failure with an obvious next step, so it must not
        # be flattened into "the model did not answer".
        raise ReplyError(str(exc)) from exc

    if written is None:
        raise ReplyError(
            "Could not write a reply. The model did not answer - try again, "
            "and check OPENAI_API_KEY is set if it keeps happening."
        )

    post = await repo.get_by_source(session, product.id, source, source_id)
    is_new = post is None
    if post is None:
        post = TrackedPost(
            product_id=product.id,
            source=source,
            source_id=source_id,
            first_run_id=run_id,
            score_when_found=score,
            state=TrackState.DRAFTED,
        )

    # Set before the row reaches the database, not after. `url` is NOT NULL,
    # so adding the row first and filling it in afterwards fails on the
    # flush - with the reply already written and paid for.
    post.url = url
    post.title = title[:1024] or None
    post.author = author or None
    post.container = container or None
    post.kind = kind or "issue"

    if is_new:
        await repo.add(session, post)

    post.draft = written.reply or None
    post.draft_version = reply_llm.PROMPT_VERSION
    post.draft_mentions_product = written.mentions_product
    post.drafted_at = datetime.now(UTC)
    post.skip_reason = written.skip_reason or None

    # Only ever moves a post *into* skipped or drafted from the front of the
    # funnel. Re-drafting something already posted must not erase the fact
    # that it was posted - that is the one piece of history the user gave us
    # by hand.
    if post.state in (TrackState.DRAFTED, TrackState.SKIPPED):
        post.state = TrackState.SKIPPED if written.skip_reason else TrackState.DRAFTED

    log.info(
        "reply.tracked",
        product_id=str(product.id),
        source_id=source_id,
        state=post.state.value,
        skipped=bool(written.skip_reason),
    )
    return post


async def mark_posted(
    session: AsyncSession,
    post: TrackedPost,
    *,
    comment_url: str | None,
    thread_comments: int = 0,
) -> TrackedPost:
    """
    Record that the user actually replied.

    `comment_url` is optional but does the real work. A permalink ends
    `#issuecomment-456789`, and that number is what lets a re-check say "two
    people replied *after you*" instead of "this thread has more comments
    than it did", which is true of any busy issue whether we turned up or
    not.
    """
    post.state = TrackState.POSTED
    post.posted_at = datetime.now(UTC)
    post.comments_when_posted = thread_comments
    post.our_comment_url = (comment_url or "").strip() or None
    post.our_comment_id = reply_check.comment_id(post.our_comment_url)
    return post


async def set_outcome(
    session: AsyncSession, post: TrackedPost, outcome: str, note: str | None
) -> TrackedPost:
    """What the reply was worth. Only a person can know this."""
    post.outcome = outcome
    post.outcome_note = (note or "").strip() or None
    return post


async def skip(session: AsyncSession, post: TrackedPost, reason: str) -> TrackedPost:
    """The user decided not to reply. Kept, so the next search knows."""
    post.state = TrackState.SKIPPED
    post.skip_reason = reason.strip() or "Not worth replying to."
    return post


def as_dict(post: TrackedPost) -> dict:
    """The shape the tracking screen reads."""
    return {
        "id": str(post.id),
        "source": post.source,
        "source_id": post.source_id,
        "url": post.url,
        "title": post.title,
        "author": post.author,
        "container": post.container,
        "kind": post.kind,
        "score_when_found": post.score_when_found,
        "state": post.state.value,
        "draft": post.draft,
        "draft_mentions_product": post.draft_mentions_product,
        "drafted_at": post.drafted_at.isoformat() if post.drafted_at else None,
        "skip_reason": post.skip_reason,
        "posted_at": post.posted_at.isoformat() if post.posted_at else None,
        "our_comment_url": post.our_comment_url,
        "replies_after": post.replies_after,
        "author_replied": post.author_replied,
        "last_checked_at": (
            post.last_checked_at.isoformat() if post.last_checked_at else None
        ),
        "outcome": post.outcome.value if post.outcome else None,
        "outcome_note": post.outcome_note,
    }


def uuid_or_none(value: str) -> uuid.UUID | None:
    """A bad id in a URL is a 404, not a 500."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
