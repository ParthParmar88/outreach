"""
Run one platform's search for one product, using the plan's own terms.

This is the join between the two halves of the product. The planner decided
what to look for; this executes it and scores what comes back. The user never
types a keyword.

A run in flight lives in `RUNS`, because progress changes several times a
second and a row per tick would be a write every two seconds for nothing.
It is written to `search_run` twice: once when it starts, so an interrupted
search still leaves a trace, and once when it reaches a final state. Reads
check memory first and fall back to the table, so a run from last week opens
the same way as one from a minute ago.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from outreach import classify, dedupe, planner, rank, score, usage
from outreach.config import settings
from outreach.connectors import github, github_discussions, hackernews
from outreach.db.models.product import Product
from outreach.db.repositories import leads as lead_repo
from outreach.db.repositories import products as repo
from outreach.db.repositories import search_runs as run_repo
from outreach.db.session import session_scope
from outreach.planner import MarketingPlan
from outreach.profile import Profile
from outreach.schemas.conversation import Conversation
from outreach.services import plan_service

log = structlog.get_logger(__name__)

RUNS: dict[str, dict] = {}

#: So a broken eval pool complains once rather than on every run.
_EVAL_WARNED = False

#: What the fetch stage is called, per platform. The others never vary.
FETCH_LABEL = {
    "github": "Searching GitHub issues and discussions",
    "hackernews": "Searching Hacker News stories and comments",
}

STAGES = [
    ("fetch", "Searching"),
    ("filter", "Removing bots and project insiders"),
    ("rank", "Reading for meaning"),
    ("judge", "Judging who actually needs this"),
    ("score", "Scoring opportunities"),
]

#: Pages we want each query to get before the budget runs out.
#:
#: Two is the useful number: page one is whatever GitHub thinks is most
#: relevant, page two is the rest of the recent activity, and page three is
#: usually older and thinner. Better to spend the third page on another
#: repository than on the same one.
PAGES_PER_QUERY = 2

#: Floor and ceiling on the request budget.
#:
#: The ceiling matters: GitHub allows 30 searches a minute, so 60 requests is
#: already a two minute run, and nobody watches a progress bar for longer
#: than that.
MIN_REQUESTS = 15
MAX_REQUESTS = 60

#: The same ceiling for Hacker News, which is not paying the same bill.
#:
#: GitHub's 60 is two minutes of waiting on a rate limit. Algolia answers in
#: about a tenth of a second and charges nothing, so this is a politeness
#: ceiling on a free service rather than a quota - 48 requests is roughly
#: fifteen seconds, spaced.
HN_MAX_REQUESTS = 48

#: Below this many queries, the run says so rather than letting the user read
#: a starved search as a verdict on their market.
THIN_PLAN = 10

#: The discussion search gets its own budget rather than a slice of the one
#: above.
#:
#: They are not competing for the same thing. Issue search is REST and spends
#: from 30 requests a minute; discussion search is GraphQL and spends from
#: 5,000 points an hour, of which one page of ours costs about nine. Taking
#: discussion pages out of the issue budget would slow the issue search down
#: to pay a bill it was never charged.
#:
#: So the real constraint here is wall clock, not quota, and the two searches
#: run concurrently - which is why this number is sized to finish inside the
#: issue search rather than to exhaust anything.
MAX_DISCUSSION_REQUESTS = 30

#: Roughly what rewriting the plan spends from the issue-search rate limit.
#:
#: Rewriting a plan is not free in the currency the search needs. Repository
#: discovery counts hits across several phrase searches, and the fallback
#: asks `/search/repositories` a few more times - all of it on the same 30
#: requests a minute the search itself lives on.
#:
#: Left unaccounted, the run spent that quota, then started a 60 request
#: search into a rate limit it had already half-consumed, and paid for it in
#: minutes of backoff. Subtracting it up front costs a couple of pages and
#: keeps the run inside its limit.
REPLAN_REQUEST_COST = 12

#: Per-source override for how much of the ranked list the triage reads.
#:
#: Falls back to `settings.triage_pool`, which is what GitHub uses. Hacker
#: News is listed separately because it was measured first, not because it
#: felt different:
#:
#:     same fetch, 297 candidates
#:       pool 25   ->   3 clear matches, best result 20 (PROBLEM)
#:       pool all  ->  16 clear matches, best result 36 (DIY_WORKAROUND)
#:
#: Five times the clear matches, and the best lead of the run - somebody
#: cutting their Claude Code token spend by 80% - was invisible at 25.
#:
#: The reason is structural rather than a tuning accident. GitHub has
#: repository sweeps, so even a mediocre top 25 contains posts from rooms
#: chosen on purpose. Hacker News has no rooms: every candidate comes from a
#: broad phrase match, and the embedding has only a comment's first line to
#: rank on, so position 200 is no worse a bet than position 20.
#:
#: It is affordable because titles are cheap - 297 of them is about eight
#: batched calls, well under a cent, and cached by content afterwards.
TRIAGE_POOL: dict[str, int] = {
    # 0 means every candidate.
    #
    # ── Why Hacker News has a number rather than 0 ───────────────────────
    #
    # It was 0, and 0 was right when the fetch returned about 300 candidates:
    # embedding rank is close to useless here, so reading every title was the
    # only way to find the good ones. Measured, 25 titles produced 3 clear
    # matches and a best score of 20; every title produced 16 and 36.
    #
    # Widening the search changed the arithmetic. Better phrases return three
    # times the candidates, and 0 would have turned that straight into three
    # times the triage calls. This is what keeps the token spend flat while
    # the search gets bigger: fetch as much as Algolia will give us, embed it
    # all - embedding a post costs a fraction of reading its title - and let
    # the ranking choose which 300 titles are worth the model's attention.
    #
    # 300 is the volume the triage was already reading, so this is the same
    # bill for a better pool, not a bigger one.
    "hackernews": 300,
}

#: How many of the triage's picks get read in full and scored.
#:
#: This number used to carry the whole selection problem and had to be large
#: because of it: the stage before it sorted by embedding similarity, which
#: is flat across the results that matter, so the only way to reach a good
#: lead was to read deep enough to trip over it.
#:
#: The triage changed what this number means. Titles are now read for all
#: candidates and ranked by whether something is *happening*, so what arrives
#: here is already chosen rather than merely near the top of a topic. A
#: smaller, sharper set is the right shape for the expensive stage.
#:
#: Ten by decision, to hold the per-run token spend down.
#:
#: This is a much safer number than it used to be, and the reason is worth
#: keeping: it is only affordable because `triage_pool` is 0. Titles are read
#: for every candidate, so the ten that arrive here are ten the triage picked
#: out of thousands. Back when the pool was capped the same ten were whatever
#: happened to rank highest by embedding similarity, which is flat across the
#: results that matter - the two are not comparable, however identical the
#: number looks.
#:
#: Watch the run notes rather than this line. The triage reports how many
#: scored a clear match and were cut by this limit; while that number is
#: zero, ten is genuinely enough, and when it is not, it says so.
#: How far back each source is searched.
#:
#: Not one number, because "still worth replying to" means something
#: different on each. A GitHub issue opened two months ago is usually still
#: open, still subscribed to, and a reply is read. A Hacker News thread is
#: finished within a few days of leaving the front page.
#:
#: Measured on one product's terms over ninety days: 48% of the Hacker News
#: candidates were 31-90 days old - fetched, embedded, ranked and competing
#: for triage slots against posts somebody could actually answer. Cutting to
#: thirty days lost 26% of the volume and over half the Show HN launches,
#: which accumulate in exactly that long tail.
SEARCH_DAYS = {
    "github": 90,
    "hackernews": 30,
}
DEFAULT_SEARCH_DAYS = 90

CLASSIFY_TOP = 10

#: How a connector marks a result that one of the plan's phrases found.
#:
#: GitHub writes "phrase: ". Hacker News searches each phrase twice and says
#: which half found the post. Only the first was recognised, so every Hacker
#: News run reported that all of its problems "matched nothing at all" - under
#: a funnel line showing hundreds of results.
PHRASE_LABELS = ("phrase: ", "story: ", "comment: ")


def _budget(terms: list[str], repos: list[str]) -> int:
    """
    Scale the request budget to how much there is to search.

    A fixed budget was fine with four queries and starves at fourteen: every
    query gets one page, and the run sees the first hundred results of each
    rather than the best few hundred overall. Better repositories made the
    budget the bottleneck rather than the search.
    """
    queries = len(terms) + len(repos)
    return max(MIN_REQUESTS, min(MAX_REQUESTS, queries * PAGES_PER_QUERY))


def _hn_budget(terms: list[str]) -> int:
    """
    Requests for one Hacker News run.

    Its own function because the GitHub budget is rationing something. There,
    a request is a slice of 30 a minute shared by everyone in the
    organisation, and spending it is the whole reason that ceiling exists.

    Algolia is free, unauthenticated, and answers in about a tenth of a
    second. Nothing is being rationed here, so the old shared budget was not
    protecting a limit - it was throwing away results. A real run said so
    plainly: `stopped at the 15 request limit with 1 query still having more
    to give`.

    Each term becomes two queries, stories and comments, so the arithmetic is
    doubled against GitHub's. `HN_MAX_REQUESTS` is a politeness ceiling on
    somebody else's free service, and at a quarter of a second apart the whole
    budget is about fifteen seconds of wall clock.

    This does not move the token spend. What is fetched gets embedded, which
    is cheap; how much of it a model *reads* is `TRIAGE_POOL`, and that is
    pinned.
    """
    return max(MIN_REQUESTS, min(HN_MAX_REQUESTS, len(terms) * 2 * PAGES_PER_QUERY))


class OpportunityError(Exception):
    """Something the user needs to know about, phrased for a person."""


def start(
    product_id: uuid.UUID,
    platform: str,
    terms: list[str] | None = None,
    repos: list[str] | None = None,
) -> str:
    """Register a run. `terms` and `repos` override what the plan chose."""
    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {
        "id": run_id,
        "product_id": str(product_id),
        "platform": platform,
        "terms": terms,
        "repos": repos,
        "state": "queued",
        "stages": [
            {
                "id": s,
                # The fetch stage names the source it is reading. Watching a
                # progress bar that says "Searching" tells you nothing about
                # whether the right thing is happening.
                "label": FETCH_LABEL.get(platform, label) if s == "fetch" else label,
                "state": "waiting",
                "detail": None,
            }
            for s, label in STAGES
        ],
        "percent": 0,
        "notes": [],
        "results": [],
        "error": None,
        "started_at": datetime.now(UTC).isoformat(),
    }
    return run_id


async def load(session: AsyncSession, run_id: str) -> dict:
    """
    A run, from memory if it is live and from the table if it is not.

    Memory first because a run in flight is updated many times a second and
    the table only sees it at the start and at the end. The stored copy of a
    live run is deliberately behind.
    """
    run = RUNS.get(run_id)
    if run is not None:
        return run

    row = await run_repo.get(session, run_id)
    if row is None:
        raise OpportunityError("No search with that id.")
    return run_repo.to_dict(row)


async def latest(
    session: AsyncSession, product_id: uuid.UUID, platform: str | None = None
) -> dict | None:
    """
    The most recent search for a product, or None if there has never been one.

    `platform` narrows it to one source, so a screen can show GitHub and
    Hacker News side by side rather than only whichever ran most recently.
    """
    row = await run_repo.latest_for_product(session, product_id, platform)
    if row is None:
        return None

    # A live run is fresher than its row, which was written when it started.
    live = RUNS.get(row.id)
    return live if live is not None else run_repo.to_dict(row)


async def _persist(run: dict) -> None:
    """
    Write the run to the table, never failing the run in order to do it.

    A search that found ten good leads and then could not save them should
    still show the ten leads. Losing the durable copy costs the history, not
    the result the user is currently looking at.
    """
    try:
        async with session_scope() as session:
            await run_repo.save(session, run)
    except Exception:
        log.exception("opportunity.persist_failed", run_id=run.get("id"))


async def _record_leads(run: dict) -> None:
    """
    Fold this run's results into the product's lead list.

    Runs before `_persist` rather than after, so the "N new" note it adds is
    part of the copy that gets stored: a note written afterwards would show
    on screen once and be missing from the run for ever after.

    Never fails the run. A search that found ten good leads and then could
    not file them should still show the ten leads.
    """
    if run.get("state") != "succeeded":
        return

    results = run.get("results") or []
    if not results:
        return

    try:
        async with session_scope() as session:
            fresh = await lead_repo.record(
                session, uuid.UUID(run["product_id"]), results
            )
    except Exception:
        log.exception("opportunity.leads_failed", run_id=run.get("id"))
        return

    # Said either way. "0 new" is a real answer to "has anything happened
    # since last week", and leaving it out makes the run look like it
    # forgot to check.
    run["notes"].append(
        f"{fresh} of these {len(results)} have never been seen before"
        if fresh
        else f"none of these {len(results)} are new since your last search"
    )


def _capture_for_eval(conversations: list[Conversation], product: str) -> None:
    """
    Add this run's judged results to the labelling pool.

    The pool is the only ground truth this system has, and it was being fed
    by exactly one caller: the manual `/sources/github/search` endpoint,
    which nothing in the UI ever calls. So every real search went
    uncaptured and the pool sat at 25 candidates collected by hand in
    August, while every prompt change since was argued rather than
    measured.

    Wrapped, because collecting evidence must never cost a result.

    The path is resolved rather than imported by name. `eval` lives beside
    `src` in the backend root, so a bare `from eval import store` only works
    when the process happens to have been started from that directory - and
    when it does not, this fails silently and the pool stops growing with
    nothing to say why. Which is the failure being fixed here, so it is not
    one to reproduce.
    """
    try:
        root = str(Path(__file__).resolve().parents[3])
        if root not in sys.path:
            sys.path.insert(0, root)

        from eval import store

        store.capture(conversations, product)
    except Exception:
        # Once per process, at a level somebody will actually see. A pool
        # that quietly never grows is worse than a noisy failure.
        global _EVAL_WARNED
        if not _EVAL_WARNED:
            _EVAL_WARNED = True
            log.warning("opportunity.eval_capture_failed", exc_info=True)


async def execute(run_id: str) -> None:
    """The background job. Every exit path writes a final state."""
    run = RUNS[run_id]
    run["state"] = "running"

    product_id = uuid.UUID(run["product_id"])

    # Counts every token this run spends, wherever the call is made.
    meter = usage.start()

    # Written once up front so an interrupted run leaves a trace. Without
    # this a server restart mid-search loses the fact that it happened at
    # all, and the last-search card silently shows the run before it.
    await _persist(run)

    try:
        # Rewrite the plan first if it has gone out of date.
        #
        # `is_stale` has always known the answer; nothing on this path ever
        # asked it. A plan was only rewritten when somebody opened the plan
        # page or re-crawled the site, so a search would happily run terms
        # written against a rubric two versions old - and did. Every
        # improvement to the planner reached new products only, while
        # existing ones searched the same words forever and looked, from the
        # results, as though nothing had changed at all.
        async with session_scope() as session:
            product = await repo.get(session, product_id)
            if product is None:
                raise OpportunityError("That product no longer exists.")
            stale = plan_service.is_stale(product)

        replanned = False
        if stale:
            run["notes"].append("plan was out of date - rewriting it before searching")
            try:
                await plan_service.ensure_plan(product_id)
                replanned = True
            except Exception as exc:
                # An old plan still searches. Failing to improve it must not
                # cost the run.
                log.warning("opportunity.replan_failed", error=str(exc))
                run["notes"].append(f"could not rewrite the plan: {str(exc)[:150]}")

        async with session_scope() as session:
            product = await repo.get(session, product_id)
            if product is None:
                raise OpportunityError("That product no longer exists.")
            terms, places, groups = _terms_for(product, run["platform"])
            # A caller-supplied list wins outright, including an empty
            # one: "search no phrases, only these repositories" is a
            # deliberate and useful thing to ask for.
            if run["terms"] is not None:
                terms = run["terms"]
                # A hand-edited list is not grouped, so there is no ontology
                # left to report coverage against. Reporting the plan's
                # branches over terms the user replaced would be worse than
                # reporting nothing: every branch would read as empty.
                groups = {}
            if run["repos"] is not None:
                places = run["repos"]
            target = _target_text(product)
            own = planner.own_names(product.name, product.canonical_url)

        if not terms and not places:
            raise OpportunityError(
                "The plan has no search terms for this platform. Rewrite the plan."
            )

        budget = _budget(terms, places)
        if replanned:
            budget = max(MIN_REQUESTS, budget - REPLAN_REQUEST_COST)

        run["notes"].append(
            f"searching {len(terms)} phrases + {len(places)} repositories "
            f"with {budget} requests"
            + (f" ({REPLAN_REQUEST_COST} kept back for the replan)" if replanned else "")
        )

        # Say so when the plan is thin, rather than letting a starved run look
        # like an empty market. A run that fetches nothing because it barely
        # searched is the single most confusing outcome this thing produces:
        # the numbers all look valid and the conclusion drawn is "there is
        # nobody out there", which is the opposite of what happened.
        if len(terms) + len(places) < THIN_PLAN:
            run["notes"].append(
                f"this plan is thin - {len(terms)} phrases and {len(places)} "
                f"repositories is little to search. Few results here mean a "
                f"narrow plan, not an empty market. Rewrite the plan, or add "
                f"repositories to sweep."
            )

        _mark(run, "fetch", "running")

        raw, detail = await _fetch(run["platform"], terms, places, budget, run)

        raw, from_own = _drop_own(raw, own, places)
        if from_own:
            run["notes"].append(
                f"dropped {from_own} from this product's own repository - "
                f"the people there already use it"
            )

        # The same *content* turns up twice often enough to be worth a pass:
        # somebody files an issue and opens a discussion for it, or posts the
        # same question in two Hacker News threads. Ids never collide, so
        # only a content check finds those.
        conversations, duplicates = dedupe.collapse(raw)
        if duplicates:
            run["notes"].append(f"collapsed {duplicates} repeats of the same post")

        _mark(run, "fetch", "done", detail)
        _mark(run, "filter", "done", "bots and insiders removed")

        if not conversations:
            _finish(run)
            return

        # Free, and before anything is embedded or read. A repository sweep
        # takes every recent issue in a repository, and most of what any
        # repository does is not about us.
        fetched = len(conversations)
        conversations, gate_note = classify.gate(conversations, terms)
        run["notes"].append(gate_note)

        if not conversations:
            _finish(run)
            return

        _mark(run, "rank", "running")
        conversations = await rank.score_relevance(target, conversations)
        _mark(run, "rank", "done", f"{len(conversations)} read")

        ranked = len(conversations)
        # Held for the coverage report: this is every candidate each problem
        # actually produced, before the judge limit picks ten of them.
        candidates = list(conversations)

        # Titles first, cheaply, and only then the expensive judge.
        #
        # `triage_pool` caps how much of the ranked list the triage is allowed
        # to read. See the setting for what a small pool costs; the short
        # version is that embedding rank and result quality are close to
        # unrelated here, so a tight pool decides the run before anything has
        # read a title.
        cap = TRIAGE_POOL.get(run["platform"], settings.triage_pool)
        pool = conversations
        if cap:
            pool = conversations[:cap]
            if len(conversations) > len(pool):
                run["notes"].append(
                    f"triage pool: reading the top {len(pool)} of "
                    f"{len(conversations)} by embedding score. The other "
                    f"{len(conversations) - len(pool)} are not read at all - "
                    f"raise TRIAGE_POOL to widen this."
                )

        conversations, triage_notes = await classify.triage(
            target, pool, CLASSIFY_TOP
        )
        run["notes"].extend(triage_notes)

        # The whole funnel on one line.
        #
        # Every number in a run is individually plausible while the shape of
        # the run is badly wrong, and without this the only visible output is
        # the final count - which reads as a verdict on the market rather than
        # a description of how little was searched. One glance here says
        # whether a small result set came from a small search or a small
        # market.
        run["notes"].append(
            f"funnel: {detail} -> {fetched} after duplicates "
            f"-> {ranked} through the gate -> {len(conversations)} judged"
        )

        _mark(run, "judge", "running")
        conversations, notes = await classify.classify_all(target, conversations)
        run["notes"].extend(notes)
        _mark(run, "judge", "done", f"{len(conversations)} judged")

        await _attach_reach(conversations)

        conversations = score.apply(conversations)
        run["results"] = [_to_dict(c, i + 1) for i, c in enumerate(conversations)]
        _mark(run, "score", "done", f"{len(conversations)} scored")

        _capture_for_eval(conversations, target)

        coverage = _coverage(candidates, conversations, groups)
        if coverage:
            run["notes"].append(coverage)

        _finish(run)

    except Exception as exc:
        log.exception("opportunity.failed", run_id=run_id)
        run["state"] = "failed"
        run["error"] = str(exc)[:400]
        for stage in run["stages"]:
            if stage["state"] == "running":
                stage["state"] = "skipped"

    finally:
        # In a finally, not after `_finish`, because the happy path has
        # several early returns in it - an empty fetch, an empty gate - and
        # those are exactly the runs worth remembering having done.
        #
        # The cost line goes first, so it is part of the copy that is stored.
        # It is said on every exit, a failed run included: a search that
        # spent tokens and then broke still spent them.
        run["notes"].append(meter.summary())
        log.info(
            "opportunity.usage",
            run_id=run_id,
            tokens=meter.tokens,
            cost_usd=round(meter.cost, 6),
        )
        await _record_leads(run)
        await _persist(run)


# ---------------------------------------------------------------- internals


async def _fetch(
    platform: str,
    terms: list[str],
    places: list[str],
    budget: int,
    run: dict,
) -> tuple[list[Conversation], str]:
    """
    Everything one platform returns, plus a line describing what came back.

    The one place that knows a platform is more than a connector. GitHub is
    two searches that have to run together; Hacker News is one search over
    two different kinds of thing. Downstream sees a flat list either way,
    which is what lets ranking, triage and scoring stay source-agnostic.
    """
    if platform == "hackernews":
        found = await hackernews.search(
            terms,
            days=SEARCH_DAYS.get("hackernews", DEFAULT_SEARCH_DAYS),
            max_requests=_hn_budget(terms),
            min_story_points=settings.min_hn_points,
        )
        run["notes"].extend(found.notes)

        stories = sum(1 for c in found.conversations if c.kind == "story")
        comments = len(found.conversations) - stories
        return found.conversations, f"{stories} stories + {comments} comments"

    # GitHub, concurrently, because the two queue on different rate limits -
    # REST search on 30 a minute, GraphQL on 5,000 points an hour. Run in
    # sequence the discussion search would add its whole duration to the run
    # for no reason; run together it is effectively free.
    issues, discussions = await asyncio.gather(
        github.search(
            terms,
            repos=places,
            days=SEARCH_DAYS.get("github", DEFAULT_SEARCH_DAYS),
            max_requests=budget,
            outsiders_only=settings.outsiders_only,
            min_repo_stars=settings.min_repo_stars,
        ),
        _discussions(terms, places, run),
    )

    run["notes"].extend(issues.notes)
    run["notes"].extend(discussions.notes)

    return (
        issues.conversations + discussions.conversations,
        f"{len(issues.conversations)} issues + "
        f"{len(discussions.conversations)} discussions",
    )


def _drop_own(
    conversations: list[Conversation], own: set[str], places: list[str]
) -> tuple[list[Conversation], int]:
    """
    Remove posts from the product's own repository. Returns (kept, dropped).

    The plan no longer sweeps that repository, but a phrase search covers
    the whole of GitHub and brings its posts back - and they score at the top,
    because nothing matches a product better than its own tracker.

    A repository the user put in the list by hand is left alone. Asking for
    it by name is a decision, not an accident.
    """
    asked_for = {place.lower() for place in places}
    kept = [
        c
        for c in conversations
        if c.source != "github"
        or (c.container or "").lower() in asked_for
        or not planner.is_own_repo(c.container, own)
    ]
    return kept, len(conversations) - len(kept)


async def _discussions(
    terms: list[str], places: list[str], run: dict
) -> github.SearchResult:
    """
    Search Discussions, degrading to nothing rather than failing the run.

    Deliberately swallows everything. The issue search is the older half of
    this pipeline and works on its own; losing the newer half to a missing
    token or a GraphQL hiccup should cost the discussions, not the run. The
    reason always lands in the notes, so a silent zero is still explained.
    """
    try:
        # Drop the repositories with Discussions turned off before spending
        # a search request discovering it. They answer with an empty page and
        # no error, so the budget goes and nothing comes back.
        if places:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as c:
                usable = await github.repos_with_discussions(c, places)
            if len(usable) < len(places):
                run["notes"].append(
                    f"discussions: skipped {len(places) - len(usable)} of "
                    f"{len(places)} repositories that have Discussions turned off"
                )
            places = usable

        return await github_discussions.search(
            terms,
            repos=places,
            # Discussions are half of GitHub, so they share GitHub's window.
            days=SEARCH_DAYS.get("github", DEFAULT_SEARCH_DAYS),
            max_requests=MAX_DISCUSSION_REQUESTS,
            outsiders_only=settings.outsiders_only,
            min_repo_stars=settings.min_repo_stars,
        )
    except github_discussions.DiscussionsUnavailable as exc:
        log.warning("opportunity.discussions_unavailable", error=str(exc))
        return github.SearchResult(notes=[f"Discussions not searched: {exc}"])
    except Exception as exc:
        log.exception("opportunity.discussions_failed")
        return github.SearchResult(
            notes=[f"Discussion search failed, issues only: {str(exc)[:200]}"]
        )


def _terms_for(
    product: Product, platform: str
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    """
    The plan's search terms for this platform, and the problems they belong to.

    Falls back to the profile's pain words when the plan has none. Those are
    the phrases somebody with the problem types, which is exactly what a
    keyword search needs, so an empty plan is recoverable rather than fatal.

    The third value is empty for a plan written before the ontology existed.
    Everything downstream treats that as "no coverage report", not as an
    error - an old plan still searches perfectly well.
    """
    if product.plan:
        try:
            plan = MarketingPlan(**product.plan)
            for entry in plan.platforms:
                if entry.key == platform:
                    return (
                        list(entry.search_terms),
                        list(entry.target_places),
                        dict(entry.term_groups),
                    )
        except Exception:
            log.warning("opportunity.plan_unreadable", product_id=str(product.id))

    if product.profile:
        try:
            pain = Profile(**product.profile).pain_words
            return pain[:8], [], {}
        except Exception:
            pass

    return [], [], {}


async def _attach_reach(conversations: list[Conversation]) -> None:
    """
    Fill in how big each result's repository is, for the reach score.

    Runs on the judged handful rather than on everything fetched, and the
    counts are cached between runs, so this is usually free and never more
    than a few requests. It also sits on the 5,000-per-hour core limit rather
    than the 30-per-minute search limit, so it cannot slow a search down.

    Failure is silently survivable: an unknown count scores as average, which
    is the honest answer when we could not look it up.
    """
    names = sorted({c.container for c in conversations if c.container})
    if not names:
        return

    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
            stars = await github.repo_stars(client, names)
    except Exception as exc:
        log.warning("opportunity.stars_failed", error=str(exc))
        return

    for conversation in conversations:
        count = stars.get(conversation.container or "", -1)
        if count >= 0:
            conversation.repo_stars = count


def _tally(
    conversations: list[Conversation], groups: dict[str, list[str]]
) -> tuple[dict[str, int], int]:
    """How many of these came from each problem, and how many from sweeps."""
    branch_of = planner.branch_of(groups)
    counts = {name: 0 for name in groups}
    swept = 0

    for conversation in conversations:
        label = conversation.found_by or ""
        phrase = next(
            (label.removeprefix(p) for p in PHRASE_LABELS if label.startswith(p)), None
        )
        if phrase is not None:
            name = branch_of.get(phrase.lower())
            if name in counts:
                counts[name] += 1
        elif label.startswith("repo: "):
            # Repository sweeps carry no phrase, so they belong to no branch.
            # Counted separately rather than dropped: they are usually the
            # best source in the run, and a coverage line that silently
            # omitted them would understate it badly.
            swept += 1

    return counts, swept


def _coverage(
    fetched: list[Conversation],
    results: list[Conversation],
    groups: dict[str, list[str]],
) -> str | None:
    """
    What each problem in the plan found, and what survived to the results.
    None when there is no ontology to report against.

    ── Why this is worth a line of its own ──────────────────────────────────

    A run that searched five problems and returned results for one looks
    exactly like a run where only one problem exists in the market. Both show
    a list of good posts about caching. The difference is the whole story, and
    without this nobody ever sees it - the results are individually correct,
    so there is nothing to notice.

    ── Why both numbers, and not just the results ───────────────────────────

    Because a zero means two completely different things and the fix is
    opposite in each. `95 -> 0` is a problem that found plenty and lost the
    race for a judge slot: raise the limit, or narrow the others. `0 -> 0` is
    a problem nothing matched at all: the terms for it are wrong.

    Reporting only the results collapses those two into one number and sends
    you to rewrite terms that were working.
    """
    if not groups:
        return None

    found, found_swept = _tally(fetched, groups)
    kept, kept_swept = _tally(results, groups)

    parts = [f"{name} {found[name]}->{kept[name]}" for name in groups]
    if found_swept or kept_swept:
        parts.append(f"repo sweeps {found_swept}->{kept_swept}")

    line = "coverage (found -> judged): " + " · ".join(parts)

    unmatched = [name for name in groups if found[name] == 0]
    if unmatched:
        line += (
            f" — {', '.join(unmatched)} matched nothing at all, so those terms "
            f"are wrong rather than that problem being rare."
        )
    return line


def _target_text(product: Product) -> str:
    """What every result is matched and judged against."""
    parts: list[str] = []
    if product.profile:
        # A profile written by an older version of the extractor may no
        # longer parse. The description below is enough on its own.
        with contextlib.suppress(Exception):
            parts.append(Profile(**product.profile).as_search_text())
    if product.description:
        parts.append(product.description)
    if product.goal:
        parts.append(f"The goal of this search: {product.goal}")
    return "\n\n".join(p for p in parts if p) or product.name


def _to_dict(c: Conversation, rank_position: int) -> dict:
    detail = score.breakdown(c)
    engagement = f"{c.comments} comments"
    if c.score:
        engagement += f" · {c.score} reactions"

    return {
        "id": c.source_id,
        "rank": rank_position,
        "score": c.opportunity or 0,
        "band": score.band(c.opportunity or 0),
        "url": c.url,
        "kind": c.kind,
        "category": c.category,
        "is_answered": c.is_answered,
        "title": c.title or "(no title)",
        "author": c.author or "unknown",
        "container": c.container,
        "created_at": c.created_at.isoformat(),
        "engagement": engagement,
        "problem": c.pain_point or "",
        "evidence_quote": c.evidence_quote or "",
        "intent": c.intent,
        "domain": c.post_domain,
        "asking_for_help": c.asking_for_help,
        "product_fit": c.product_fit or 0.0,
        "reason": c.reason or "",
        "explain": detail.get("explain", ""),
    }


def _mark(run: dict, stage_id: str, state: str, detail: str | None = None) -> None:
    for stage in run["stages"]:
        if stage["id"] == stage_id:
            stage["state"] = state
            if detail:
                stage["detail"] = detail
    done = sum(1 for s in run["stages"] if s["state"] == "done")
    run["percent"] = round(100 * done / len(run["stages"]))


def _finish(run: dict) -> None:
    for stage in run["stages"]:
        if stage["state"] in ("waiting", "running"):
            stage["state"] = "done"
    run["state"] = "succeeded"
    run["percent"] = 100
