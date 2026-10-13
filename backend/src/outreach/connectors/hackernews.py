"""
Hacker News connector, through Algolia's search index.

Same three steps as the GitHub connectors, same order:

    build_query()       phrase + filters  ->  query params
    to_conversation()   one Algolia hit   ->  one Conversation
    search()            run the queries, page through, be polite

── Why comments are searched, not just stories ──────────────────────────

On GitHub the unit is the issue. On Hacker News it is the *comment*, and
searching only stories throws away most of what is here. A story is usually
a link somebody posted; the person describing a problem in their own words
is four replies down. Measured on one product's terms: `"prompt caching"`
matches 43 stories and 363 comments, and the comments are the ones that say
what actually went wrong.

Both are fetched, as separate queries, because Algolia filters by tag and a
single request cannot ask for stories and comments with different rules.

── What is missing compared to GitHub ───────────────────────────────────

Two signals this pipeline leans on do not exist here and are not faked:

  * no author association. There is no "wrote this in their own project"
    on Hacker News, so the insider filter has nothing to act on.
  * comments carry no points. Algolia returns `points: null` for every
    one of them, so engagement scoring falls back on the story.

Neither is worth inventing a substitute for. A guessed signal is worse
than an absent one, because the scorer cannot tell the difference.
"""

from __future__ import annotations

import asyncio
import html
import re
import time
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from outreach.config import settings
from outreach.connectors.github import SearchResult, render_phrase
from outreach.schemas.conversation import Conversation

log = structlog.get_logger(__name__)

SEARCH_URL = "https://hn.algolia.com/api/v1/search"

#: Algolia serves at most this many, whatever `nbHits` claims - ten pages of
#: a hundred. The same ceiling GitHub has, for the same reason.
HARD_RESULT_CAP = 1000
PER_PAGE = 100
MAX_PAGES_PER_QUERY = 3

#: An item's page on Hacker News itself. Algolia gives ids, not links, and
#: for a comment the useful destination is the comment in its thread rather
#: than whatever the story linked to.
ITEM_URL = "https://news.ycombinator.com/item?id={}"

#: Algolia is generous - thousands of requests an hour, no key required -
#: but it is a free service being used by a robot, so requests are spaced.
#: Slower than necessary is the correct side to err on with somebody else's
#: infrastructure.
SPACING_SECONDS = 0.25

_TAG = re.compile(r"<[^>]+>")
_PARA = re.compile(r"</p\s*>|<br\s*/?>", re.I)

_pace_lock = asyncio.Lock()
_last_request_at = 0.0


async def _pace() -> None:
    global _last_request_at
    async with _pace_lock:
        since = time.monotonic() - _last_request_at
        if since < SPACING_SECONDS:
            await asyncio.sleep(SPACING_SECONDS - since)
        _last_request_at = time.monotonic()


# ---------------------------------------------------------------- 1. queries


def build_query(phrase: str, days: int, tag: str) -> dict:
    """
    One set of Algolia parameters.

    The phrase is rendered by the same function the GitHub connectors use,
    which is what makes a term mean one thing wherever a plan runs it: `+`
    is an intersection on both sources, and both must appear.

    Unquoted here, though. See `render_phrase` for the measurements - the
    short version is that Algolia's index is far smaller than GitHub's, so
    exact-phrase matching that narrows usefully there returns nothing here.
    A real run made this concrete: four of the plan's six Hacker News terms
    returned zero results quoted, and the same terms return 58 to 2,225
    unquoted.
    """
    since = int((datetime.now(UTC) - timedelta(days=days)).timestamp())
    return {
        "query": render_phrase(phrase, quote=False),
        "tags": tag,
        "hitsPerPage": PER_PAGE,
        "numericFilters": f"created_at_i>{since}",
    }


def build_queries(
    phrases: list[str], days: int = 90, tags: tuple[str, ...] = ("story", "comment")
) -> list[tuple[str, dict]]:
    """
    One query per phrase per tag. Returns (label, params).

    No equivalent of a repository sweep. GitHub lets us name a room and read
    everything recent in it; Hacker News has no rooms, only a firehose, so
    every result here has to come from a phrase.
    """
    out: list[tuple[str, dict]] = []
    seen: set[str] = set()

    for phrase in phrases:
        clean = " ".join(phrase.split())
        if not clean:
            continue
        for tag in tags:
            params = build_query(clean, days, tag)
            if not params["query"]:
                continue
            key = f"{tag}:{params['query']}"
            if key in seen:
                continue
            seen.add(key)
            out.append((f"{tag}: {clean}", params))

    return out


# ---------------------------------------------------------------- 2. mapping


def clean_text(raw: str | None) -> str:
    """
    Algolia's HTML into something a model should read.

    `comment_text` arrives as stored HTML with escaped entities - tags for
    paragraphs and links, `&#x27;` for an apostrophe. Passed through as-is
    it costs tokens on markup and puts `&#x27;` in front of the classifier,
    which then has to spend attention deciding it is not meaningful.
    """
    if not raw:
        return ""
    text = _PARA.sub("\n", raw)
    text = _TAG.sub("", text)
    return html.unescape(text).strip()


#: How much of a comment stands in for its title.
#:
#: Long enough to carry a claim, short enough to scan in a list. The triage
#: truncates at 160 characters anyway.
HEADLINE_CHARS = 150


def headline(body: str) -> str:
    """
    A comment's own opening, to stand where a story would have a title.

    ── Why a comment cannot borrow its thread's title ───────────────────

    Algolia gives a comment `story_title` and nothing else title-shaped, so
    the obvious mapping is to use it. That is wrong in a way that is easy to
    miss, because the result looks perfectly reasonable on screen.

    Everything downstream reads `title`. The triage reads *only* titles - it
    is what picks 25 candidates out of several hundred - so with the thread
    title there, every comment in a thread is judged by the same string, and
    what the person actually wrote is invisible to the one stage that
    decides whether anybody reads it. On one real run that hid a comment
    asking "Does anyone know what the impact on prompt caching is?" beneath
    a headline about somebody else's coding agent, scored 4.

    It reads wrong too: the card showed the thread title as the headline and
    again underneath as the container, so a lead was displayed under the
    name of a product it had nothing to do with.

    The thread still matters, and it stays in `container` - that is context
    for a remark, not the remark.
    """
    text = " ".join(body.split())
    if not text:
        return ""

    # Prefer a whole first sentence when there is one of a sensible length;
    # a hard character cut mid-clause reads worse than a slightly short one.
    for stop in (". ", "? ", "! "):
        head, sep, _ = text.partition(stop)
        if sep and len(head) <= HEADLINE_CHARS:
            return head + sep.strip()

    if len(text) <= HEADLINE_CHARS:
        return text
    return text[:HEADLINE_CHARS].rsplit(" ", 1)[0] + "..."


#: Threads whose comments match everything and mean nothing.
#:
#: Hacker News runs a handful of recurring megathreads - the monthly hiring
#: posts especially - where hundreds of people list every technology they
#: have touched. A comment in one of those contains "LLM", "agents",
#: "caching" and "retrieval" because somebody is describing a career, not a
#: problem, so they match any technical vocabulary a plan can produce and
#: crowd out real results. Dropped by thread rather than by content: the
#: giveaway is where the comment is, not what it says.
#:
#: `[dead]` is Hacker News' own marker for a killed thread. Nobody is going
#: to read a reply there.
NOISE_THREADS = re.compile(
    r"^\s*(\[dead\]"
    r"|ask hn:\s*who('s| is| wants)"
    r"|ask hn:\s*freelancer"
    r"|who is hiring"
    r"|who wants to be hired"
    r"|freelancer\?\s*seeking freelancer)",
    re.I,
)


def to_conversation(hit: dict) -> Conversation | None:
    """
    One Algolia hit to a Conversation. None when it cannot be used.

    Handles both shapes, because the two differ in almost every field that
    matters: a story has `title`, `points` and `num_comments`; a comment has
    `comment_text`, `story_title` and no score at all.
    """
    try:
        source_id = str(hit.get("objectID") or "").strip()
        created = hit.get("created_at")
        if not source_id or not created:
            return None

        is_comment = "comment_text" in hit

        # Before anything is built: a comment in a hiring megathread is
        # somebody's CV, and it matches every technical term there is.
        thread = str(hit.get("story_title") or hit.get("title") or "")
        if NOISE_THREADS.match(thread):
            return None
        body = clean_text(
            hit.get("comment_text") if is_comment else hit.get("story_text")
        )
        # A story is titled; a comment speaks for itself. See `headline`.
        title = headline(body) if is_comment else (hit.get("title") or None)

        # A comment with nothing in it is a deleted one; Algolia keeps the
        # row. Nothing downstream can judge an empty post.
        if not title:
            return None

        return Conversation(
            source="hackernews",
            kind="comment" if is_comment else "story",
            source_id=source_id,
            # The item on Hacker News, never the link the story pointed at.
            # Somebody replying needs the thread, not the article.
            url=ITEM_URL.format(source_id),
            title=title,
            body=body,
            author=hit.get("author"),
            created_at=datetime.fromisoformat(str(created).replace("Z", "+00:00")),
            # Comments have no points at all in this index, so they score
            # zero rather than borrowing the story's and looking popular.
            score=int(hit.get("points") or 0),
            comments=int(hit.get("num_comments") or 0),
            container=_container(hit, is_comment),
            # Hacker News has no notion of writing in your own project, so
            # the insider filter has nothing to work with here.
            author_association=None,
            labels=[t for t in (hit.get("_tags") or []) if isinstance(t, str)][:6],
        )
    except (TypeError, ValueError, KeyError):
        return None


def _container(hit: dict, is_comment: bool) -> str | None:
    """
    Where this lives, in the same sense as "owner/name" on GitHub.

    For a comment that is the thread it sits in, which is the one piece of
    context that makes a stray remark readable. For a story it is the site
    it links to, or the kind of post when it links nowhere.
    """
    if is_comment:
        title = hit.get("story_title")
        return str(title)[:120] if title else "Hacker News"

    url = hit.get("url")
    if url:
        try:
            host = str(url).split("//", 1)[-1].split("/", 1)[0]
            return host.removeprefix("www.") or "Hacker News"
        except Exception:
            return "Hacker News"

    tags = hit.get("_tags") or []
    if "ask_hn" in tags:
        return "Ask HN"
    if "show_hn" in tags:
        return "Show HN"
    return "Hacker News"


# ---------------------------------------------------------------- 3. fetching


async def search(
    phrases: list[str],
    days: int = 90,
    max_requests: int = 20,
    min_story_points: int = 0,
    tags: tuple[str, ...] = ("story", "comment"),
) -> SearchResult:
    """
    Run every query and collect the results.

    Paged round robin - page one of every query, then page two - for the
    same reason the GitHub connectors are: run one at a time and a single
    broad phrase spends the budget while the last three never run.

    Returns the same `SearchResult` the GitHub connectors do, so a caller
    can merge sources without caring which produced what.
    """
    result = SearchResult()
    queries = build_queries(phrases, days, tags)
    if not queries:
        return result

    seen: set[str] = set()
    found: dict[str, int] = {label: 0 for label, _ in queries}
    cursors: dict[str, int] = {label: 0 for label, _ in queries}
    done: set[str] = set()
    stopped_early = False

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        for _ in range(MAX_PAGES_PER_QUERY):
            if len(done) >= len(queries):
                break

            for label, params in queries:
                if label in done:
                    continue
                if result.requests_made >= max_requests:
                    stopped_early = True
                    break

                page = cursors[label]
                if page * PER_PAGE >= HARD_RESULT_CAP:
                    done.add(label)
                    continue

                try:
                    added, more = await _fetch_page(
                        client, params, page, label, result, seen
                    )
                except Exception as exc:
                    log.warning("hn.query_failed", label=label, error=str(exc))
                    result.notes.append(f"hn {label} failed: {exc}")
                    done.add(label)
                    continue

                found[label] += added
                cursors[label] = page + 1
                if not more:
                    done.add(label)

            if stopped_early:
                break

    for label, _ in queries:
        result.notes.append(f"hn {label} -> {found[label]}")

    if stopped_early:
        left = len(queries) - len(done)
        result.notes.append(
            f"Hacker News stopped at the {max_requests} request limit with "
            f"{left} quer{'y' if left == 1 else 'ies'} still having more to give."
        )

    if min_story_points > 0:
        _drop_quiet_stories(result, min_story_points)

    return result


async def _fetch_page(
    client: httpx.AsyncClient,
    params: dict,
    page: int,
    label: str,
    result: SearchResult,
    seen: set[str],
) -> tuple[int, bool]:
    """One page of one query. Returns (new conversations, is there more)."""
    payload = await _get(client, {**params, "page": page})
    result.requests_made += 1

    hits = payload.get("hits") or []
    if not hits:
        return 0, False

    total = int(payload.get("nbHits") or 0)
    if page == 0 and total > HARD_RESULT_CAP:
        result.notes.append(
            f"  {label} matched {total:,} but Algolia serves at most "
            f"{HARD_RESULT_CAP} - this phrase is too broad to be precise"
        )

    added = 0
    for hit in hits:
        conversation = to_conversation(hit)
        if conversation is None:
            continue
        key = f"{conversation.source}:{conversation.source_id}"
        if key in seen:
            continue
        seen.add(key)
        conversation.found_by = label
        result.conversations.append(conversation)
        added += 1

    return added, page + 1 < int(payload.get("nbPages") or 0)


def _drop_quiet_stories(result: SearchResult, minimum: int) -> None:
    """
    Remove stories nobody voted for. Comments are never touched.

    A story with two points sank without trace, and replying to it reaches
    nobody. A *comment* with no points means only that Algolia does not
    report them - judging comments on a number that is always zero would
    delete the better half of this source.
    """
    kept: list[Conversation] = []
    dropped = 0
    for conversation in result.conversations:
        if conversation.kind == "story" and conversation.score < minimum:
            dropped += 1
            continue
        kept.append(conversation)

    if dropped:
        result.notes.append(f"hn: dropped {dropped} stories under {minimum} points")
    result.conversations = kept


async def _get(client: httpx.AsyncClient, params: dict) -> dict:
    """
    One request, spaced, retrying on the failures that are worth retrying.

    Algolia answers 429 when it wants a pause. It sends no Retry-After, so
    the wait is chosen here rather than read from the response.
    """
    for attempt in range(3):
        await _pace()
        try:
            response = await client.get(SEARCH_URL, params=params)
        except (httpx.TransportError, httpx.RemoteProtocolError) as exc:
            if attempt == 2:
                raise RuntimeError(f"Hacker News connection failed: {exc}") from exc
            await asyncio.sleep(1.5 * (attempt + 1))
            continue

        if response.status_code == 200:
            return response.json()

        if response.status_code == 429:
            log.warning("hn.rate_limited", attempt=attempt)
            await asyncio.sleep(5.0 * (attempt + 1))
            continue

        if response.status_code >= 500:
            if attempt == 2:
                raise RuntimeError(f"Algolia returned {response.status_code}")
            await asyncio.sleep(2.0 * (attempt + 1))
            continue

        raise RuntimeError(
            f"Algolia rejected the query: {response.status_code} {response.text[:160]}"
        )

    raise RuntimeError("Hacker News still rate limited after three attempts.")
