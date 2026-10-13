"""
GitHub connector. Searches issues, returns Conversations.

One file, three steps, read top to bottom:

    build_query()   phrase + filters  ->  a GitHub search string
    to_conversation()   one API item  ->  one Conversation
    search()        run the queries, page through, handle rate limits

Two GitHub limits shape all of it and neither is optional:

  * a search query longer than 256 characters is rejected outright
  * search allows 30 requests a minute, and going over gets you a 403 with a
    Retry-After header rather than a friendly warning
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import structlog
from pydantic import BaseModel

from outreach.config import settings
from outreach.schemas.conversation import Conversation

log = structlog.get_logger(__name__)

SEARCH_URL = "https://api.github.com/search/issues"

MAX_QUERY_CHARS = 256
#: GitHub will not serve past this, whatever total_count claims.
HARD_RESULT_CAP = 1000
PER_PAGE = 100

#: Pages any single query may take before we move on to the next one.
#:
#: Without this, one broad phrase eats the whole request budget. A term
#: matching 90,000 issues will happily hand over 1,000 of them - all chosen
#: by GitHub's idea of relevance, not ours - while the other five phrases
#: never run at all. Three pages each spreads the same budget across more
#: angles, and breadth beats depth when every phrase matches thousands.
MAX_PAGES_PER_QUERY = 3

_BOT = re.compile(r"(\[bot\]$|^dependabot|^renovate|^github-actions|-bot$)", re.I)
_REPO_FROM_API_URL = re.compile(r"/repos/([^/]+/[^/]+)")


def is_bot_login(login: str | None) -> bool:
    """
    Does this handle belong to a bot?

    Public because the Discussions connector needs exactly the same answer,
    and two copies of this regex would drift the first time somebody adds a
    new bot to one of them.
    """
    return bool(login and _BOT.search(login))


class SearchResult(BaseModel):
    conversations: list[Conversation] = []
    requests_made: int = 0
    notes: list[str] = []
    """What each query returned and anything that was skipped. Read this
    first when the result count is surprising."""


# ---------------------------------------------------------------- 1. queries


#: Separates the halves of an intersection term: "prompt caching + RAG".
#:
#: See `render_phrase` for why this exists at all.
INTERSECT = "+"


def render_phrase(phrase: str, quote: bool = True) -> str:
    """
    One phrase to the search syntax it means.

    Two forms, and picking the wrong one is the difference between a search
    and a lottery:

        prompt caching        ->  "prompt caching"
        prompt caching + RAG  ->  "prompt caching" RAG

    A plain phrase is quoted, so GitHub matches it as an exact string. That
    is right for a term of art - people write "prompt caching" verbatim - and
    it is also why a single phrase is such a blunt instrument. `"prompt
    caching"` matches every post that mentions caching at all, tens of
    thousands of them, of which GitHub serves the first thousand.

    ── `quote` ──────────────────────────────────────────────────────────

    Off for Hacker News, and that is a difference in corpus size rather than
    a difference in intent. GitHub search runs over millions of issues, so
    an exact phrase is the narrowing that makes a term usable. Algolia's
    Hacker News index is orders of magnitude smaller, and the same quoting
    leaves nothing behind: measured over one year of comments, `slow AI
    responses` matches 0 quoted and 94 unquoted, `context management issues`
    3 and 180, `stale information` 14 and 2,225.

    The `+` semantics are identical either way, which is the part that has
    to be: a term means the same thing in a plan whichever source runs it.
    Only how strictly a multi-word *side* is matched changes, and it changes
    so that a term narrows to a usable set on each source rather than to the
    same literal query.

    A `+` asks for the **intersection** instead: both concepts, anywhere in
    the post, in either order. Unquoted terms are ANDed by GitHub, which the
    quoting rule above hides. That is the form that finds the good posts,
    because the good posts are always about two things at once - caching AND
    retrieval, context AND invalidation. Someone writing about only one of
    them is writing about something else.
    """
    parts = [p.strip().strip('"') for p in phrase.split(INTERSECT)]
    parts = [" ".join(p.split()) for p in parts if p.strip()]
    if not quote:
        return " ".join(parts)
    return " ".join(f'"{p}"' if " " in p else p for p in parts)


def build_query(
    phrase: str = "",
    repo: str | None = None,
    days: int = 30,
    exclude: list[str] | None = None,
    state: str | None = "open",
) -> str:
    """
    Build one search string, trimmed to fit GitHub's 256 character limit.

    Filters are dropped from the end if it would overflow. Dropping one
    widens the search, which is recoverable; going over the limit returns a
    422 and loses the query completely, which is not. The phrase is never
    dropped, because a search without its phrase is a different search.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()

    parts: list[str] = []
    if phrase:
        rendered = render_phrase(phrase)
        if rendered:
            parts.append(rendered)

    # /search/issues returns pull requests too, and someone's own patch is
    # almost never a marketing opportunity.
    parts.append("is:issue")

    # Open issues only, by default. A closed one is usually solved, and
    # arriving weeks later to comment on a problem somebody already fixed is
    # the wrong kind of outreach. Pass state=None to include everything.
    if state in ("open", "closed"):
        parts.append(f"is:{state}")

    parts.append(f"created:>={since}")

    if repo:
        parts.append(f"repo:{repo}")

    # Exclusions last: first to be sacrificed to the length limit, and GitHub
    # only allows five boolean operators anyway.
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
    state: str | None = "open",
) -> list[tuple[str, str]]:
    """
    One query per phrase, plus one per repository. Returns (label, query).

    Separate queries rather than one big boolean, because GitHub search has
    no grouping and a five-operator cap - "any of these fifteen phrases"
    cannot be expressed, so we just ask fifteen times.

    Repository queries carry no phrase at all. That is deliberate: every
    recent issue in a repo where our buyers already are becomes a candidate,
    which is how we find someone who described the problem in words we never
    thought of. A keyword-only search can never recover that.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    for phrase in phrases:
        clean = " ".join(phrase.split())
        if not clean:
            continue
        query = build_query(clean, days=days, exclude=exclude, state=state)
        if query not in seen:
            seen.add(query)
            out.append((f"phrase: {clean}", query))

    for repo in repos or []:
        query = build_query(repo=repo, days=days, state=state)
        if query not in seen:
            seen.add(query)
            out.append((f"repo: {repo}", query))

    return out


# ---------------------------------------------------------------- 2. mapping


def to_conversation(item: dict) -> Conversation | None:
    """
    One search result to a Conversation. None when it cannot be used.

    Returns None instead of raising so that one malformed item does not lose
    the other ninety-nine in the page.
    """
    try:
        source_id = str(item.get("node_id") or item.get("id") or "")
        url = item.get("html_url")
        created = item.get("created_at")
        if not source_id or not url or not created:
            return None

        user = item.get("user") or {}
        handle = user.get("login")
        reactions = item.get("reactions") or {}

        return Conversation(
            source="github",
            source_id=source_id,
            url=url,
            title=item.get("title"),
            body=item.get("body") or "",
            author=handle,
            author_is_bot=(user.get("type") == "Bot" or is_bot_login(handle)),
            created_at=datetime.fromisoformat(created.replace("Z", "+00:00")),
            score=_reactions(reactions),
            comments=int(item.get("comments") or 0),
            container=_repo(item),
            author_association=item.get("author_association"),
            labels=[
                label["name"]
                for label in item.get("labels") or []
                if isinstance(label, dict) and label.get("name")
            ],
        )
    except (TypeError, ValueError, KeyError):
        return None


def _reactions(reactions: dict) -> int:
    """Total reactions, ignoring the `url` key GitHub puts in the object."""
    total = reactions.get("total_count")
    if isinstance(total, int):
        return total
    return sum(v for k, v in reactions.items() if k != "url" and isinstance(v, int))


def _repo(item: dict) -> str | None:
    """"owner/name", from whichever field this response happens to carry."""
    api_url = item.get("repository_url") or ""
    match = _REPO_FROM_API_URL.search(str(api_url))
    if match:
        return match.group(1)
    parts = [p for p in str(item.get("html_url") or "").split("/") if p]
    return f"{parts[2]}/{parts[3]}" if len(parts) >= 4 else None


# ---------------------------------------------------------------- 3. fetching


#: Associations that mean the author works on the repository they posted in.
#:
#: A blocklist, after a spell as an allowlist of `{"NONE"}` alone. The
#: allowlist was safer in principle - GitHub keeps adding values, and a
#: blocklist lets each new one through - and far too strict in practice. It
#: removed about 80% of every result set, and the thing it removed most of
#: was CONTRIBUTOR.
#:
#: CONTRIBUTOR was excluded on the reasoning that a merged pull request means
#: you work on the project. Mostly it means you fixed a typo once. The
#: engaged power user who files the thoughtful feature request about caching
#: on llama.cpp or LibreChat is nearly always a CONTRIBUTOR, and they are
#: exactly who we are looking for: heavy user, hits real limits, has an
#: audience in the thread.
#:
#: What we actually want gone is people writing tickets in their own project,
#: and those three values name them precisely. A `None` association - which
#: happens - falls through and is kept, which is the right default.
INSIDER = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


REPO_URL = "https://api.github.com/repos"

#: Star counts, remembered between runs.
#:
#: Stars barely move week to week, and the same repositories come back run
#: after run, so looking them up once is the difference between a filter that
#: costs a minute and one that costs nothing.
_STARS_CACHE = Path(__file__).resolve().parents[3] / ".cache" / "repo_stars.json"


def _load_stars() -> dict[str, int]:
    try:
        return json.loads(_STARS_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_stars(stars: dict[str, int]) -> None:
    try:
        _STARS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _STARS_CACHE.write_text(json.dumps(stars), encoding="utf-8")
    except OSError:
        pass


async def repo_stars(
    client: httpx.AsyncClient, names: list[str]
) -> dict[str, int]:
    """
    How many stars each repository has. Unknown ones come back as -1.

    Uses the plain repository endpoint, which is on the 5,000-per-hour core
    limit rather than the 30-per-minute search limit, so this never competes
    with the search itself. Twelve at a time, because that is fast without
    tripping the secondary limit that punishes concurrency.
    """
    known = _load_stars()
    missing = [n for n in names if n and n not in known]

    if missing:
        headers = {"Accept": "application/vnd.github+json"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        semaphore = asyncio.Semaphore(12)

        async def one(name: str) -> None:
            async with semaphore:
                try:
                    response = await client.get(
                        f"{REPO_URL}/{name}", headers=headers, follow_redirects=True
                    )
                    known[name] = (
                        response.json().get("stargazers_count", 0)
                        if response.status_code == 200
                        else -1
                    )
                except Exception:
                    known[name] = -1

        await asyncio.gather(*(one(name) for name in missing))
        _save_stars(known)

    return {n: known.get(n, -1) for n in names if n}


async def repo_descriptions(
    client: httpx.AsyncClient, names: list[str]
) -> dict[str, str]:
    """
    What each repository says it is. Missing or unreachable ones come back "".

    Needed because a repository found by counting search hits arrives as a
    name and nothing else, and a name is far too little to judge relevance
    from - "Grace" and "jaeger" say nothing about what they are. The
    description is the one sentence the owner wrote to answer exactly that.

    On the plain repository endpoint, so this spends from the 5,000-an-hour
    core limit rather than the 30-a-minute search limit, and never competes
    with the search itself.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    out: dict[str, str] = {}
    semaphore = asyncio.Semaphore(12)

    async def one(name: str) -> None:
        async with semaphore:
            try:
                response = await client.get(
                    f"{REPO_URL}/{name}", headers=headers, follow_redirects=True
                )
                if response.status_code == 200:
                    payload = response.json()
                    out[name] = " ".join(
                        filter(None, [
                            (payload.get("description") or "")[:200],
                            " ".join(payload.get("topics") or [])[:100],
                        ])
                    )
                else:
                    out[name] = ""
            except Exception:
                out[name] = ""

    await asyncio.gather(*(one(n) for n in names if n))
    return out


#: Dead names we will spend a search request each trying to rescue.
#:
#: On the 30-a-minute search limit, unlike the rest of this checking, so it is
#: bounded rather than run over everything.
MAX_RESOLVE = 8


async def resolve_repo(client: httpx.AsyncClient, name: str) -> str | None:
    """
    Find the real repository behind a name whose owner is wrong.

    ── Why this is worth a search request ───────────────────────────────────

    A model asked to name competitors gets the *project* right and the owner
    wrong, almost every time: `cognee/cognee`, `mem0/mem0`, `GPTCache/GPTCache`
    and `Letta/Letta` are all real projects under an org nobody would guess -
    `topoteretes`, `mem0ai`, `zilliztech`, `letta-ai`.

    Checking those names 404s and, before this existed, dropped them. Which
    meant the plan asked for competitors, the model answered correctly, and
    every single answer was discarded on the prefix - leaving the slots to be
    filled by whatever a keyword search happened to turn up.

    The project half of the name is the half worth trusting, so that is what
    gets looked up.

    ── One lookup, not two ──────────────────────────────────────────────────

    This used to have its own implementation - most-starred repository whose
    name matches exactly - which is the same rule `find_repo_candidates` was
    written to replace, and it failed the same way. Asked to rescue
    `pinecone/pinecone` it answered `wmww/Pinecone`, "an unmaintained
    programming language", because that project really is called Pinecone and
    Pinecone's own repositories are not.

    Two functions answering one question is how a fix lands in one of them.
    """
    project = name.split("/")[-1].strip()
    if not project:
        return None

    try:
        # No star floor: this is rescuing a name somebody meant, and small
        # projects get their owner guessed wrong too.
        found = await find_repo_candidates(client, project, min_stars=0, limit=1)
    except Exception:
        return None

    return found[0]["full_name"] if found else None


async def check_repos(
    client: httpx.AsyncClient, repos: list[str]
) -> tuple[list[str], list[str]]:
    """
    Keep the repositories that exist, following renames. Returns (good, bad).

    Worth a request each because these come from a model's memory, and that
    memory is out of date: projects get renamed, move between organisations,
    or never existed under the name it recalled. A bad name does not fail
    quietly - GitHub rejects the whole search query with a wall of JSON.

    This uses the plain repository endpoint, which is on the 5,000-per-hour
    core limit rather than the 30-per-minute search limit. Checking ten names
    therefore costs nothing that the search itself needs.
    """
    good: list[str] = []
    bad: list[str] = []
    resolved_count = 0

    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    for repo in repos:
        name = repo.strip().strip("/")
        if not name or name.count("/") != 1:
            bad.append(f"{repo} (not in owner/name form)")
            continue

        try:
            response = await client.get(
                f"{REPO_URL}/{name}", headers=headers, follow_redirects=True
            )
        except Exception:
            # Unreachable is not the same as wrong. Keep it and let the
            # search decide.
            good.append(name)
            continue

        if response.status_code == 200:
            payload = response.json()
            # Use the name GitHub gives back, which is the current one after
            # any rename. Searching the old name returns nothing at all.
            actual = payload.get("full_name") or name

            dead = _why_unusable(payload)
            if dead:
                # No "skipped" here: the caller prefixes it, and saying it
                # twice is how a note reads "skipped X skipped - ...".
                bad.append(f"{actual} - {dead}")
                continue

            good.append(actual)
            if actual.lower() != name.lower():
                bad.append(f"{name} was renamed to {actual}")
        elif response.status_code == 404:
            # The project is usually real and the owner usually guessed. Try
            # to find it before throwing the name away, but only for the
            # first few - this costs a search request each.
            resolved = None
            if resolved_count < MAX_RESOLVE:
                resolved_count += 1
                resolved = await resolve_repo(client, name)

            if resolved and resolved.lower() not in {g.lower() for g in good}:
                good.append(resolved)
                bad.append(f"{name} does not exist - used {resolved} instead")
            else:
                bad.append(f"{name} does not exist")
        else:
            good.append(name)

    return good, bad


async def find_repos(
    client: httpx.AsyncClient,
    topic: str,
    min_stars: int = 500,
    limit: int = 12,
) -> list[dict]:
    """
    Ask GitHub which repositories match a topic, most starred first.

    The alternative is asking a model to recall repository names, which is
    how `microsoft/DeepSpeed` and `haystack-ai/haystack` ended up in a plan:
    one had moved organisation, the other never existed. GitHub knows what
    exists today; the model knows what existed when it was trained.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    response = await client.get(
        "https://api.github.com/search/repositories",
        params={
            "q": f"{topic} stars:>={min_stars}",
            "sort": "stars",
            "order": "desc",
            "per_page": min(limit, 30),
        },
        headers=headers,
    )
    if response.status_code != 200:
        return []

    return [
        {
            "full_name": item["full_name"],
            "description": (item.get("description") or "")[:160],
            "stars": item.get("stargazers_count", 0),
            "open_issues": item.get("open_issues_count", 0),
        }
        for item in response.json().get("items", [])
    ]


#: How long since the last commit before a project counts as dormant.
#:
#: Generous on purpose, and it is a different question from "is this project
#: healthy". A competitor whose product has stalled is a *good* place to be -
#: its tracker fills up with people who cannot get what they need any more.
#: What is worthless is a repository nobody has touched in years, where the
#: last few issues predate the problem we are searching for.
#:
#: Eighteen months keeps the stalled-but-alive and drops the museum pieces.
DORMANT_AFTER_DAYS = 548


def _why_unusable(payload: dict) -> str | None:
    """
    Why this repository cannot be swept, or None if it can be.

    Every fact here arrives in a response we were already making and used to
    throw away, which is what let a real plan spend slots on
    `allenai/allennlp` (archived, last touched November 2022) and
    `facebookresearch/DPR` (archived, April 2023).

    Archiving is the one that matters most and is completely unambiguous: an
    archived repository is read-only, so there is no reply box. It is not a
    weak lead, it is an impossible one - and no amount of prompting stops a
    model recalling famous names, because they are famous precisely for
    having mattered a long time ago.
    """
    if payload.get("archived"):
        return "the repository is archived, so nobody can reply there"
    if payload.get("disabled"):
        return "the repository is disabled"
    if not payload.get("has_issues", True):
        return "issues are turned off"

    pushed = payload.get("pushed_at")
    if pushed:
        try:
            last = datetime.fromisoformat(str(pushed).replace("Z", "+00:00"))
        except ValueError:
            return None
        age = (datetime.now(UTC) - last).days
        if age > DORMANT_AFTER_DAYS:
            return f"nothing has been pushed there in {age // 30} months"

    return None


def _slug(text: str) -> str:
    """A name reduced to comparable letters: "GPT-Cache" and "gptcache" match."""
    return "".join(c for c in text.lower() if c.isalnum())


async def repos_with_discussions(
    client: httpx.AsyncClient, names: list[str]
) -> list[str]:
    """
    Of these repositories, the ones that actually have Discussions turned on.

    Worth a request each because the two limits are not the same currency. A
    repository with Discussions disabled answers a discussion sweep with an
    empty page and no error, so the cost is a *search* request - 30 a minute,
    and the thing the run runs out of. This check spends from the core limit
    instead, which is 5,000 an hour and otherwise idle.

    Measured against one real sweep list: eight of sixteen repositories had
    Discussions off, so a quarter of that run's discussion budget bought
    nothing while three phrase queries were cut short for want of it.

    Note that "returned nothing" is the larger set and not the same thing -
    `langchain-ai/langchain` has Discussions enabled and still matched no
    posts. Only the ones that *cannot* answer are worth skipping.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    semaphore = asyncio.Semaphore(8)
    keep: list[str] = []

    async def one(name: str) -> None:
        async with semaphore:
            try:
                response = await client.get(
                    f"{REPO_URL}/{name}", headers=headers, follow_redirects=True
                )
            except Exception:
                # Unknown is not the same as off. Keep it and let the sweep
                # decide, as everywhere else.
                keep.append(name)
                return
            if response.status_code != 200 or response.json().get("has_discussions"):
                keep.append(name)

    await asyncio.gather(*(one(n) for n in names if n))

    # Caller order, not completion order, so the sweep stays predictable.
    kept = set(keep)
    return [n for n in names if n in kept]


async def find_repo_candidates(
    client: httpx.AsyncClient, name: str, min_stars: int = 200, limit: int = 4
) -> list[dict]:
    """
    Repositories that might be a product's own. Best first, empty if unsure.

    Returns several rather than one because the right organisation still has
    the wrong repository in it: Pinecone's busiest is `pinecone-io/examples`,
    a folder of notebooks, while the one worth sweeping is `pinecone-io/
    canopy`, their RAG framework. Name matching cannot tell those apart -
    only the description can, and that check belongs to the caller, which
    knows what the product is.

    `find_repos` is the wrong tool for this and fails loudly: it sorts by
    stars, so it answers "the most popular repository that mentions this
    word" rather than "the repository called this". Asked for `mem0` it
    returns a 92,000 star project called claude-mem; asked for `Haystack` it
    returns funNLP; asked for `LangChain`, markitdown.

    Two changes fix that. `in:name` stops the description and README from
    matching at all, and the result is then required to *be* the name rather
    than merely rank first for it.

    ── The owner matters more than the repository ────────────────────────

    Matching only the repository name is still not enough, and Pinecone is
    the case that proves it. There is no repository called exactly
    `pinecone` belonging to Pinecone - the company's code lives in
    `pinecone-io/canopy`, `pinecone-io/python-sdk` and friends. So an exact
    name rule rejects every correct answer, and then happily accepts
    `wmww/Pinecone` ("an unmaintained programming language") and
    `matrix-org/pinecone` ("peer-to-peer overlay routing for the Matrix
    ecosystem"), because those two genuinely are called that.

    An organisation named after the product is much stronger evidence than a
    repository that happens to share a word, so owner matches are preferred
    outright and a name match is only the fallback. Within either group the
    busiest tracker wins, since issues are the entire reason we want it.

    Returns None rather than a best guess. A wrong repository here is not a
    near miss - it is a whole sweep spent on a project with no connection to
    the product, which is worse than the empty slot it filled.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    response = await client.get(
        "https://api.github.com/search/repositories",
        params={
            "q": f"{name} in:name stars:>={min_stars}",
            "sort": "stars",
            "order": "desc",
            "per_page": 20,
        },
        headers=headers,
    )
    if response.status_code != 200:
        return []

    target = _slug(name)
    by_owner: list[dict] = []
    by_name: list[dict] = []

    for item in response.json().get("items", []):
        # The search response carries this, so an archived competitor costs
        # nothing to avoid here - and costs a whole slot if it gets through.
        # Both `pinecone-io/canopy` and `weaviate/Verba` were resolved
        # correctly, added, and then thrown away by the archived check three
        # steps later, having displaced something usable on the way.
        if item.get("archived") or item.get("disabled"):
            continue

        owner, _, short = item["full_name"].partition("/")
        info = {
            "full_name": item["full_name"],
            "description": (item.get("description") or "")[:160],
            "stars": item.get("stargazers_count", 0),
            "open_issues": item.get("open_issues_count", 0),
        }
        if _is_owner_for(owner, target):
            by_owner.append(info)
        elif _slug(short) == target:
            by_name.append(info)

    # Owner matches outrank name matches, however popular the name match is.
    pool = by_owner or by_name
    # Busiest first: issues are the entire reason we want the repository.
    pool.sort(key=lambda info: -info["open_issues"])
    return pool[:limit]


#: What an organisation adds to a product's name when it registers one.
#:
#: The list exists because the obvious rule - does the owner *start with* the
#: product name - is far too loose on short names, and quietly wrong on long
#: ones. It matched `zephyrproject-rtos` for "Zep", `haystackeditor` for
#: "Haystack" and `langchain4j` for "LangChain": three different products,
#: each stealing the slot belonging to the real one.
#:
#: Requiring the remainder to be a corporate suffix keeps `pinecone-io`,
#: `mem0ai` and `langchain-ai` while rejecting all three of those.
_OWNER_SUFFIXES = frozenset(
    {
        "", "io", "ai", "ml", "hq", "inc", "co", "org", "oss", "dev", "app",
        "labs", "lab", "team", "tech", "cloud", "systems", "group", "project",
    }
)


#: And what it puts in front, when the bare name was already taken.
#:
#: `getzep`, `getsentry`, `getdbt`, `usebruno` - a standard startup move once
#: the plain name is gone. Without this, "Zep" skips its own organisation
#: entirely and matches `Rezonality/zep`, a C++ text editor widget that
#: happens to be spelled the same.
_OWNER_PREFIXES = ("get", "use", "try", "go", "the")


def _is_owner_for(owner: str, target: str) -> bool:
    """Is this organisation the one named after the product?"""
    slug = _slug(owner)

    for prefix in ("", *_OWNER_PREFIXES):
        if not slug.startswith(prefix + target):
            continue
        if slug[len(prefix) + len(target) :] in _OWNER_SUFFIXES:
            return True

    return False


async def find_repo_by_name(
    client: httpx.AsyncClient, name: str, min_stars: int = 200
) -> dict | None:
    """The single best candidate, or None. See `find_repo_candidates`."""
    found = await find_repo_candidates(client, name, min_stars=min_stars, limit=1)
    return found[0] if found else None


async def repos_by_hits(
    phrases: list[str],
    days: int = 180,
    limit: int = 12,
    min_stars: int = 500,
    max_requests: int = 6,
) -> list[tuple[str, int]]:
    """
    Find repositories by searching for the problem and counting who turns up.

    Returns (repo, hits), most hits first.

    ── Why not just ask GitHub for matching repositories ─────────────────

    Because `find_repos` searches repository *names and descriptions*, and a
    description is a marketing sentence about what a project is, not evidence
    that anybody there has this problem. Ranking those by similarity to the
    product reliably surfaces the big framework repos - they describe
    themselves in the same vocabulary the product does - and reliably misses
    the places the conversations actually happen. One real run picked
    llama_index, langchain and claude-code that way, while the leads a person
    found by hand were in open-webui, llama.cpp, LibreChat and vanna.

    So this asks the opposite question. Run the phrase searches across the
    whole of GitHub first, then count which repositories the matching posts
    came from. A repository that produced eleven posts about this problem in
    six months has demonstrated it, and no description had to be trusted.

    Deliberately searches without a state filter and over a long window: this
    is measuring where a topic lives, and a closed issue is evidence of that
    just as much as an open one.
    """
    if not phrases:
        return []

    result = await search(
        phrases,
        days=days,
        max_requests=max_requests,
        state=None,
        drop_bots=True,
        # Both filters off on purpose. This is counting where a conversation
        # happens, and an owner talking about the problem in their own repo
        # is still proof that it is discussed there - even though they are
        # not a lead themselves.
        outsiders_only=False,
        min_repo_stars=0,
    )

    hits: dict[str, int] = {}
    for conversation in result.conversations:
        if conversation.container:
            hits[conversation.container] = hits.get(conversation.container, 0) + 1

    #: One post proves nothing - every phrase has a long tail of one-offs
    #: from repositories that mentioned it once in passing.
    ranked = [(repo, n) for repo, n in hits.items() if n >= 2]
    ranked.sort(key=lambda pair: (-pair[1], pair[0]))

    if not ranked or min_stars <= 0:
        return ranked[:limit]

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        stars = await repo_stars(client, [repo for repo, _ in ranked[: limit * 3]])

    return [
        (repo, n)
        for repo, n in ranked
        # Unknown (-1) is kept, as everywhere else: a failed lookup is not
        # evidence of a small project.
        if stars.get(repo, -1) < 0 or stars.get(repo, -1) >= min_stars
    ][:limit]


async def search(
    phrases: list[str],
    repos: list[str] | None = None,
    days: int = 30,
    exclude: list[str] | None = None,
    max_requests: int = 10,
    drop_bots: bool = True,
    outsiders_only: bool = False,
    state: str | None = "open",
    min_repo_stars: int = 0,
) -> SearchResult:
    """
    Run every query and collect the results.

    Queries are paged **round robin**: page one of every query, then page two
    of every query, and so on. Running them one at a time looks simpler and
    is much worse - a phrase matching 90,000 issues will happily take ten
    pages of a twenty request budget, all chosen by GitHub's idea of
    relevance rather than ours, while the last three phrases never run at
    all. When every phrase matches thousands, breadth beats depth.

    A failing query is noted and dropped rather than raised, so one bad
    phrase does not cost the others.
    """
    result = SearchResult()
    seen: set[str] = set()

    if not settings.github_token:
        result.notes.append("No GITHUB_TOKEN set: 10 requests a minute instead of 30.")

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as checker:
        # Before spending any of the search budget. One bad name otherwise
        # costs a request and returns a wall of GitHub's JSON instead of an
        # explanation.
        if repos:
            repos, problems = await check_repos(checker, repos)
            for problem in problems:
                result.notes.append(f"  skipped {problem}")

    queries = build_queries(phrases, repos, days, exclude, state)

    #: label -> how many new conversations it contributed
    found: dict[str, int] = {label: 0 for label, _ in queries}
    #: Queries with nothing left to give, or that failed.
    done: set[str] = set()
    stopped_early = False

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        page = 1
        while page * PER_PAGE <= HARD_RESULT_CAP and len(done) < len(queries):
            for label, query in queries:
                if label in done:
                    continue
                if result.requests_made >= max_requests:
                    stopped_early = True
                    break

                try:
                    added, exhausted = await _fetch_page(
                        client, query, page, result, seen, label
                    )
                except Exception as exc:
                    log.warning("github.query_failed", label=label, error=str(exc))
                    result.notes.append(f"{label} failed: {exc}")
                    done.add(label)
                    continue

                found[label] += added
                if exhausted:
                    done.add(label)

            if stopped_early:
                break
            page += 1

    for label, _ in queries:
        result.notes.append(f"{label} -> {found[label]}")
        if found[label] == 0 and label.startswith("phrase: "):
            hint = _why_nothing(label.removeprefix("phrase: "))
            if hint:
                result.notes.append(f"    {hint}")

    if stopped_early:
        left = len(queries) - len(done)
        result.notes.append(
            f"Stopped at the {max_requests} request limit with {left} "
            f"quer{'y' if left == 1 else 'ies'} still having more to give. "
            f"Fewer, narrower queries would go deeper."
        )

    _apply_filters(result, drop_bots=drop_bots, outsiders_only=outsiders_only)

    if min_repo_stars > 0:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            await _drop_small_repos(client, result, min_repo_stars)

    return result


async def _drop_small_repos(
    client: httpx.AsyncClient, result: SearchResult, minimum: int
) -> None:
    """
    Remove results from projects too small to be worth replying in.

    Phrase searches cover the whole of GitHub, so they pull in one-person
    side projects alongside the real ones. Commenting in a repository with
    four stars reaches nobody: there is no audience reading it, and the
    author is usually the only person who ever will.

    Repository searches are unaffected in practice, because those are
    projects somebody chose deliberately.
    """
    names = sorted({c.container for c in result.conversations if c.container})
    if not names:
        return

    stars = await repo_stars(client, names)

    kept: list[Conversation] = []
    dropped = 0
    for conversation in result.conversations:
        count = stars.get(conversation.container or "", -1)
        # Unknown stays. A lookup that failed is not evidence of a small
        # project, and silently discarding on a network hiccup is worse than
        # showing one extra result.
        if count >= 0 and count < minimum:
            dropped += 1
            continue
        kept.append(conversation)

    if dropped:
        result.notes.append(
            f"dropped {dropped} from repositories under {minimum:,} stars"
        )
    result.conversations = kept


async def _fetch_page(
    client: httpx.AsyncClient,
    query: str,
    page: int,
    result: SearchResult,
    seen: set[str],
    label: str = "",
) -> tuple[int, bool]:
    """
    One page of one query. Returns (new conversations, nothing left).

    "Nothing left" means a short page - GitHub gave us fewer than it could,
    so there is no point asking for the next one.

    `label` is stamped on every conversation this page produced, which is the
    only moment that association exists - `seen` means a post is credited to
    the first query that found it and never appears again.
    """
    payload = await _get(client, {"q": query, "per_page": PER_PAGE, "page": page})
    result.requests_made += 1

    items = payload.get("items") or []
    if not items:
        return 0, True

    total = int(payload.get("total_count") or 0)
    if page == 1 and total > HARD_RESULT_CAP:
        # Say so rather than letting a run silently see a fraction of what
        # matched. The fix is a narrower phrase, not more pages.
        result.notes.append(
            f"  matched {total:,} but GitHub serves at most {HARD_RESULT_CAP} "
            f"- this phrase is too broad to be precise"
        )

    added = 0
    for item in items:
        if "pull_request" in item:
            continue
        conversation = to_conversation(item)
        if conversation is None:
            continue
        key = f"{conversation.source}:{conversation.source_id}"
        if key in seen:
            continue
        seen.add(key)
        conversation.found_by = label
        result.conversations.append(conversation)
        added += 1

    return added, len(items) < PER_PAGE


def _why_nothing(phrase: str) -> str | None:
    """
    Explain an empty phrase query, because the reason is never obvious.

    A plain phrase is searched as an exact quoted string. That works for
    terms of art - "stale embeddings" is a fixed compound people reuse
    verbatim - and fails completely for anything sentence-shaped, because
    nobody writes the same sentence twice.

    The instinct to search for how a frustrated person *talks* is right. It
    just belongs in the `product` text, where the embedding matches meaning,
    not here, where GitHub matches characters.
    """
    sides = [s.strip() for s in phrase.split(INTERSECT) if s.strip()]

    # An intersection that matches nothing is over-narrow, not over-long -
    # the opposite problem, and the opposite advice.
    if len(sides) > 1:
        return (
            f"both halves had to appear in the same post and none did. Try "
            f"dropping one side, or widening it to just \"{sides[0]}\"."
        )

    words = phrase.split()
    if len(words) >= 4:
        return (
            f"searched as the exact string \"{phrase}\" - too sentence-like to "
            f"match anything. Try a 2-3 word fragment such as "
            f"\"{' '.join(words[-2:])}\", and put the full description in "
            f"`product` instead."
        )
    return "no matches. Try a broader term, or add a repo to sweep."


def _apply_filters(
    result: SearchResult, *, drop_bots: bool, outsiders_only: bool
) -> None:
    """
    Drop the obvious non-leads, and say how many went and why.

    Filtering after fetching rather than in the query, because GitHub search
    cannot express either of these. Reporting the counts matters as much as
    the filtering: "found 12" is alarming on its own, and unremarkable next
    to "dropped 180 written by repo owners".
    """
    kept: list[Conversation] = []
    dropped_bots = 0
    dropped_insiders = 0

    for conversation in result.conversations:
        if drop_bots and conversation.author_is_bot:
            dropped_bots += 1
            continue
        if outsiders_only and conversation.author_association in INSIDER:
            dropped_insiders += 1
            continue
        kept.append(conversation)

    if dropped_bots:
        result.notes.append(f"dropped {dropped_bots} bot-authored")
    if dropped_insiders:
        result.notes.append(
            f"dropped {dropped_insiders} written by people who work on that repo "
            f"(owner, member or collaborator)"
        )

    result.conversations = kept


async def _run_one(
    client: httpx.AsyncClient,
    query: str,
    result: SearchResult,
    seen: set[str],
    max_requests: int,
) -> int:
    """Page through one query. Returns how many new conversations it added."""
    added = 0
    page = 1

    while result.requests_made < max_requests and page * PER_PAGE <= HARD_RESULT_CAP:
        # No `sort` parameter, which means GitHub's own best-match ordering.
        #
        # Sorting by `created` looks sensible and is actively harmful here: a
        # query matching 89,000 issues only ever serves 1,000, so sorting by
        # date means the 1,000 *newest* rather than the 1,000 *best*. The
        # date window is already pinned by `created:>=` in the query, so
        # relevance ordering costs no recency and gains a far better sample.
        payload = await _get(
            client,
            {"q": query, "per_page": PER_PAGE, "page": page},
        )
        result.requests_made += 1

        items = payload.get("items") or []
        if not items:
            break

        total = int(payload.get("total_count") or 0)
        if page == 1 and total > HARD_RESULT_CAP:
            # Say so rather than letting a run silently see a tenth of what
            # exists. The fix is a narrower date window, not more pages.
            result.notes.append(
                f"  matched {total:,} but GitHub serves at most {HARD_RESULT_CAP}"
            )

        for item in items:
            if "pull_request" in item:
                continue
            conversation = to_conversation(item)
            if conversation is None:
                continue
            key = f"{conversation.source}:{conversation.source_id}"
            if key in seen:
                continue
            seen.add(key)
            result.conversations.append(conversation)
            added += 1

        if len(items) < PER_PAGE:
            break
        page += 1

    return added


#: Smallest gap between two search requests.
#:
#: ── Why paying a second per request is cheaper than not ──────────────────
#:
#: GitHub has a second, undocumented-by-number limit beside the 30 per
#: minute: a *secondary* limit that fires when requests arrive too fast
#: together, however much primary quota is left. It answers 403 with no
#: rate-limit headers at all, which is why `_retry_after` falls back to a
#: flat minute for it.
#:
#: A real run tripped it three times and spent three minutes asleep out of
#: six. Spacing 58 requests a second apart costs 58 seconds instead, and
#: that time is spent fetching rather than waiting - so the run gets both
#: faster and more complete.
SEARCH_SPACING_SECONDS = 1.0

_pace_lock = asyncio.Lock()
_last_search_at = 0.0


async def _pace() -> None:
    """Hold the caller until a request may be sent without crowding."""
    global _last_search_at
    async with _pace_lock:
        since = time.monotonic() - _last_search_at
        if since < SEARCH_SPACING_SECONDS:
            await asyncio.sleep(SEARCH_SPACING_SECONDS - since)
        _last_search_at = time.monotonic()


async def _get(client: httpx.AsyncClient, params: dict) -> dict:
    """
    One request, waiting as long as GitHub asks when it says to wait.

    Rate limiting arrives as 403 or 429 with a Retry-After header. When a
    server tells you exactly how long to wait, guessing is worse.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    for attempt in range(3):
        await _pace()
        try:
            response = await client.get(SEARCH_URL, params=params, headers=headers)
        except (httpx.TransportError, httpx.RemoteProtocolError) as exc:
            # A dropped connection is not an answer. Without this, one
            # network hiccup ends a query permanently and quietly costs the
            # run several hundred results.
            if attempt == 2:
                raise RuntimeError(f"GitHub connection failed: {exc}") from exc
            log.info("github.retrying", attempt=attempt, error=str(exc))
            await asyncio.sleep(1.5 * (attempt + 1))
            continue

        if response.status_code == 200:
            return response.json()

        if response.status_code in (403, 429):
            wait = _retry_after(response)
            if wait is None:
                raise RuntimeError(
                    "GitHub returned 403 with no rate-limit headers. "
                    "The token is probably invalid."
                )
            log.warning("github.rate_limited", wait_seconds=wait)
            await asyncio.sleep(min(wait, 60))
            continue

        if response.status_code == 422:
            raise RuntimeError(f"GitHub rejected the query: {response.text[:200]}")

        response.raise_for_status()

    raise RuntimeError("Still rate limited after three attempts.")


def _retry_after(response: httpx.Response) -> float | None:
    """How long GitHub wants us to wait, or None if this is not a rate limit."""
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

    # Secondary limits sometimes arrive with neither header.
    if "secondary rate limit" in response.text.lower():
        return 60.0

    return None
