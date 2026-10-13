"""
GitHub Discussions connector. GraphQL, because REST cannot see them.

The issue search next door indexes issues and pull requests and nothing else.
A discussion titled "Prompt caching incompatibility with RAG document
retrieval" simply does not appear in it, however exactly it matches - not
ranked low, not filtered out, *absent*. The only way to reach discussions is
the GraphQL API's `search(type: DISCUSSION)`, which is why this file exists.

That gap matters more than it sounds. Issues skew towards "here is a bug,
here is my patch"; discussions skew towards "how are people solving this?".
The second is the question a marketer wants to arrive underneath, so a search
that only reads issues systematically finds the wrong half of GitHub.

Same three steps as the REST connector, same order:

    build_query()       phrase + filters  ->  a search string
    to_conversation()   one GraphQL node  ->  one Conversation
    search()            run the queries, page through, handle rate limits

Three things differ from REST and every one of them bites:

  * a token is **required**, not merely helpful. GraphQL answers 401 without
    one, where REST search would still have served 10 requests a minute.
  * errors arrive with HTTP 200 and an `errors` array. A response that looks
    perfectly healthy can carry nothing but a complaint about the query.
  * `is:issue` and `is:open` are wrong here - the first matches nothing, the
    second silently drops resolved threads that are still worth reading - so
    the query has to be built separately rather than borrowed.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from outreach.config import settings
from outreach.connectors.github import (
    INSIDER,
    SearchResult,
    is_bot_login,
    render_phrase,
)
from outreach.schemas.conversation import Conversation

log = structlog.get_logger(__name__)

GRAPHQL_URL = "https://api.github.com/graphql"

#: Same limit as the REST search, and the same consequence for exceeding it.
MAX_QUERY_CHARS = 256

#: GitHub will not serve past this, whatever `discussionCount` claims.
HARD_RESULT_CAP = 1000

#: Discussions per page.
#:
#: REST happily serves 100. GraphQL search is a different engine and a slower
#: one: a hundred discussions, each dragging its own label, reaction and
#: repository connections behind it, is enough work to hit GitHub's internal
#: timeout on a broad query. That arrives as a 502 and costs the entire page
#: rather than trimming it. Fifty is the size that stopped doing that.
PER_PAGE = 50

#: Pages any single query may take before we move on. Same reasoning as the
#: issue search: when every phrase matches thousands, breadth beats depth.
MAX_PAGES_PER_QUERY = 3

#: Labels are a minor signal and each one multiplies the query's node cost.
LABELS_PER_DISCUSSION = 8


#: One document, reused for every request.
#:
#: `nodes` is a union - `search` can return issues, repositories and users too
#: - so everything lives inside an inline fragment. Anything that is not a
#: Discussion comes back as an empty object rather than an error, which is why
#: `to_conversation` has to tolerate one.
SEARCH_QUERY = """
query($q: String!, $first: Int!, $after: String, $labels: Int!) {
  search(query: $q, type: DISCUSSION, first: $first, after: $after) {
    discussionCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Discussion {
        id
        title
        body
        url
        createdAt
        upvoteCount
        isAnswered
        authorAssociation
        author { login __typename }
        category { name }
        comments { totalCount }
        reactions { totalCount }
        labels(first: $labels) { nodes { name } }
        repository { nameWithOwner stargazerCount isArchived }
      }
    }
  }
}
"""


class DiscussionsUnavailable(Exception):
    """
    The search could not run at all, phrased for a person.

    Raised rather than returned because there is a real difference between
    "searched and found nothing" and "never searched". A run that quietly
    reports zero discussions when the token was missing teaches the user that
    there are no discussions worth finding, which is the opposite of true.
    """


# ---------------------------------------------------------------- 1. queries


def build_query(
    phrase: str = "",
    repo: str | None = None,
    days: int = 30,
    exclude: list[str] | None = None,
    category: str | None = None,
) -> str:
    """
    Build one discussion search string, trimmed to fit the 256 char limit.

    Deliberately *not* `github.build_query` with a different type. Two of the
    qualifiers that function always adds are wrong here:

      * `is:issue` matches no discussion at all, so borrowing it returns an
        empty result set that looks exactly like a phrase nobody uses.
      * `is:open` looks harmless and costs real leads. A closed discussion is
        usually one somebody answered, and "here is how I worked around it"
        with forty upvotes is a better place to reply than a fresh question
        nobody has read yet.

    Filters drop from the end when the string would overflow, for the same
    reason as the REST builder: a dropped filter widens the search, an
    over-long query is rejected outright and loses it.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()

    parts: list[str] = []
    if phrase:
        # Shared with the issue connector, so "prompt caching + RAG" means
        # the same intersection on both sides of the search.
        rendered = render_phrase(phrase)
        if rendered:
            parts.append(rendered)

    parts.append(f"created:>={since}")

    if repo:
        parts.append(f"repo:{repo}")

    if category:
        parts.append(f'category:"{category}"')

    for term in (exclude or [])[:3]:
        parts.append(f'-"{term}"' if " " in term else f"-{term}")

    query = " ".join(parts)
    while len(query) > MAX_QUERY_CHARS and len(parts) > 1:
        parts.pop()
        query = " ".join(parts)
    return query


def build_queries(
    phrases: list[str],
    repos: list[str] | None = None,
    days: int = 30,
    exclude: list[str] | None = None,
) -> list[tuple[str, str]]:
    """
    One query per phrase, plus one per repository. Returns (label, query).

    Repository queries carry no phrase, exactly as in the issue search: in a
    repo where our buyers already are, every recent discussion is a candidate
    without anyone having guessed the right keyword. Discussions reward that
    more than issues do, because a discussion forum is smaller and more
    conversational than an issue tracker - sweeping one is reading a room,
    not draining an ocean.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    for phrase in phrases:
        clean = " ".join(phrase.split())
        if not clean:
            continue
        query = build_query(clean, days=days, exclude=exclude)
        if query not in seen:
            seen.add(query)
            out.append((f"phrase: {clean}", query))

    for repo in repos or []:
        query = build_query(repo=repo, days=days)
        if query not in seen:
            seen.add(query)
            out.append((f"repo: {repo}", query))

    return out


# ---------------------------------------------------------------- 2. mapping


def to_conversation(node: dict) -> Conversation | None:
    """
    One GraphQL node to a Conversation. None when it cannot be used.

    Returns None rather than raising so that one odd node - or one empty
    object from the union - does not lose the other forty-nine in the page.
    """
    try:
        source_id = str(node.get("id") or "")
        url = node.get("url")
        created = node.get("createdAt")
        if not source_id or not url or not created:
            return None

        author = node.get("author") or {}
        handle = author.get("login")
        repository = node.get("repository") or {}
        category = node.get("category") or {}

        return Conversation(
            source="github",
            kind="discussion",
            source_id=source_id,
            url=url,
            title=node.get("title"),
            body=node.get("body") or "",
            author=handle,
            author_is_bot=(
                author.get("__typename") == "Bot" or is_bot_login(handle)
            ),
            created_at=datetime.fromisoformat(str(created).replace("Z", "+00:00")),
            score=_attention(node),
            comments=int((node.get("comments") or {}).get("totalCount") or 0),
            container=repository.get("nameWithOwner"),
            author_association=node.get("authorAssociation"),
            labels=[
                label["name"]
                for label in (node.get("labels") or {}).get("nodes") or []
                if isinstance(label, dict) and label.get("name")
            ],
            category=category.get("name"),
            # Explicitly None-preserving. False means "a question nobody has
            # answered yet", None means "not a question" - collapsing them
            # would hide the best signal discussions carry.
            is_answered=node.get("isAnswered"),
        )
    except (TypeError, ValueError, KeyError):
        return None


def _attention(node: dict) -> int:
    """
    Upvotes plus reactions.

    Discussions have both, and they are separate affordances rather than two
    names for one number: the upvote arrow sits on the post, the emoji picker
    sits under it, and people use them for different things. Summing keeps
    this comparable with the issue connector, where `score` is reactions.
    """
    upvotes = node.get("upvoteCount")
    reactions = (node.get("reactions") or {}).get("totalCount")
    return int(upvotes or 0) + int(reactions or 0)


# ---------------------------------------------------------------- 3. fetching


async def search(
    phrases: list[str],
    repos: list[str] | None = None,
    days: int = 30,
    exclude: list[str] | None = None,
    max_requests: int = 12,
    drop_bots: bool = True,
    outsiders_only: bool = False,
    min_repo_stars: int = 0,
    skip_archived: bool = True,
) -> SearchResult:
    """
    Run every query and collect the results.

    Paged **round robin** - page one of every query, then page two of every
    query - for the same reason the issue search is: run one at a time and a
    single broad phrase eats the budget while the last three never run.

    Returns the same `SearchResult` the REST connector does, so callers can
    merge the two without caring which produced what.

    Raises `DiscussionsUnavailable` only when nothing could run at all. A
    single failing query is noted and dropped, as there.
    """
    if not settings.github_token:
        raise DiscussionsUnavailable(
            "Searching GitHub Discussions needs a GITHUB_TOKEN. Unlike the "
            "issue search, the GraphQL API refuses anonymous requests "
            "outright. A fine-grained token with no scopes is enough."
        )

    result = SearchResult()
    queries = build_queries(phrases, repos, days, exclude)
    if not queries:
        return result

    seen: set[str] = set()
    #: discussion id -> (stars, archived) for the repository it lives in.
    #:
    #: GraphQL hands both over in the same response, but neither belongs on
    #: `Conversation` - only this connector would ever set them, and only the
    #: filter below ever reads them. Local to one search rather than module
    #: state, so two runs at once cannot clear each other's entries.
    repo_facts: dict[str, tuple[int | None, bool]] = {}
    #: label -> how many new conversations it contributed
    found: dict[str, int] = {label: 0 for label, _ in queries}
    #: label -> cursor for its next page, once it has one
    cursors: dict[str, str | None] = {label: None for label, _ in queries}
    #: Queries with nothing left to give, or that failed.
    done: set[str] = set()
    stopped_early = False

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        for page in range(1, MAX_PAGES_PER_QUERY + 1):
            if len(done) >= len(queries):
                break
            if page * PER_PAGE > HARD_RESULT_CAP:
                break

            for label, query in queries:
                if label in done:
                    continue
                if result.requests_made >= max_requests:
                    stopped_early = True
                    break

                try:
                    added, cursor = await _fetch_page(
                        client, query, cursors[label], result, seen, repo_facts, label
                    )
                except DiscussionsUnavailable:
                    # Fatal for the whole search rather than for this query.
                    # A rejected token fails identically on every remaining
                    # query, so swallowing it here would bury one real cause
                    # under a dozen "query failed" notes and leave the user
                    # reading the wrong problem.
                    raise
                except Exception as exc:
                    log.warning(
                        "github_discussions.query_failed", label=label, error=str(exc)
                    )
                    result.notes.append(f"discussions {label} failed: {exc}")
                    done.add(label)
                    continue

                found[label] += added
                cursors[label] = cursor
                if cursor is None:
                    done.add(label)

            if stopped_early:
                break

    for label, _ in queries:
        result.notes.append(f"discussions {label} -> {found[label]}")
        if found[label] == 0 and label.startswith("repo: "):
            result.notes.append(
                "    nothing here - the repository may have Discussions "
                "turned off, which is silent rather than an error"
            )

    if stopped_early:
        left = len(queries) - len(done)
        result.notes.append(
            f"Discussions stopped at the {max_requests} request limit with "
            f"{left} quer{'y' if left == 1 else 'ies'} still having more to give."
        )

    _filter(
        result,
        repo_facts,
        drop_bots=drop_bots,
        outsiders_only=outsiders_only,
        min_repo_stars=min_repo_stars,
        skip_archived=skip_archived,
    )

    return result


async def _fetch_page(
    client: httpx.AsyncClient,
    query: str,
    after: str | None,
    result: SearchResult,
    seen: set[str],
    repo_facts: dict[str, tuple[int | None, bool]],
    label: str = "",
) -> tuple[int, str | None]:
    """
    One page of one query. Returns (new conversations, cursor for the next).

    A None cursor means this query is finished - either GitHub said there is
    no next page, or we have reached the point past which it will not serve.
    """
    payload = await _post(
        client,
        {
            "q": query,
            "first": PER_PAGE,
            "after": after,
            "labels": LABELS_PER_DISCUSSION,
        },
    )
    result.requests_made += 1

    search_result = (payload.get("data") or {}).get("search") or {}
    nodes = search_result.get("nodes") or []
    if not nodes:
        return 0, None

    total = int(search_result.get("discussionCount") or 0)
    if after is None and total > HARD_RESULT_CAP:
        result.notes.append(
            f"  matched {total:,} discussions but GitHub serves at most "
            f"{HARD_RESULT_CAP} - this phrase is too broad to be precise"
        )

    added = 0
    for node in nodes:
        # The union yields `{}` for anything that is not a Discussion.
        if not node:
            continue
        conversation = to_conversation(node)
        if conversation is None:
            continue
        key = f"{conversation.source}:{conversation.source_id}"
        if key in seen:
            continue
        seen.add(key)
        repository = node.get("repository") or {}
        repo_facts[conversation.source_id] = (
            repository.get("stargazerCount"),
            bool(repository.get("isArchived")),
        )
        conversation.found_by = label
        result.conversations.append(conversation)
        added += 1

    page_info = search_result.get("pageInfo") or {}
    if not page_info.get("hasNextPage"):
        return added, None
    return added, page_info.get("endCursor")


def _filter(
    result: SearchResult,
    repo_facts: dict[str, tuple[int | None, bool]],
    *,
    drop_bots: bool,
    outsiders_only: bool,
    min_repo_stars: int,
    skip_archived: bool,
) -> None:
    """
    Drop the obvious non-leads, and say how many went and why.

    The star check costs nothing here, unlike in the issue connector. REST
    search does not return a repository's star count, so that connector has
    to spend a second request per repository to learn it; GraphQL hands it
    over in the same response, so the filter is free.

    Archived repositories are dropped outright and only here. Archiving makes
    a repository read-only - the reply box is gone - so a match in one is not
    a weak lead, it is an impossible one.
    """
    kept: list[Conversation] = []
    dropped_bots = 0
    dropped_insiders = 0
    dropped_small = 0
    dropped_archived = 0

    for conversation in result.conversations:
        stars, archived = repo_facts.get(conversation.source_id, (None, False))

        if drop_bots and conversation.author_is_bot:
            dropped_bots += 1
            continue
        if outsiders_only and conversation.author_association in INSIDER:
            dropped_insiders += 1
            continue
        if skip_archived and archived:
            dropped_archived += 1
            continue
        # Unknown stays, as in the issue connector: a missing count is not
        # evidence of a small project.
        if min_repo_stars > 0 and stars is not None and stars < min_repo_stars:
            dropped_small += 1
            continue
        kept.append(conversation)

    if dropped_bots:
        result.notes.append(f"discussions: dropped {dropped_bots} bot-authored")
    if dropped_insiders:
        result.notes.append(
            f"discussions: dropped {dropped_insiders} written by people who "
            f"work on that repo"
        )
    if dropped_archived:
        result.notes.append(
            f"discussions: dropped {dropped_archived} in archived repositories "
            f"(read-only, so there is nowhere to reply)"
        )
    if dropped_small:
        result.notes.append(
            f"discussions: dropped {dropped_small} from repositories under "
            f"{min_repo_stars:,} stars"
        )

    result.conversations = kept


async def _post(client: httpx.AsyncClient, variables: dict) -> dict:
    """
    One GraphQL request, waiting as long as GitHub asks when it says to wait.

    The awkward part is that GraphQL reports most failures with HTTP 200 and
    an `errors` array, so a 200 is not the end of the checking. Three kinds
    turn up in practice and they need different handling:

      * `RATE_LIMITED` - back off and retry, same as a 403 would be.
      * a timeout, which GitHub reports as a 502 with a message about the
        query taking too long. Retrying an identical query usually works,
        because it is load-dependent rather than a property of the query.
      * anything else - a bad qualifier, a malformed cursor - which will fail
        identically forever and must be raised rather than retried.
    """
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
    }
    body = {"query": SEARCH_QUERY, "variables": variables}

    for attempt in range(3):
        try:
            response = await client.post(GRAPHQL_URL, json=body, headers=headers)
        except (httpx.TransportError, httpx.RemoteProtocolError) as exc:
            if attempt == 2:
                raise RuntimeError(f"GitHub connection failed: {exc}") from exc
            log.info("github_discussions.retrying", attempt=attempt, error=str(exc))
            await asyncio.sleep(1.5 * (attempt + 1))
            continue

        if response.status_code == 401:
            raise DiscussionsUnavailable(
                "GitHub rejected the token. The GraphQL API needs a valid "
                "GITHUB_TOKEN; the issue search tolerates a bad one by "
                "falling back to anonymous requests, so this can be the "
                "first place a stale token shows up."
            )

        if response.status_code in (403, 429):
            wait = _retry_after(response)
            log.warning("github_discussions.rate_limited", wait_seconds=wait)
            await asyncio.sleep(min(wait or 60.0, 60.0))
            continue

        if response.status_code == 502:
            # Nearly always the query timing out inside GitHub. Load
            # dependent, so the same request often succeeds seconds later.
            if attempt == 2:
                raise RuntimeError("GitHub timed out on this discussion query.")
            await asyncio.sleep(2.0 * (attempt + 1))
            continue

        if response.status_code != 200:
            response.raise_for_status()

        payload = response.json()
        errors = payload.get("errors") or []
        if not errors:
            return payload

        kinds = {str(e.get("type") or "") for e in errors}
        message = "; ".join(str(e.get("message") or "")[:120] for e in errors[:2])

        if "RATE_LIMITED" in kinds:
            wait = _retry_after(response)
            log.warning("github_discussions.rate_limited", wait_seconds=wait)
            await asyncio.sleep(min(wait or 60.0, 60.0))
            continue

        if "TIMEDOUT" in kinds or "timeout" in message.lower():
            if attempt == 2:
                raise RuntimeError(f"GitHub timed out: {message}")
            await asyncio.sleep(2.0 * (attempt + 1))
            continue

        # `data` can arrive alongside errors when only part of the query
        # failed. Partial results beat none, so take them rather than raise.
        if payload.get("data", {}).get("search"):
            log.info("github_discussions.partial", error=message)
            return payload

        raise RuntimeError(f"GitHub rejected the query: {message}")

    raise RuntimeError("Still rate limited after three attempts.")


def _retry_after(response: httpx.Response) -> float | None:
    """How long GitHub wants us to wait, or None if it did not say."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass

    if response.headers.get("x-ratelimit-remaining") == "0":
        reset = response.headers.get("x-ratelimit-reset")
        if reset:
            try:
                return max(float(reset) - time.time(), 1.0)
            except ValueError:
                pass

    return None
