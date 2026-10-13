"""
Tests for the Hacker News connector.

Weighted towards the two things that silently produce a bad run rather than
an error: the query rendering, which returns nothing when it is too strict,
and the story/comment mapping, where the two shapes share almost no fields.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from outreach.connectors import hackernews as hn
from outreach.planner import _clean_term

SEARCH = "https://hn.algolia.com/api/v1/search"


def _story(**overrides) -> dict:
    hit = {
        "objectID": "48592015",
        "title": "Prompt caching breaks with RAG retrieval",
        "url": "https://example.com/post",
        "author": "someone",
        "points": 42,
        "num_comments": 17,
        "created_at": "2026-08-01T10:00:00Z",
        "created_at_i": 1785535200,
        "_tags": ["story", "author_someone"],
    }
    hit.update(overrides)
    return hit


def _comment(**overrides) -> dict:
    hit = {
        "objectID": "48592099",
        "comment_text": "<p>our bill tripled because we re-embed everything</p>",
        "author": "someone",
        "story_id": 48592015,
        "story_title": "Ask HN: how do you cache context?",
        "parent_id": 48592016,
        "points": None,
        "created_at": "2026-08-02T10:00:00Z",
        "_tags": ["comment"],
    }
    hit.update(overrides)
    return hit


def _page(hits: list[dict], *, nb_pages: int = 1, nb_hits: int | None = None) -> dict:
    return {
        "hits": hits,
        "nbHits": nb_hits if nb_hits is not None else len(hits),
        "nbPages": nb_pages,
        "page": 0,
    }


# ---------------------------------------------------------------- queries


def test_terms_are_not_quoted():
    """
    The measurement this connector was corrected by.

    Quoting makes an exact-phrase match, which narrows usefully on GitHub's
    millions of issues and returns nothing on Algolia's much smaller index.
    Four of one plan's six terms matched zero results quoted.
    """
    params = hn.build_query("context management issues", days=90, tag="comment")
    assert '"' not in params["query"]
    assert params["query"] == "context management issues"


def test_the_intersection_still_means_both():
    """`+` has to mean the same thing wherever a plan runs it."""
    params = hn.build_query("prompt caching + RAG", days=90, tag="story")
    assert params["query"] == "prompt caching RAG"


def test_the_date_window_reaches_the_query():
    params = hn.build_query("cache", days=30, tag="story")
    assert params["numericFilters"].startswith("created_at_i>")


def test_both_stories_and_comments_are_asked_for():
    """
    Searching stories alone throws away most of Hacker News: a story is a
    link somebody posted, and the person with the problem is in the replies.
    """
    tags = {params["tags"] for _, params in hn.build_queries(["prompt caching"])}
    assert tags == {"story", "comment"}


def test_an_empty_term_produces_no_query():
    assert hn.build_queries(["", "   "]) == []


# ---------------------------------------------------------------- mapping


def test_a_story_becomes_a_conversation():
    c = hn.to_conversation(_story())

    assert c is not None
    assert c.source == "hackernews"
    assert c.kind == "story"
    assert c.score == 42
    assert c.comments == 17
    # The item on Hacker News, never the link it pointed at: somebody
    # replying needs the thread, not the article.
    assert c.url == "https://news.ycombinator.com/item?id=48592015"
    assert c.container == "example.com"


def test_a_comment_becomes_a_conversation():
    c = hn.to_conversation(_comment())

    assert c is not None
    assert c.kind == "comment"
    # The thread it sits in, which is what makes a stray remark readable.
    assert c.container == "Ask HN: how do you cache context?"
    assert c.url == "https://news.ycombinator.com/item?id=48592099"


def test_comment_html_is_turned_into_text():
    c = hn.to_conversation(
        _comment(comment_text="<p>we&#x27;re paying twice</p><p>for the same tokens</p>")
    )

    assert c is not None
    assert "<p>" not in c.body
    assert "&#x27;" not in c.body
    assert "we're paying twice" in c.body


def test_a_comment_scores_zero_rather_than_borrowing_the_story():
    """
    Algolia reports `points: null` for every comment. Inventing a score
    would make a comment look popular on evidence that does not exist.
    """
    c = hn.to_conversation(_comment())
    assert c is not None and c.score == 0


def test_an_ask_hn_post_with_no_link_says_so():
    c = hn.to_conversation(
        _story(url=None, _tags=["story", "ask_hn"], story_text="how do you do this?")
    )
    assert c is not None and c.container == "Ask HN"


def test_a_deleted_comment_is_dropped():
    """Algolia keeps the row; there is nothing for a model to judge."""
    assert hn.to_conversation(_comment(comment_text="")) is None


def test_unusable_hits_return_none_rather_than_raising():
    assert hn.to_conversation({}) is None
    assert hn.to_conversation(_story(objectID="")) is None
    assert hn.to_conversation(_story(created_at="not a date")) is None


# ---------------------------------------------------------------- fetching


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_both_kinds():
    respx.get(SEARCH).mock(
        return_value=httpx.Response(200, json=_page([_story(), _comment()]))
    )

    result = await hn.search(["prompt caching"], max_requests=2)

    kinds = {c.kind for c in result.conversations}
    assert kinds == {"story", "comment"}


@pytest.mark.asyncio
@respx.mock
async def test_the_same_item_is_not_returned_twice():
    """Story and comment queries overlap; the id is what settles it."""
    respx.get(SEARCH).mock(return_value=httpx.Response(200, json=_page([_story()])))

    result = await hn.search(["prompt caching"], max_requests=4)

    assert len(result.conversations) == 1


@pytest.mark.asyncio
@respx.mock
async def test_quiet_stories_are_dropped_but_comments_never_are():
    """
    A two-point story sank without trace. A comment has no points *at all*
    in this index, so filtering comments on the same number would delete
    the better half of the source.
    """
    respx.get(SEARCH).mock(
        return_value=httpx.Response(
            200, json=_page([_story(points=1), _comment(objectID="99")])
        )
    )

    result = await hn.search(["prompt caching"], max_requests=2, min_story_points=3)

    kinds = [c.kind for c in result.conversations]
    assert "story" not in kinds
    assert "comment" in kinds


@pytest.mark.asyncio
@respx.mock
async def test_the_request_budget_is_respected():
    respx.get(SEARCH).mock(
        return_value=httpx.Response(200, json=_page([_story()], nb_pages=9))
    )

    result = await hn.search(["a", "b", "c"], max_requests=2)

    assert result.requests_made == 2
    assert any("request limit" in note for note in result.notes)


@pytest.mark.asyncio
@respx.mock
async def test_a_failing_query_does_not_lose_the_others():
    respx.get(SEARCH).mock(
        side_effect=[
            httpx.Response(400, text="bad"),
            httpx.Response(200, json=_page([_story()])),
            httpx.Response(200, json=_page([_comment()])),
            httpx.Response(200, json=_page([])),
        ]
    )

    result = await hn.search(["first", "second"], max_requests=4)

    assert len(result.conversations) >= 1
    assert any("failed" in note for note in result.notes)


@pytest.mark.asyncio
async def test_no_terms_costs_nothing():
    result = await hn.search([])
    assert result.requests_made == 0
    assert result.conversations == []


# ------------------------------------------------------- term shape guard


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        # A broad half narrows nothing, so it is stripped and the real
        # concept kept rather than the whole term thrown away.
        ("response time + AI", "response time"),
        ("data updates + AI", "data updates"),
        ("context cache + agents", "context cache"),
        # Two real concepts survive untouched.
        ("prompt caching + RAG", "prompt caching + RAG"),
        ("semantic cache + cost", "semantic cache + cost"),
        # Nothing left to narrow on.
        ("AI + LLM", None),
        ("data + models", None),
    ],
)
def test_broad_halves_are_stripped(term, expected):
    """
    Two prompt revisions asked for this and two plans ignored it, which is
    the usual sign a rule belongs in code rather than in a prompt.
    """
    assert _clean_term(term) == expected

# --------------------------------------------------- what a comment is called


def test_a_comment_is_titled_by_what_it_says():
    """
    The bug this exists for.

    Algolia gives a comment `story_title` and nothing else title-shaped, so
    using it looks reasonable and quietly breaks the triage: that stage
    reads *only* titles, so every comment in a thread arrives as the same
    string and what the person wrote is invisible to the one step deciding
    whether anybody reads it.
    """
    c = hn.to_conversation(
        _comment(comment_text="<p>our bill tripled because we re-embed everything</p>")
    )

    assert c is not None
    assert c.title == "our bill tripled because we re-embed everything"
    # The thread is context for the remark, not the remark.
    assert c.container == "Ask HN: how do you cache context?"
    assert c.title != c.container


def test_a_story_still_keeps_its_own_title():
    c = hn.to_conversation(_story())
    assert c is not None
    assert c.title == "Prompt caching breaks with RAG retrieval"


def test_a_long_comment_is_cut_at_a_sentence():
    body = "We cache the prefix now. " + "Then a great deal more text follows. " * 8
    c = hn.to_conversation(_comment(comment_text=body))

    assert c is not None
    assert c.title == "We cache the prefix now."


def test_a_comment_with_no_sentence_break_is_cut_cleanly():
    c = hn.to_conversation(_comment(comment_text="word " * 100))

    assert c is not None
    assert len(c.title) <= hn.HEADLINE_CHARS + 3
    # Cut at a space, never mid-word.
    assert c.title.endswith("...")
    assert "  " not in c.title


@pytest.mark.parametrize(
    "thread",
    [
        "Ask HN: Who wants to be hired? (June 2026)",
        "Ask HN: Who is hiring? (September 2026)",
        "Ask HN: Freelancer? Seeking Freelancer? (August 2026)",
        "[dead]",
    ],
)
def test_hiring_megathreads_are_dropped(thread):
    """
    Hundreds of people listing every technology they have touched. A comment
    there says "LLM", "agents" and "caching" because somebody is describing
    a career, so it matches any plan and crowds out real results.
    """
    assert hn.to_conversation(_comment(story_title=thread)) is None


@pytest.mark.parametrize(
    "thread",
    [
        "Ask HN: how do you cache context?",
        "Ask HN: Who owns the output of an LLM?",
        "Show HN: BetterDB",
    ],
)
def test_ordinary_ask_hn_threads_are_kept(thread):
    """The filter is about four recurring megathreads, not Ask HN itself."""
    assert hn.to_conversation(_comment(story_title=thread)) is not None

# ----------------------------------------------- how fast each source ages


def test_hacker_news_ages_far_faster_than_github():
    """
    One half-life for both was a GitHub number applied to Hacker News.

    An open GitHub issue from a month ago is still live - in the tracker,
    subscribed to, and a reply gets read. A Hacker News thread is finished
    within days of leaving the front page, so the same 0.50 at thirty days
    made a dead thread look half as good as a live one.
    """
    from datetime import UTC, datetime, timedelta

    from outreach import score
    from outreach.schemas.conversation import Conversation

    now = datetime.now(UTC)

    def fresh(source: str, days: int) -> float:
        return score._freshness(
            Conversation(
                source=source,
                source_id="x",
                url="u",
                created_at=now - timedelta(days=days),
            ),
            now,
        )

    # A month old: still half-worth on GitHub, effectively gone on HN.
    assert fresh("github", 30) > 0.45
    assert fresh("hackernews", 30) < 0.10

    # And the days that matter on HN are actually separated.
    assert fresh("hackernews", 3) - fresh("hackernews", 7) > 0.2


def test_an_unknown_source_gets_the_middle_rather_than_a_crash():
    """A connector added tomorrow must score, not raise."""
    from datetime import UTC, datetime, timedelta

    from outreach import score
    from outreach.schemas.conversation import Conversation

    now = datetime.now(UTC)
    value = score._freshness(
        Conversation(
            source="reddit", source_id="x", url="u", created_at=now - timedelta(days=21)
        ),
        now,
    )
    assert 0.4 < value < 0.6


def test_each_source_is_searched_over_its_own_window():
    """
    48% of one run's Hacker News candidates were 31-90 days old - fetched,
    embedded and competing for triage slots against posts somebody could
    still answer.
    """
    from outreach.services.opportunity_service import SEARCH_DAYS

    assert SEARCH_DAYS["hackernews"] < SEARCH_DAYS["github"]


def test_hacker_news_never_triages_fewer_titles_than_github():
    """
    Measured, not assumed. Same 297 Hacker News candidates:

        pool 25   ->   3 clear, best result 20
        pool all  ->  16 clear, best result 36

    Hacker News has no rooms - every candidate is a broad phrase match ranked
    on a comment's first line, so position 200 is no worse a bet than
    position 20.

    GitHub was expected to manage on 25, because repository sweeps come from
    rooms chosen on purpose. Measured later, it did not: the same 2,434
    candidates gave 1 clear match at 25 and 14 at 300. So GitHub's number now
    follows the setting, and this only holds the two in the right order.
    """
    from outreach.config import settings
    from outreach.services.opportunity_service import TRIAGE_POOL

    github = TRIAGE_POOL.get("github", settings.triage_pool)
    hn = TRIAGE_POOL.get("hackernews", settings.triage_pool)

    # 0 means "all", so it is not simply a larger number.
    assert hn == 0 or (github != 0 and hn >= github)
    assert github == settings.triage_pool


def test_hacker_news_gets_its_own_request_budget():
    """
    The shared budget was rationing a free service.

    A real run ended with `stopped at the 15 request limit with 1 query still
    having more to give`, and the lead it was reaching for - an Ask HN post
    scoring 36 the week before - was not in what came back.
    """
    from outreach.services.opportunity_service import (
        HN_MAX_REQUESTS,
        MIN_REQUESTS,
        _budget,
        _hn_budget,
    )

    terms = [f"term {i}" for i in range(7)]

    # Every term is two queries here, stories and comments, so the same plan
    # needs more requests than GitHub's arithmetic gives it.
    assert _hn_budget(terms) > _budget(terms, [])
    assert _hn_budget(terms) == 28

    assert _hn_budget(["one"]) == MIN_REQUESTS  # the floor still holds
    assert _hn_budget([f"t{i}" for i in range(50)]) == HN_MAX_REQUESTS


def test_a_wider_search_does_not_cost_more_tokens():
    """
    The point of the pool cap: fetch more, read the same.

    Embedding a post is a fraction of what reading its title costs, so the
    fetch can triple while the number of model calls stays where it was.
    """
    import math

    from outreach.classify import TRIAGE_BATCH
    from outreach.services.opportunity_service import TRIAGE_POOL

    pool = TRIAGE_POOL["hackernews"]
    assert pool, "an uncapped pool turns a wider fetch straight into more calls"

    # Whatever comes back from Algolia, this many triage requests and no more.
    assert math.ceil(pool / TRIAGE_BATCH) <= 15


def test_the_planner_is_told_what_hacker_news_terms_return():
    """
    The old advice was measured wrong, and produced `prefix stability`: a
    term of art from a datasheet that matches nothing anybody has written.
    """
    from outreach import planner

    text = planner.PROMPT_PATH.read_text(encoding="utf-8")

    assert "prefix stability" in text
    assert "the words people complain in" in text
    assert "competing products as terms" in text
