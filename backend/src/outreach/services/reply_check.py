"""
Look at the threads again and say whether anybody answered.

The `answered` stage of the funnel is the only automatic one after drafting,
and nothing used to fill it: the fields existed, the counting existed, and
no code ever went back to a thread. This is that code.

What "answered" means, per platform:

  * GitHub issues and discussions read top to bottom, so it is somebody
    other than you commenting after your comment.
  * Hacker News is a tree, and a busy story gets hundreds of comments that
    have nothing to do with you. There it means a reply *to your comment*.

Both need to know which comment is yours. The link you paste when marking a
reply posted says so directly. Without one, the thread is searched for the
draft we wrote - people mostly post it with light edits, and a draft is long
and specific enough not to match anything else. When neither finds it, the
post is left at `posted`. Counting new comments instead would mark every
busy thread answered whether you turned up or not, which is the number this
funnel exists to not make up.

Runs when a screen that shows the funnel is opened, not on a timer: there is
no worker process yet, and a check nobody looks at is rate limit spent on
nothing.
"""

from __future__ import annotations

import asyncio
import html
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import structlog

from outreach.config import settings
from outreach.connectors.github import is_bot_login
from outreach.db.models.tracked_post import TrackedPost, TrackState
from outreach.db.repositories import tracked_posts as repo
from outreach.db.session import session_scope

log = structlog.get_logger(__name__)

#: A post is looked at again at most this often, however many times the
#: screen is opened.
RECHECK_AFTER = timedelta(minutes=10)

#: Posts per check. Every one is a request or two against the same GitHub
#: allowance the search spends.
MAX_POSTS = 25

#: Issue comments, 100 a page.
MAX_COMMENT_PAGES = 5

#: How alike a comment and the draft must be to call the comment yours.
#: Measured on overlapping three-word runs, so reordering a sentence or
#: trimming a paragraph still matches and a stranger quoting one line does
#: not.
MATCH_AT = 0.5

GITHUB_API = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"
HN_ITEM_API = "https://hn.algolia.com/api/v1/items/{}"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={}"

_ISSUE = re.compile(r"github\.com/([^/]+)/([^/]+)/(issues|pull|discussions)/(\d+)")

DISCUSSION_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    discussion(number: $number) {
      comments(last: 100) {
        nodes {
          databaseId createdAt body url author { login }
          replies(last: 50) {
            nodes { databaseId createdAt body url author { login } }
          }
        }
      }
    }
  }
}
"""


class RateLimited(Exception):
    """Stop the whole check; the next one picks up where this left off."""


class CheckFailed(Exception):
    """This post could not be checked. The others still can."""


@dataclass(frozen=True)
class Comment:
    id: str
    author: str | None
    created_at: datetime
    text: str
    url: str
    #: The comment this one answers, or None at the top of the thread.
    parent_id: str | None = None


@dataclass(frozen=True)
class Verdict:
    ours: Comment
    replies: list[Comment]
    author_replied: bool


# ------------------------------------------------------------ pure logic


def comment_id(url: str | None) -> str | None:
    """
    Your comment's id out of the link you pasted, or None.

    `...#issuecomment-456789` and `...#discussioncomment-456789` on GitHub;
    `item?id=456789` on Hacker News, where a comment's permalink is its own
    item page.
    """
    if not url:
        return None
    parsed = urlparse(url.strip())
    if parsed.netloc.endswith("news.ycombinator.com"):
        found = parse_qs(parsed.query).get("id", [""])[0]
        return found if found.isdigit() else None
    if not parsed.fragment:
        return None
    digits = parsed.fragment.rsplit("-", 1)[-1]
    return digits if digits.isdigit() else None


_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[a-z0-9]+")


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = _WORD.findall(html.unescape(_TAG.sub(" ", text)).lower())
    return {tuple(words[i : i + 3]) for i in range(len(words) - 2)}


def likeness(a: str, b: str) -> float:
    """0 to 1: how much of the wording two texts share."""
    left, right = _shingles(a), _shingles(b)
    # Too short to tell a reply apart from "thanks, this helped".
    if min(len(left), len(right)) < 4:
        return 0.0
    return 2 * len(left & right) / (len(left) + len(right))


def find_ours(comments: list[Comment], *, our_id: str | None, draft: str | None) -> Comment | None:
    """Your comment: by the id you gave us, else by the draft's wording."""
    if our_id:
        return next((c for c in comments if c.id == our_id), None)
    if not draft:
        return None

    scored = [(likeness(c.text, draft), c) for c in comments]
    matches = [(s, c) for s, c in scored if s >= MATCH_AT]
    if not matches:
        return None
    # The best match, and the earliest on a tie: somebody quoting your whole
    # comment back scores as well as the comment itself, and comes after it.
    return min(matches, key=lambda sc: (-sc[0], sc[1].created_at))[1]


def judge(
    comments: list[Comment],
    *,
    our_id: str | None,
    draft: str | None,
    post_author: str | None,
    threaded: bool,
) -> Verdict | None:
    """Who answered you, or None when your comment is not in the thread."""
    ours = find_ours(comments, our_id=our_id, draft=draft)
    if ours is None:
        return None

    def by_someone_else(c: Comment) -> bool:
        return bool(c.author) and c.author != ours.author and not is_bot_login(c.author)

    if threaded:
        children: dict[str, list[Comment]] = {}
        for c in comments:
            if c.parent_id:
                children.setdefault(c.parent_id, []).append(c)
        # Everything under yours, however deep: a reply to a reply to you is
        # still the conversation you started.
        replies = []
        waiting = [ours.id]
        while waiting:
            for c in children.get(waiting.pop(), []):
                waiting.append(c.id)
                if by_someone_else(c):
                    replies.append(c)
    else:
        replies = [c for c in comments if c.created_at > ours.created_at and by_someone_else(c)]

    wrote_it = (post_author or "").lower()
    return Verdict(
        ours=ours,
        replies=replies,
        author_replied=bool(wrote_it)
        and any((c.author or "").lower() == wrote_it for c in replies),
    )


def apply(post: TrackedPost, verdict: Verdict | None, now: datetime) -> bool:
    """Write a check's answer onto the row. True when anything visible changed."""
    before = (post.state, post.replies_after, post.author_replied, post.our_comment_url)
    post.last_checked_at = now

    if verdict is not None:
        post.our_comment_id = verdict.ours.id
        # Found by the draft's wording: now the post can say it is linked.
        post.our_comment_url = post.our_comment_url or verdict.ours.url
        post.replies_after = len(verdict.replies)
        post.author_replied = verdict.author_replied
        # Only ever forward. Answered is what we were waiting for, and a
        # reply that is later deleted does not un-answer anything.
        if verdict.replies and post.state == TrackState.POSTED:
            post.state = TrackState.ANSWERED

    after = (post.state, post.replies_after, post.author_replied, post.our_comment_url)
    return before != after


# ------------------------------------------------------------- fetching


def _when(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _call(
    client: httpx.AsyncClient, method: str, url: str, **kwargs
) -> httpx.Response | None:
    """One request. None for a thread that is gone; raises for the rest."""
    for attempt in range(3):
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            if attempt == 2:
                raise CheckFailed(f"connection failed: {exc}") from exc
            await asyncio.sleep(1.0 * (attempt + 1))
            continue

        if response.status_code in (404, 410):
            return None
        if response.status_code == 429 or (
            response.status_code == 403
            and (
                response.headers.get("x-ratelimit-remaining") == "0"
                or "rate limit" in response.text.lower()
            )
        ):
            # Waiting would hold a page open for a minute. Stop instead.
            raise RateLimited(url)
        if response.status_code >= 500 and attempt < 2:
            await asyncio.sleep(1.0 * (attempt + 1))
            continue
        if response.status_code != 200:
            raise CheckFailed(f"{response.status_code} from {url}")
        return response

    raise CheckFailed(f"no answer from {url}")


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


async def github_issue_comments(
    client: httpx.AsyncClient, owner: str, name: str, number: str, since: datetime
) -> list[Comment]:
    comments: list[Comment] = []
    for page in range(1, MAX_COMMENT_PAGES + 1):
        response = await _call(
            client,
            "GET",
            f"{GITHUB_API}/repos/{owner}/{name}/issues/{number}/comments",
            params={"since": since.isoformat(), "per_page": 100, "page": page},
            headers=_github_headers(),
        )
        if response is None:
            break
        batch = response.json()
        comments += [
            Comment(
                id=str(item["id"]),
                author=(item.get("user") or {}).get("login"),
                created_at=_when(item["created_at"]),
                text=item.get("body") or "",
                url=item.get("html_url") or "",
            )
            for item in batch
        ]
        if len(batch) < 100:
            break
    return comments


async def github_discussion_comments(
    client: httpx.AsyncClient, owner: str, name: str, number: str
) -> list[Comment]:
    if not settings.github_token:
        # GraphQL refuses anonymous requests outright.
        raise CheckFailed("discussions need GITHUB_TOKEN")

    response = await _call(
        client,
        "POST",
        GRAPHQL_URL,
        json={
            "query": DISCUSSION_QUERY,
            "variables": {"owner": owner, "name": name, "number": int(number)},
        },
        headers=_github_headers(),
    )
    if response is None:
        return []
    payload = response.json()
    errors = payload.get("errors") or []
    if any(e.get("type") == "RATE_LIMITED" for e in errors):
        raise RateLimited(GRAPHQL_URL)

    discussion = ((payload.get("data") or {}).get("repository") or {}).get("discussion")
    if not discussion:
        return []

    def one(node: dict, parent: str | None) -> Comment:
        return Comment(
            id=str(node["databaseId"]),
            author=(node.get("author") or {}).get("login"),
            created_at=_when(node["createdAt"]),
            text=node.get("body") or "",
            url=node.get("url") or "",
            parent_id=parent,
        )

    comments: list[Comment] = []
    for node in discussion["comments"]["nodes"]:
        top = one(node, None)
        comments.append(top)
        comments += [one(reply, top.id) for reply in node["replies"]["nodes"]]
    return comments


async def hn_thread(client: httpx.AsyncClient, item_id: str) -> list[Comment]:
    """The item and everything under it, flattened, parents first."""
    response = await _call(client, "GET", HN_ITEM_API.format(item_id))
    if response is None:
        return []

    comments: list[Comment] = []
    stack: list[tuple[dict, str | None]] = [(response.json(), None)]
    while stack:
        node, parent = stack.pop()
        comments.append(
            Comment(
                id=str(node["id"]),
                author=node.get("author"),
                created_at=datetime.fromtimestamp(int(node.get("created_at_i") or 0), UTC),
                text=node.get("text") or "",
                url=HN_ITEM_URL.format(node["id"]),
                parent_id=parent,
            )
        )
        stack += [(child, str(node["id"])) for child in node.get("children") or []]
    return comments


async def check_post(client: httpx.AsyncClient, post: TrackedPost) -> Verdict | None:
    """Fetch the thread and judge it. None when your comment is not found."""
    our_id = post.our_comment_id or comment_id(post.our_comment_url)

    if post.source == "hackernews":
        # With your comment's id, only its own replies are needed - a big
        # story's whole tree is megabytes.
        comments = await hn_thread(client, our_id or post.source_id)
        return judge(
            comments,
            our_id=our_id,
            draft=post.draft,
            post_author=post.author,
            threaded=True,
        )

    if post.source == "github":
        found = _ISSUE.search(post.url)
        if not found:
            raise CheckFailed(f"not a GitHub thread: {post.url}")
        owner, name, kind, number = found.groups()
        if kind == "discussions":
            comments = await github_discussion_comments(client, owner, name, number)
        else:
            # Your comment cannot predate the draft it was written from.
            # A day of slack covers clocks and a draft written again later.
            known = [t for t in (post.drafted_at, post.posted_at) if t]
            start = min(known) if known else datetime.now(UTC) - timedelta(days=90)
            comments = await github_issue_comments(
                client, owner, name, number, start - timedelta(days=1)
            )
        return judge(
            comments,
            our_id=our_id,
            draft=post.draft,
            post_author=post.author,
            threaded=False,
        )

    raise CheckFailed(f"no reply check for {post.source}")


# ------------------------------------------------------------ the batch

#: One check at a time per account and scope. A second request for the same
#: thing - React's development double render, two tabs - waits for the one
#: already running and gets its answer, instead of fetching every thread
#: again.
_running: dict[tuple[uuid.UUID, uuid.UUID | None], asyncio.Task[dict[str, int]]] = {}


async def check_due(user_id: uuid.UUID, product_id: uuid.UUID | None = None) -> dict[str, int]:
    """Check the posted replies that are due. Returns how many changed."""
    key = (user_id, product_id)
    task = _running.get(key)
    if task is None or task.done():
        task = asyncio.create_task(_check_due(user_id, product_id))
        _running[key] = task

        def forget(finished: asyncio.Task[dict[str, int]]) -> None:
            if _running.get(key) is finished:
                del _running[key]

        task.add_done_callback(forget)
    # Shielded: one caller going away must not cancel it for the others.
    return await asyncio.shield(task)


async def _check_due(user_id: uuid.UUID, product_id: uuid.UUID | None) -> dict[str, int]:
    checked = changed = 0
    now = datetime.now(UTC)

    async with session_scope() as session:
        posts = await repo.open_for_checking(
            session,
            user_id,
            product_id,
            checked_before=now - RECHECK_AFTER,
            limit=MAX_POSTS,
        )
        if not posts:
            return {"checked": 0, "changed": 0}

        async with httpx.AsyncClient(
            headers={"User-Agent": settings.user_agent},
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            follow_redirects=True,
        ) as client:
            for post in posts:
                try:
                    verdict = await check_post(client, post)
                except RateLimited as exc:
                    log.warning("reply_check.rate_limited", url=str(exc))
                    break
                except (CheckFailed, KeyError, TypeError, ValueError) as exc:
                    # A payload shaped unlike the last one fails this post
                    # alone rather than rolling back the batch. Marked checked
                    # anyway, so it cannot hold up the rest by staying first
                    # in the queue.
                    log.info("reply_check.failed", post_id=str(post.id), reason=str(exc))
                    post.last_checked_at = now
                    checked += 1
                    continue

                checked += 1
                if apply(post, verdict, now):
                    changed += 1
                log.info(
                    "reply_check.checked",
                    post_id=str(post.id),
                    found_ours=verdict is not None,
                    replies=post.replies_after,
                    state=post.state.value,
                )

    return {"checked": checked, "changed": changed}
