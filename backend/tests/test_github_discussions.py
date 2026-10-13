"""
Tests for the Discussions connector.

Weighted towards the two things that would silently break it rather than
towards coverage: the query qualifiers, which return zero results when wrong
rather than an error, and GraphQL's habit of reporting failure with HTTP 200.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from outreach.config import settings
from outreach.connectors import github_discussions as gd

GRAPHQL = "https://api.github.com/graphql"


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    """Every test but one wants a token present."""
    monkeypatch.setattr(settings, "github_token", "test-token")


def _node(**overrides) -> dict:
    node = {
        "id": "D_kwDOABCD",
        "title": "Prompt caching incompatibility with RAG document retrieval",
        "body": "Retrieved context changes every request so the cache never hits.",
        "url": "https://github.com/open-webui/open-webui/discussions/18899",
        "createdAt": "2026-08-01T10:00:00Z",
        "upvoteCount": 7,
        "isAnswered": False,
        "authorAssociation": "NONE",
        "author": {"login": "someone", "__typename": "User"},
        "category": {"name": "Q&A"},
        "comments": {"totalCount": 4},
        "reactions": {"totalCount": 3},
        "labels": {"nodes": [{"name": "rag"}, {"name": "enhancement"}]},
        "repository": {
            "nameWithOwner": "open-webui/open-webui",
            "stargazerCount": 90_000,
            "isArchived": False,
        },
    }
    node.update(overrides)
    return node


def _page(nodes: list[dict], *, has_next: bool = False, total: int | None = None) -> dict:
    return {
        "data": {
            "search": {
                "discussionCount": total if total is not None else len(nodes),
                "pageInfo": {"hasNextPage": has_next, "endCursor": "CURSOR"},
                "nodes": nodes,
            }
        }
    }


# ---------------------------------------------------------------- queries


def test_query_omits_issue_and_state_qualifiers():
    """
    The whole point of a separate builder.

    `is:issue` matches no discussion, and `is:open` would drop resolved
    threads that are still good places to reply. Both come back empty rather
    than erroring, so nothing else would catch this.
    """
    query = gd.build_query("prompt caching", days=30)

    assert "is:issue" not in query
    assert "is:open" not in query
    assert "is:closed" not in query
    assert '"prompt caching"' in query
    assert "created:>=" in query


def test_multi_word_phrase_is_quoted_single_word_is_not():
    assert '"prompt caching"' in gd.build_query("prompt caching")
    single = gd.build_query("reindex")
    assert "reindex" in single and '"reindex"' not in single


def test_query_stays_within_the_length_limit():
    query = gd.build_query(
        "a fairly long phrase that goes on",
        repo="some-org/some-really-long-repository-name",
        days=365,
        exclude=["one exclusion", "another exclusion", "a third exclusion"],
    )
    assert len(query) <= gd.MAX_QUERY_CHARS


def test_phrase_survives_trimming():
    """Filters are dropped to fit; the phrase never is."""
    query = gd.build_query(
        "cache invalidation",
        repo="x" * 100 + "/" + "y" * 100,
        exclude=["z" * 60],
    )
    assert '"cache invalidation"' in query


def test_repo_queries_carry_no_phrase():
    queries = dict(
        (label, q)
        for label, q in gd.build_queries(["one"], repos=["run-llama/llama_index"])
    )
    sweep = queries["repo: run-llama/llama_index"]
    assert "repo:run-llama/llama_index" in sweep
    assert '"one"' not in sweep


def test_duplicate_queries_are_collapsed():
    queries = gd.build_queries(["same", "same", "  same  "])
    assert len(queries) == 1


# ---------------------------------------------------------------- mapping


def test_node_becomes_a_conversation():
    conversation = gd.to_conversation(_node())

    assert conversation is not None
    assert conversation.source == "github"
    assert conversation.kind == "discussion"
    assert conversation.container == "open-webui/open-webui"
    assert conversation.category == "Q&A"
    assert conversation.is_answered is False
    assert conversation.comments == 4
    # Upvotes and reactions are separate affordances, so both count.
    assert conversation.score == 10
    assert conversation.labels == ["rag", "enhancement"]
    assert conversation.author_association == "NONE"
    assert conversation.created_at.tzinfo is not None


def test_unanswerable_discussion_keeps_none_rather_than_false():
    """
    None means "not a question", False means "a question nobody answered".

    Collapsing them would throw away the best signal discussions carry.
    """
    conversation = gd.to_conversation(_node(isAnswered=None))
    assert conversation is not None
    assert conversation.is_answered is None


def test_bot_authors_are_marked():
    by_typename = gd.to_conversation(
        _node(author={"login": "helper", "__typename": "Bot"})
    )
    by_login = gd.to_conversation(
        _node(author={"login": "dependabot[bot]", "__typename": "User"})
    )
    assert by_typename is not None and by_typename.author_is_bot
    assert by_login is not None and by_login.author_is_bot


def test_unusable_nodes_return_none_rather_than_raising():
    assert gd.to_conversation({}) is None
    assert gd.to_conversation(_node(url=None)) is None
    assert gd.to_conversation(_node(createdAt="not a date")) is None


def test_missing_author_is_survivable():
    """A deleted account arrives as a null author, not a missing key."""
    conversation = gd.to_conversation(_node(author=None))
    assert conversation is not None
    assert conversation.author is None


# ---------------------------------------------------------------- fetching


@pytest.mark.asyncio
@respx.mock
async def test_search_returns_discussions():
    respx.post(GRAPHQL).mock(return_value=httpx.Response(200, json=_page([_node()])))

    result = await gd.search(["prompt caching"], days=30)

    assert len(result.conversations) == 1
    assert result.conversations[0].kind == "discussion"
    assert result.requests_made == 1


@pytest.mark.asyncio
@respx.mock
async def test_no_token_is_a_clear_refusal_not_an_empty_result(monkeypatch):
    """
    Zero results and "we never looked" must not be indistinguishable.

    GraphQL 401s without a token where REST search would have served
    anonymously, so this is the one failure a user will hit by accident.
    """
    monkeypatch.setattr(settings, "github_token", "")

    with pytest.raises(gd.DiscussionsUnavailable, match="GITHUB_TOKEN"):
        await gd.search(["anything"])


@pytest.mark.asyncio
@respx.mock
async def test_graphql_errors_arrive_with_http_200():
    """The trap this connector exists to avoid falling into."""
    respx.post(GRAPHQL).mock(
        return_value=httpx.Response(
            200,
            json={"errors": [{"type": "INVALID", "message": "bad qualifier"}]},
        )
    )

    result = await gd.search(["broken"])

    assert result.conversations == []
    assert any("bad qualifier" in note for note in result.notes)


@pytest.mark.asyncio
@respx.mock
async def test_partial_data_alongside_errors_is_kept():
    payload = _page([_node()])
    payload["errors"] = [{"type": "FORBIDDEN", "message": "one repo was private"}]
    respx.post(GRAPHQL).mock(return_value=httpx.Response(200, json=payload))

    result = await gd.search(["prompt caching"])

    assert len(result.conversations) == 1


@pytest.mark.asyncio
@respx.mock
async def test_bad_token_names_itself():
    respx.post(GRAPHQL).mock(return_value=httpx.Response(401, json={}))

    with pytest.raises(gd.DiscussionsUnavailable, match="rejected the token"):
        await gd.search(["anything"])


@pytest.mark.asyncio
@respx.mock
async def test_one_failing_query_does_not_lose_the_others():
    good = _page([_node()])
    bad = {"errors": [{"type": "INVALID", "message": "nope"}]}
    respx.post(GRAPHQL).mock(
        side_effect=[
            httpx.Response(200, json=bad),
            httpx.Response(200, json=good),
        ]
    )

    result = await gd.search(["first", "second"])

    assert len(result.conversations) == 1


@pytest.mark.asyncio
@respx.mock
async def test_paging_follows_the_cursor_and_stops():
    first = _page([_node(id="D_1")], has_next=True)
    second = _page([_node(id="D_2")], has_next=False)
    route = respx.post(GRAPHQL).mock(
        side_effect=[
            httpx.Response(200, json=first),
            httpx.Response(200, json=second),
        ]
    )

    result = await gd.search(["prompt caching"])

    assert len(result.conversations) == 2
    assert route.call_count == 2
    # The second request must carry the cursor the first handed back.
    assert route.calls[1].request.read().decode().count("CURSOR") == 1


@pytest.mark.asyncio
@respx.mock
async def test_duplicates_across_pages_are_dropped():
    same = _node(id="D_same")
    respx.post(GRAPHQL).mock(
        side_effect=[
            httpx.Response(200, json=_page([same], has_next=True)),
            httpx.Response(200, json=_page([same], has_next=False)),
        ]
    )

    result = await gd.search(["prompt caching"])

    assert len(result.conversations) == 1


@pytest.mark.asyncio
@respx.mock
async def test_request_budget_is_respected():
    respx.post(GRAPHQL).mock(
        return_value=httpx.Response(200, json=_page([_node()], has_next=True))
    )

    result = await gd.search(["a", "b", "c"], max_requests=2)

    assert result.requests_made == 2
    assert any("request limit" in note for note in result.notes)


@pytest.mark.asyncio
@respx.mock
async def test_breadth_before_depth():
    """
    Every query gets page one before any gets page two.

    Without this a single broad phrase takes the whole budget and the last
    phrase never runs at all.
    """
    route = respx.post(GRAPHQL).mock(
        return_value=httpx.Response(200, json=_page([_node()], has_next=True))
    )

    await gd.search(["alpha", "beta"], max_requests=3)

    sent = [call.request.read().decode() for call in route.calls]
    assert "alpha" in sent[0]
    assert "beta" in sent[1]
    assert "alpha" in sent[2]


# ---------------------------------------------------------------- filters


@pytest.mark.asyncio
@respx.mock
async def test_archived_repositories_are_dropped():
    """Archiving removes the reply box, so a match there is unreachable."""
    respx.post(GRAPHQL).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                [
                    _node(id="D_live"),
                    _node(
                        id="D_dead",
                        repository={
                            "nameWithOwner": "old/thing",
                            "stargazerCount": 9_000,
                            "isArchived": True,
                        },
                    ),
                ]
            ),
        )
    )

    result = await gd.search(["prompt caching"])

    assert [c.source_id for c in result.conversations] == ["D_live"]
    assert any("archived" in note for note in result.notes)


@pytest.mark.asyncio
@respx.mock
async def test_small_repositories_are_dropped_without_extra_requests():
    """
    GraphQL returns the star count inline, unlike REST.

    So this filter must cost no additional request - which is the whole
    reason it lives here rather than being reused from the issue connector.
    """
    route = respx.post(GRAPHQL).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                [
                    _node(id="D_big"),
                    _node(
                        id="D_small",
                        repository={
                            "nameWithOwner": "tiny/side-project",
                            "stargazerCount": 4,
                            "isArchived": False,
                        },
                    ),
                ]
            ),
        )
    )

    result = await gd.search(["prompt caching"], min_repo_stars=500)

    assert [c.source_id for c in result.conversations] == ["D_big"]
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_unknown_star_count_is_kept():
    """A missing count is not evidence of a small project."""
    respx.post(GRAPHQL).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                [
                    _node(
                        repository={
                            "nameWithOwner": "who/knows",
                            "stargazerCount": None,
                            "isArchived": False,
                        }
                    )
                ]
            ),
        )
    )

    result = await gd.search(["prompt caching"], min_repo_stars=500)

    assert len(result.conversations) == 1


@pytest.mark.asyncio
@respx.mock
async def test_insiders_are_dropped_when_asked():
    respx.post(GRAPHQL).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                [
                    _node(id="D_outsider", authorAssociation="NONE"),
                    _node(id="D_owner", authorAssociation="OWNER"),
                ]
            ),
        )
    )

    result = await gd.search(["prompt caching"], outsiders_only=True)

    assert [c.source_id for c in result.conversations] == ["D_outsider"]


@pytest.mark.asyncio
@respx.mock
async def test_bots_are_dropped_when_asked():
    respx.post(GRAPHQL).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                [
                    _node(id="D_human"),
                    _node(id="D_bot", author={"login": "x", "__typename": "Bot"}),
                ]
            ),
        )
    )

    result = await gd.search(["prompt caching"], drop_bots=True)

    assert [c.source_id for c in result.conversations] == ["D_human"]


@pytest.mark.asyncio
@respx.mock
async def test_concurrent_searches_do_not_share_filter_state():
    """
    Repo facts are per-search, not module state.

    Two runs at once used to be able to clear each other's star and archive
    lookups, which showed up as results vanishing at random under load.
    """
    import asyncio

    respx.post(GRAPHQL).mock(
        return_value=httpx.Response(
            200,
            json=_page(
                [
                    _node(
                        id="D_small",
                        repository={
                            "nameWithOwner": "tiny/x",
                            "stargazerCount": 3,
                            "isArchived": False,
                        },
                    )
                ]
            ),
        )
    )

    both = await asyncio.gather(
        gd.search(["a"], min_repo_stars=500),
        gd.search(["b"], min_repo_stars=500),
    )

    assert all(r.conversations == [] for r in both)


@pytest.mark.asyncio
@respx.mock
async def test_over_cap_result_sets_say_so():
    respx.post(GRAPHQL).mock(
        return_value=httpx.Response(200, json=_page([_node()], total=40_000))
    )

    result = await gd.search(["cache"])

    assert any("too broad" in note for note in result.notes)


@pytest.mark.asyncio
@respx.mock
async def test_empty_repo_sweep_hints_at_discussions_being_off():
    """Silent, and the single most confusing way this returns nothing."""
    respx.post(GRAPHQL).mock(return_value=httpx.Response(200, json=_page([])))

    result = await gd.search([], repos=["some/repo"])

    assert any("Discussions turned off" in note for note in result.notes)


@pytest.mark.asyncio
async def test_no_queries_costs_nothing():
    result = await gd.search([], repos=[])
    assert result.requests_made == 0
    assert result.conversations == []


# ---------------------------------------------------------------- freshness


@pytest.mark.asyncio
@respx.mock
async def test_date_window_reaches_the_query():
    route = respx.post(GRAPHQL).mock(
        return_value=httpx.Response(200, json=_page([]))
    )

    await gd.search(["x"], days=7)

    expected = (datetime.now(UTC) - timedelta(days=7)).date().isoformat()
    assert expected in route.calls[0].request.read().decode()
