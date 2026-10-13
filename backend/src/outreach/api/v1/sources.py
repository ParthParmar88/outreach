"""Search a source directly, to see what a connector actually returns."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from outreach import classify, dedupe, rank, score
from outreach.connectors import github, github_discussions
from outreach.schemas.conversation import Conversation

router = APIRouter(prefix="/sources", tags=["sources"])


class GitHubSearch(BaseModel):
    phrases: list[str] = Field(
        default_factory=list,
        description=(
            "SHORT fragments, 1-3 words, searched as exact quoted strings - "
            "anything sentence-shaped matches nothing at all. Use ' + ' to "
            "intersect two concepts instead: 'prompt caching + RAG' means "
            "both must appear anywhere in the post, which is far more "
            "precise than either alone and is where the good results are."
        ),
        examples=[
            ["prompt caching + RAG", "stale index", "re-embed + cost"]
        ],
    )
    repos: list[str] = Field(
        default_factory=list,
        description=(
            "Whole repositories to sweep, as owner/name. Every recent issue "
            "becomes a candidate with no keyword needed."
        ),
        examples=[["run-llama/llama_index"]],
    )
    exclude: list[str] = Field(default_factory=list, max_length=3)
    days: int = Field(default=30, ge=1, le=365)
    max_requests: int = Field(default=10, ge=1, le=60)
    min_repo_stars: int = Field(
        default=500,
        ge=0,
        description=(
            "Ignore issues in projects smaller than this. Commenting in a "
            "four-star repository reaches nobody. 0 turns it off."
        ),
    )

    product: str = Field(
        default="",
        description=(
            "What you are looking for, in plain language. Results are ranked "
            "by how close they are in meaning to this. Describe the PROBLEM "
            "your product solves, not its features - posts describe problems. "
            "Leave empty to sort by discussion volume instead."
        ),
        examples=[
            "Developers whose vector index goes stale when source documents "
            "change, who have to re-embed everything, and whose embedding and "
            "token bills keep growing because they resend unchanged context."
        ],
    )

    include_discussions: bool = Field(
        default=True,
        description=(
            "Also search GitHub Discussions, which the issue search cannot "
            "see at all - they are absent from /search/issues rather than "
            "ranked low. Needs a GITHUB_TOKEN, because the GraphQL API "
            "refuses anonymous requests. Discussions skew towards 'how do "
            "people solve this?' where issues skew towards 'here is my "
            "patch', so this is usually where the leads are."
        ),
    )
    drop_bots: bool = Field(
        default=True,
        description="Remove dependabot, renovate and friends. Almost always wanted.",
    )
    outsiders_only: bool = Field(
        default=False,
        description=(
            "Drop authors who work on the repository they posted in - "
            "owners, members and collaborators, who are writing tickets in "
            "their own project. Past contributors are KEPT: a merged pull "
            "request usually means they fixed a typo once, and the engaged "
            "power user filing a thoughtful feature request is exactly who "
            "we want."
        ),
    )

    classify: int = Field(
        default=140,
        ge=0,
        le=300,
        description=(
            "How many of the best-ranked results get read by the LLM. Costs "
            "roughly $0.0002 each, and repeats are cached. Keep this high: "
            "embeddings sort by topic and everything fetched is on-topic, so "
            "the classifier is the only stage that separates a lead from a "
            "post about the same subject. 0 skips classification and scoring."
        ),
    )
    show: int = Field(default=20, ge=1, le=100, description="Results to return.")


class GitHubSearchOut(BaseModel):
    found: int
    requests_made: int
    notes: list[str]
    conversations: list[Conversation]


@router.post("/github/search", response_model=GitHubSearchOut)
async def github_search(payload: GitHubSearch) -> GitHubSearchOut:
    """
    Search GitHub issues and, unless turned off, Discussions. PRs excluded.

    The two run concurrently against different rate limits, so adding
    discussions costs the request almost no extra time.
    """
    if not payload.phrases and not payload.repos:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Give at least one phrase or one repository.",
        )

    async def issues() -> github.SearchResult:
        return await github.search(
            payload.phrases,
            repos=payload.repos,
            days=payload.days,
            exclude=payload.exclude,
            max_requests=payload.max_requests,
            drop_bots=payload.drop_bots,
            outsiders_only=payload.outsiders_only,
            min_repo_stars=payload.min_repo_stars,
        )

    async def discussions() -> github.SearchResult:
        if not payload.include_discussions:
            return github.SearchResult()
        try:
            return await github_discussions.search(
                payload.phrases,
                repos=payload.repos,
                days=payload.days,
                exclude=payload.exclude,
                max_requests=payload.max_requests,
                drop_bots=payload.drop_bots,
                outsiders_only=payload.outsiders_only,
                min_repo_stars=payload.min_repo_stars,
            )
        except Exception as exc:
            # This endpoint exists to show what a connector returns, so a
            # half answer with the reason attached beats a 500.
            return github.SearchResult(
                notes=[f"discussions unavailable: {str(exc)[:200]}"]
            )

    result, extra = await asyncio.gather(issues(), discussions())
    result.conversations.extend(extra.conversations)
    result.requests_made += extra.requests_made
    result.notes.extend(extra.notes)

    result.conversations, duplicates = dedupe.collapse(result.conversations)
    if duplicates:
        result.notes.append(f"collapsed {duplicates} repeats of the same post")

    conversations = result.conversations

    if not payload.product:
        result.notes.append(
            "no `product` given, so these are sorted by discussion volume, not "
            "relevance, and nothing was classified or scored"
        )
        return GitHubSearchOut(
            found=len(conversations),
            requests_made=result.requests_made,
            notes=result.notes,
            conversations=_by_attention(conversations)[: payload.show],
        )

    # 3. RANK - embed everything, sort by meaning.
    try:
        conversations = await rank.score_relevance(payload.product, conversations)
        result.notes.append(f"ranked {len(conversations)} by relevance")
    except rank.RankError as exc:
        # Ranking is an improvement, not a precondition. Losing it should cost
        # the ordering, not the results we already paid to fetch.
        result.notes.append(f"relevance ranking unavailable: {exc}")
        return GitHubSearchOut(
            found=len(conversations),
            requests_made=result.requests_made,
            notes=result.notes,
            conversations=_by_attention(conversations)[: payload.show],
        )

    # 4. CUT - only the best few are worth an LLM call.
    conversations = conversations[: payload.classify]
    result.notes.append(f"kept top {len(conversations)} for classification")

    # 5. CLASSIFY - what is the author actually doing?
    try:
        conversations, notes = await classify.classify_all(payload.product, conversations)
        result.notes.extend(notes)
    except classify.ClassifyError as exc:
        result.notes.append(f"classification unavailable: {exc}")
        return GitHubSearchOut(
            found=len(conversations),
            requests_made=result.requests_made,
            notes=result.notes,
            conversations=conversations[: payload.show],
        )

    # 6. SCORE - relevance and intent as gates, then rank by the result.
    conversations = score.apply(conversations)

    counts: dict[str, int] = {}
    for conversation in conversations:
        counts[conversation.intent or "?"] = counts.get(conversation.intent or "?", 0) + 1
    result.notes.append(
        "intents: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    )

    # Keep every classified result for labelling. Building the evaluation set
    # as a side effect of ordinary use is the only version of this that
    # actually happens - a separate collection exercise never gets done.
    added = _capture(conversations, payload.product)
    if added:
        result.notes.append(f"{added} new candidates saved for labelling")

    # 7. SHOW
    return GitHubSearchOut(
        found=len(conversations),
        requests_made=result.requests_made,
        notes=result.notes,
        conversations=conversations[: payload.show],
    )


def _capture(conversations: list[Conversation], product: str) -> int:
    """Never let collecting evaluation data break a search."""
    try:
        from eval import store

        return store.capture(conversations, product)
    except Exception:
        return 0


def _by_attention(conversations: list[Conversation]) -> list[Conversation]:
    """
    Fallback ordering. Popularity, which is not relevance.

    Here only so raw output is readable when nothing better is available.
    """
    return sorted(conversations, key=lambda c: c.comments * 2 + c.score, reverse=True)


@router.get("/github/repos")
async def suggest_repos(q: str, min_stars: int = 500, limit: int = 12) -> list[dict]:
    """
    Repositories GitHub actually has, for a topic.

    Here because asking a model to recall repository names produces plausible
    wrong ones: renamed projects, wrong organisations, names that never
    existed. GitHub knows what exists today.
    """
    import httpx

    from outreach.config import settings as s

    async with httpx.AsyncClient(timeout=s.http_timeout_seconds) as client:
        return await github.find_repos(client, q, min_stars=min_stars, limit=limit)


@router.post("/github/queries", response_model=list[str])
async def github_queries(payload: GitHubSearch) -> list[str]:
    """
    Show the queries without running them. Free, instant, hits nothing.

    Both sets, labelled, because they are not the same string: the discussion
    search drops `is:issue` and `is:open`, and seeing that side by side is
    the quickest way to understand why one finds things the other cannot.
    """
    out = [
        f"issues     {q}"
        for _, q in github.build_queries(
            payload.phrases, payload.repos, payload.days, payload.exclude
        )
    ]
    if payload.include_discussions:
        out += [
            f"discussion {q}"
            for _, q in github_discussions.build_queries(
                payload.phrases, payload.repos, payload.days, payload.exclude
            )
        ]
    return out
