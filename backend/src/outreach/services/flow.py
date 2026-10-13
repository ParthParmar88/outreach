"""
Brief -> Plan -> Run, backed by the pipeline that already works.

Held in memory, not the database. That is a deliberate stage, not an
oversight: the shapes the screens need are still moving, and a migration per
change would slow that down for no benefit. Everything here is written so
that swapping the dicts for repositories touches this file only.

The consequence, stated plainly: restarting the server loses runs. Fine
while two people are developing, not fine the day someone else uses it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import structlog

from outreach import classify, expand, rank, score
from outreach.config import settings
from outreach.connectors import github
from outreach.schemas.conversation import Conversation
from outreach.schemas.web import (
    BriefIn,
    BriefOut,
    ConversationOut,
    ExamplePost,
    PlanOut,
    PlanPredicates,
    PlanTerm,
    ResultOut,
    RunOut,
    ScoreComponent,
    ScoreDetail,
    StageProgress,
)

log = structlog.get_logger(__name__)

BRIEFS: dict[str, dict] = {}
PLANS: dict[str, dict] = {}
RUNS: dict[str, dict] = {}
RESULTS: dict[str, list[Conversation]] = {}
FEEDBACK: dict[str, str] = {}

#: What the user sees happening. Fewer than the pipeline's internal stages,
#: because "fuse" and "diversify" mean nothing to a marketer watching a
#: progress list.
STAGES = [
    ("fetch", "Searching sources"),
    ("dedupe", "Removing duplicates and bots"),
    ("embed", "Reading for meaning"),
    ("rerank", "Ranking by relevance"),
    ("analyze", "Judging intent"),
    ("score", "Scoring opportunities"),
]

CALL_BUDGET = 20


class FlowError(Exception):
    """Something the user needs to know about, phrased for a person."""


# ---------------------------------------------------------------- 1. Brief


def create_brief(payload: BriefIn) -> BriefOut:
    brief_id = uuid.uuid4().hex[:12]
    BRIEFS[brief_id] = {
        "id": brief_id,
        **payload.model_dump(),
        "created_at": datetime.now(UTC),
        "latest_plan_id": None,
        "latest_run_id": None,
        "latest_run_state": None,
        "result_count": None,
    }
    return BriefOut(**BRIEFS[brief_id])


def list_briefs() -> list[BriefOut]:
    return [
        BriefOut(**b)
        for b in sorted(BRIEFS.values(), key=lambda b: b["created_at"], reverse=True)
    ]


def get_brief(brief_id: str) -> dict:
    brief = BRIEFS.get(brief_id)
    if brief is None:
        raise FlowError("No brief with that id. It may have been lost on a restart.")
    return brief


# ---------------------------------------------------------------- 2. Plan


async def compile_plan(brief_id: str) -> PlanOut:
    """
    Turn a brief into an executable plan, expanding the keywords on the way.

    The one LLM call happens here rather than during the run, and that is the
    whole design: expansion finishes *before* anything is fetched, so the user
    can read every added term and delete the ones they disagree with. Once
    they press Start, the plan is frozen and the run is reproducible.
    """
    brief = get_brief(brief_id)

    terms = [PlanTerm(term=k.strip(), origin="user") for k in brief["keywords"] if k.strip()]

    # Very short keywords match everything and cost a page of results each.
    # Flagged rather than dropped, because it is the user's search.
    for term in terms:
        if len(term.term) < 3:
            term.reason = "very short - will match a lot of unrelated posts"

    # Added terms are marked, reasoned, and deletable. Never silent.
    for suggestion in await expand.expand(brief["description"], brief["keywords"]):
        terms.append(
            PlanTerm(
                term=suggestion["term"],
                origin="expansion",
                reason=suggestion["reason"],
            )
        )

    date_from = (datetime.now(UTC) - timedelta(days=brief["days_back"])).date()
    predicates = PlanPredicates(
        sources=brief["sources"],
        date_from=date_from.isoformat(),
        date_to=datetime.now(UTC).date().isoformat(),
    )

    plan_id = uuid.uuid4().hex[:12]
    material = json.dumps(
        {"terms": [t.term for t in terms], "predicates": predicates.model_dump()},
        sort_keys=True,
    )

    plan = {
        "id": plan_id,
        "brief_id": brief_id,
        "plan_hash": hashlib.sha256(material.encode()).hexdigest()[:16],
        "version": 1,
        "terms": terms,
        "predicates": predicates,
        "stages": [s for s, _ in STAGES],
        "estimated_documents": min(len(terms) * 100, 1000) or 100,
        # Embeddings for everything fetched, plus 25 classifications.
        "estimated_cost_usd": round(0.001 + 25 * 0.0002, 4),
        "example_posts": _example_posts(brief),
    }
    PLANS[plan_id] = plan
    BRIEFS[brief_id]["latest_plan_id"] = plan_id
    return PlanOut(**plan)


def _example_posts(brief: dict) -> list[ExamplePost]:
    """
    What we are looking for, written out as posts.

    Nobody can review a search plan. Anyone can read an example post and say
    "yes, that is it" or "no, that is not what I meant" - which is the whole
    reason this screen exists.
    """
    return [
        ExamplePost(
            source="github",
            title="Do I have to re-embed everything when one document changes?",
            body=(
                f"{brief['description'][:180]}... Someone describing this problem "
                "in their own words, without using our vocabulary."
            ),
        )
    ]


def get_plan(plan_id: str) -> PlanOut:
    plan = PLANS.get(plan_id)
    if plan is None:
        raise FlowError("No plan with that id. It may have been lost on a restart.")
    return PlanOut(**plan)


def amend_plan(plan_id: str, terms: list[str]) -> PlanOut:
    """
    The user edited the terms, so rehash and bump the version.

    A new hash is the point: an amended plan is a different plan, and must
    not reuse the previous one's cached results.
    """
    plan = PLANS.get(plan_id)
    if plan is None:
        raise FlowError("No plan with that id.")

    # Keep origin and reason for terms that survived the edit. Relabelling a
    # kept suggestion as "user" would erase the record of where it came from,
    # and the review screen would stop being able to explain itself.
    known = {t.term.lower(): t for t in plan["terms"]}
    plan["terms"] = [
        known.get(t.strip().lower()) or PlanTerm(term=t.strip(), origin="user")
        for t in terms
        if t.strip()
    ]
    plan["version"] += 1
    material = json.dumps(sorted(t.term for t in plan["terms"]))
    plan["plan_hash"] = hashlib.sha256(material.encode()).hexdigest()[:16]
    return PlanOut(**plan)


# ---------------------------------------------------------------- 3. Run


def start_run(plan_id: str) -> RunOut:
    plan = PLANS.get(plan_id)
    if plan is None:
        raise FlowError("No plan with that id.")

    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {
        "id": run_id,
        "plan_id": plan_id,
        "state": "queued",
        "stages": [
            StageProgress(id=s, label=label, state="waiting") for s, label in STAGES
        ],
        "percent": 0,
        "cost_usd": 0.0,
        "calls_used": 0,
        "call_budget": CALL_BUDGET,
        "error": None,
    }
    BRIEFS[plan["brief_id"]]["latest_run_id"] = run_id
    BRIEFS[plan["brief_id"]]["latest_run_state"] = "queued"
    return RunOut(**RUNS[run_id])


def get_run(run_id: str) -> RunOut:
    run = RUNS.get(run_id)
    if run is None:
        raise FlowError("No run with that id. It may have been lost on a restart.")
    return RunOut(**run)


async def execute(run_id: str) -> None:
    """
    The background job. Every exit path writes a final state, so a run can
    never be left showing "running" with nothing behind it.
    """
    run = RUNS[run_id]
    plan = PLANS[run["plan_id"]]
    brief = BRIEFS[plan["brief_id"]]

    run["state"] = "running"
    _mark(run, "fetch", "running")

    try:
        result = await github.search(
            [t.term for t in plan["terms"]],
            days=brief["days_back"],
            max_requests=CALL_BUDGET,
            outsiders_only=settings.outsiders_only,
        )
        run["calls_used"] = result.requests_made
        _mark(run, "fetch", "done", f"{len(result.conversations)} found")
        _mark(run, "dedupe", "done", "bots and insiders removed")

        conversations = result.conversations
        if not conversations:
            _finish(run, brief, 0)
            RESULTS[run_id] = []
            return

        target = await _what_we_are_looking_for(brief)

        _mark(run, "embed", "running")
        conversations = await rank.score_relevance(target, conversations)
        _mark(run, "embed", "done", f"{len(conversations)} embedded")
        _mark(run, "rerank", "done", f"top 25 of {len(conversations)}")

        conversations = conversations[:25]

        _mark(run, "analyze", "running")
        conversations, _ = await classify.classify_all(target, conversations)
        _mark(run, "analyze", "done", "25 judged")

        conversations = score.apply(conversations)
        _mark(run, "score", "done", f"{len(conversations)} scored")

        RESULTS[run_id] = conversations
        run["cost_usd"] = round(0.001 + len(conversations) * 0.0002, 4)
        _finish(run, brief, len(conversations))

    except Exception as exc:
        log.exception("flow.run_failed", run_id=run_id)
        run["state"] = "failed"
        run["error"] = str(exc)[:400]
        brief["latest_run_state"] = "failed"
        for stage in run["stages"]:
            if stage.state == "running":
                stage.state = "skipped"


async def _what_we_are_looking_for(brief: dict) -> str:
    """
    The text everything is matched against.

    The typed description always counts - it is what this particular search
    is about, and it is more specific than the product as a whole. The
    product profile is added on top when the brief is linked to a crawled
    product, because it carries two things a typed sentence usually does not:
    the domain, which stops a code indexer scoring as a vector database, and
    the pain words, which are phrased the way somebody with the problem
    writes rather than the way the website does.
    """
    description = brief["description"]
    product_id = brief.get("product_id")
    if not product_id:
        return description

    try:
        import uuid as _uuid

        from outreach.db.repositories import products as product_repo
        from outreach.db.session import session_scope as db
        from outreach.profile import Profile

        async with db() as session:
            product = await product_repo.get(session, _uuid.UUID(product_id))
            if product is None or not product.profile:
                return description
            profile = Profile(**product.profile)

        if not profile.is_usable:
            return description

        log.info("flow.using_profile", domain=profile.domain)
        return f"{profile.as_search_text()}\n\nThis search specifically: {description}"

    except Exception as exc:
        # A missing or malformed profile must never stop a run. Falling back
        # to the description is a worse search, not a broken one.
        log.warning("flow.profile_unavailable", error=str(exc))
        return description


def _mark(run: dict, stage_id: str, state: str, detail: str | None = None) -> None:
    for stage in run["stages"]:
        if stage.id == stage_id:
            stage.state = state
            if detail:
                stage.detail = detail
    done = sum(1 for s in run["stages"] if s.state == "done")
    run["percent"] = round(100 * done / len(run["stages"]))


def _finish(run: dict, brief: dict, count: int) -> None:
    for stage in run["stages"]:
        if stage.state in ("waiting", "running"):
            stage.state = "done"
    run["state"] = "succeeded"
    run["percent"] = 100
    brief["latest_run_state"] = "succeeded"
    brief["result_count"] = count


# ---------------------------------------------------------------- Results


def get_results(run_id: str) -> list[ResultOut]:
    conversations = RESULTS.get(run_id)
    if conversations is None:
        if run_id in RUNS:
            return []
        raise FlowError("No run with that id.")
    return [_to_result(c, i + 1) for i, c in enumerate(conversations)]


def _to_result(c: Conversation, rank_position: int) -> ResultOut:
    detail = score.breakdown(c)
    engagement = f"{c.comments} comments"
    if c.score:
        engagement += f" · {c.score} reactions"

    return ResultOut(
        id=c.source_id,
        rank=rank_position,
        score=c.opportunity or 0,
        band=score.band(c.opportunity or 0),
        conversation=ConversationOut(
            source=c.source,
            url=c.url,
            title=c.title or "(no title)",
            author=c.author or "unknown",
            created_at=c.created_at,
            engagement=engagement,
        ),
        problem=c.pain_point or "",
        actively_looking=c.asking_for_help,
        # The classifier does not rate severity separately; fit is the closest
        # honest proxy. Better to derive it visibly than to invent a number.
        pain_severity=max(1, min(5, round((c.product_fit or 0) * 5))),
        product_fit=c.product_fit or 0.0,
        evidence_quote=c.evidence_quote or "",
        score_detail=ScoreDetail(
            components=[ScoreComponent(**comp) for comp in detail["components"]],
            relevance=detail["relevance"],
            subtotal=detail["subtotal"],
            final=detail["final"],
            explain=detail["explain"],
        ),
        feedback=FEEDBACK.get(c.source_id),
        domain=c.post_domain,
        intent=c.intent,
        reason=c.reason,
    )


def record_feedback(result_id: str, useful: bool) -> None:
    """
    Free training data. Every dismissal is a human saying "not this", which
    is exactly the label the ranking will need and the hardest to collect
    deliberately.
    """
    FEEDBACK[result_id] = "useful" if useful else "not-useful"


async def draft_reply(result_id: str, allow_mention: bool) -> tuple[str, bool]:
    """Placeholder until the reply prompt exists. Never posts anything."""
    await asyncio.sleep(0)
    return (
        "A helpful answer to this person's actual problem goes here, written "
        "before any mention of our product."
        + (
            "\n\nIf you are looking at context caching specifically, [product] "
            "may be worth a look."
            if allow_mention
            else ""
        ),
        allow_mention,
    )
