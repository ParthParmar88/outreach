"""
Tests for the reply check - the only thing that ever marks a post answered.

It used to not exist: the funnel had an `answered` stage, the activity page
counted it, and nothing went back to a thread to look. Pinned here are the
two judgements that are easy to get quietly wrong: which comment is yours,
and what counts as somebody answering it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from outreach.db.models.tracked_post import TrackedPost, TrackState
from outreach.services import reply_check as rc
from outreach.services.reply_check import Comment

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

DRAFT = (
    "We hit the same cache invalidation problem when the retriever returned "
    "documents in a different order each call. Sorting the chunks by id before "
    "building the prompt made the prefix stable, and cache hits went from "
    "almost none to most requests."
)


def _c(id: str, author: str | None, minutes: int, text: str = "", parent: str | None = None):
    return Comment(
        id=id,
        author=author,
        created_at=T0 + timedelta(minutes=minutes),
        text=text,
        url=f"https://example.com/{id}",
        parent_id=parent,
    )


def _post(**overrides) -> TrackedPost:
    base = dict(
        id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        source="github",
        source_id="I_kw1",
        url="https://github.com/o/r/issues/7",
        author="asker",
        kind="issue",
        state=TrackState.POSTED,
        draft=DRAFT,
        drafted_at=T0,
        posted_at=T0 + timedelta(minutes=5),
        our_comment_url=None,
        our_comment_id=None,
        replies_after=0,
        author_replied=False,
        last_checked_at=None,
    )
    base.update(overrides)
    return TrackedPost(**base)


# ------------------------------------------------------------ comment ids


def test_comment_ids_from_every_kind_of_link():
    assert rc.comment_id("https://github.com/o/r/issues/7#issuecomment-456789") == "456789"
    assert rc.comment_id("https://github.com/o/r/discussions/3#discussioncomment-99") == "99"
    # A Hacker News comment's permalink is its own item page. This used to
    # come back None, so no Hacker News reply could ever be attributed.
    assert rc.comment_id("https://news.ycombinator.com/item?id=41234567") == "41234567"
    assert rc.comment_id("https://github.com/o/r/issues/7") is None
    assert rc.comment_id("") is None
    assert rc.comment_id(None) is None


# --------------------------------------------------------- finding yours


def test_a_lightly_edited_draft_is_still_yours():
    posted = DRAFT.replace("We hit", "Hi! We ran into").replace(", and cache", ". Cache")
    assert rc.likeness(posted, DRAFT) >= rc.MATCH_AT


def test_an_unrelated_comment_is_not_yours():
    other = "Have you tried upgrading to the latest release? This was fixed in 0.12."
    assert rc.likeness(other, DRAFT) < rc.MATCH_AT


def test_a_short_comment_never_matches():
    assert rc.likeness("same problem here", "same problem here") == 0.0


def test_somebody_quoting_you_does_not_become_you():
    quoted = f"> {DRAFT}\n\nThis worked for us too, thanks."
    comments = [_c("1", "me", 10, DRAFT), _c("2", "stranger", 20, quoted)]
    assert rc.find_ours(comments, our_id=None, draft=DRAFT).id == "1"


def test_the_link_you_gave_beats_the_wording():
    comments = [_c("1", "me", 10, DRAFT), _c("2", "me", 20, "a different comment")]
    assert rc.find_ours(comments, our_id="2", draft=DRAFT).id == "2"


# ------------------------------------------------------ who answered you


def test_github_counts_other_people_after_you():
    comments = [
        _c("1", "asker", 0, "original question follow-up"),
        _c("2", "me", 10, DRAFT),
        _c("3", "me", 12, "and one more thing"),  # you, again
        _c("4", "github-actions[bot]", 13, "stale"),  # a bot
        _c("5", "stranger", 30, "thanks"),
        _c("6", "Asker", 40, "that fixed it"),
    ]
    verdict = rc.judge(comments, our_id="2", draft=None, post_author="asker", threaded=False)

    assert [c.id for c in verdict.replies] == ["5", "6"]
    # Case-insensitive: GitHub logins are.
    assert verdict.author_replied is True


def test_hacker_news_counts_only_replies_under_yours():
    """A busy story's other comments are not answers to you."""
    comments = [
        _c("100", "poster", 0, "story"),
        _c("101", "me", 10, DRAFT, parent="100"),
        _c("102", "stranger", 11, "unrelated top-level", parent="100"),
        _c("103", "someone", 20, "reply to you", parent="101"),
        _c("104", "me", 25, "my answer back", parent="103"),
        _c("105", "poster", 30, "reply to the reply", parent="104"),
    ]
    verdict = rc.judge(comments, our_id="101", draft=None, post_author="poster", threaded=True)

    assert sorted(c.id for c in verdict.replies) == ["103", "105"]
    assert verdict.author_replied is True


def test_no_verdict_when_your_comment_is_not_there():
    comments = [_c("1", "stranger", 10, "nothing like the draft at all, really not")]
    assert rc.judge(comments, our_id=None, draft=DRAFT, post_author="a", threaded=False) is None


# ------------------------------------------------------ writing it down


def test_a_reply_moves_posted_to_answered():
    post = _post()
    verdict = rc.Verdict(ours=_c("2", "me", 10), replies=[_c("5", "x", 30)], author_replied=False)

    assert rc.apply(post, verdict, T0) is True
    assert post.state == TrackState.ANSWERED
    assert post.replies_after == 1
    assert post.last_checked_at == T0
    # Found by wording: the row now knows which comment is yours.
    assert post.our_comment_id == "2"
    assert post.our_comment_url == "https://example.com/2"


def test_no_replies_leaves_it_posted():
    post = _post()
    verdict = rc.Verdict(ours=_c("2", "me", 10), replies=[], author_replied=False)

    rc.apply(post, verdict, T0)
    assert post.state == TrackState.POSTED


def test_not_finding_yours_changes_nothing_but_the_check_time():
    """Counting new comments instead would mark every busy thread answered."""
    post = _post()
    assert rc.apply(post, None, T0) is False
    assert post.state == TrackState.POSTED
    assert post.replies_after == 0
    assert post.last_checked_at == T0


def test_a_pasted_link_is_not_overwritten():
    post = _post(our_comment_url="https://github.com/o/r/issues/7#issuecomment-2")
    verdict = rc.Verdict(ours=_c("2", "me", 10), replies=[], author_replied=False)

    rc.apply(post, verdict, T0)
    assert post.our_comment_url == "https://github.com/o/r/issues/7#issuecomment-2"


# ------------------------------------------------------------- fetching


def _gh(id: int, login: str, minutes: int, body: str = "") -> dict:
    return {
        "id": id,
        "user": {"login": login},
        "created_at": (T0 + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"),
        "body": body,
        "html_url": f"https://github.com/o/r/issues/7#issuecomment-{id}",
    }


@respx.mock
async def test_github_issue_found_by_draft_and_answered():
    route = respx.get("https://api.github.com/repos/o/r/issues/7/comments").mock(
        return_value=httpx.Response(
            200,
            json=[
                _gh(1, "stranger", -60, "old"),
                _gh(2, "me", 10, DRAFT),
                _gh(3, "asker", 40, "ty"),
            ],
        )
    )
    post = _post()

    async with httpx.AsyncClient() as client:
        verdict = await rc.check_post(client, post)

    # Only comments since the draft (less a day of slack) were asked for.
    assert route.calls.last.request.url.params["since"].startswith("2026-08-31")
    assert verdict.ours.id == "2"
    assert [c.id for c in verdict.replies] == ["3"]
    assert verdict.author_replied is True


def _hn(id: int, author: str, minutes: int, text: str = "", children=()) -> dict:
    return {
        "id": id,
        "author": author,
        "created_at_i": int((T0 + timedelta(minutes=minutes)).timestamp()),
        "text": text,
        "children": list(children),
    }


@respx.mock
async def test_hacker_news_with_your_link_fetches_only_your_comment():
    route = respx.get("https://hn.algolia.com/api/v1/items/501").mock(
        return_value=httpx.Response(
            200, json=_hn(501, "me", 10, DRAFT, [_hn(502, "poster", 20, "good point")])
        )
    )
    post = _post(
        source="hackernews",
        source_id="500",
        url="https://news.ycombinator.com/item?id=500",
        author="poster",
        kind="story",
        our_comment_url="https://news.ycombinator.com/item?id=501",
    )

    async with httpx.AsyncClient() as client:
        verdict = await rc.check_post(client, post)

    assert route.called
    assert [c.id for c in verdict.replies] == ["502"]
    assert verdict.author_replied is True


@respx.mock
async def test_hacker_news_without_a_link_finds_the_draft_in_the_story():
    story = _hn(
        500,
        "poster",
        0,
        "",
        [
            _hn(
                510,
                "busy",
                11,
                "<p>Totally unrelated thought about the article.</p>",
                [_hn(511, "other", 12, "agreed")],
            ),
            _hn(520, "me", 10, "<p>" + DRAFT.replace("'", "&#x27;") + "</p>"),
        ],
    )
    respx.get("https://hn.algolia.com/api/v1/items/500").mock(
        return_value=httpx.Response(200, json=story)
    )
    post = _post(
        source="hackernews",
        source_id="500",
        url="https://news.ycombinator.com/item?id=500",
        author="poster",
        kind="story",
    )

    async with httpx.AsyncClient() as client:
        verdict = await rc.check_post(client, post)

    assert verdict.ours.id == "520"
    # The busy thread next door is not an answer to you.
    assert verdict.replies == []


@respx.mock
async def test_rate_limit_stops_instead_of_waiting():
    respx.get("https://api.github.com/repos/o/r/issues/7/comments").mock(
        return_value=httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(rc.RateLimited):
            await rc.check_post(client, _post())
