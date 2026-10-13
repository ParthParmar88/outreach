"""
Makes and stores the marketing plan for a product.

Sits between the API and the planner agent. Its real job is deciding *when*
to spend a model call: a plan costs real money and takes half a minute, so it
is written once and reused until something it was built from actually changes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from outreach import planner
from outreach.db.models.product import CrawlState, Product
from outreach.db.repositories import products as repo
from outreach.db.session import session_scope

log = structlog.get_logger(__name__)


class PlanError(Exception):
    """Something the user needs to know about, phrased for a person."""


def current_plan(product: Product) -> planner.MarketingPlan | None:
    """The stored plan, or None. Does not generate anything."""
    if not product.plan:
        return None
    try:
        return planner.MarketingPlan(**product.plan)
    except Exception:
        # A plan written by an older version of the shape. Treat it as absent
        # rather than crashing the page that wanted to show it.
        log.warning("plan.unreadable", product_id=str(product.id))
        return None


def is_stale(product: Product) -> bool:
    """True when the product has changed since the plan was written."""
    if not product.plan:
        return True
    expected = planner.source_hash(
        product.profile, product.description or "", product.goal or ""
    )
    return expected != product.plan_source_hash


async def ensure_plan(product_id: uuid.UUID, force: bool = False) -> None:
    """
    Write the plan if there isn't a current one. Runs in the background.

    Every exit path leaves the product readable. A missing plan is a product
    you can still search manually, which is what it was before the planner
    existed - so failing quietly here is genuinely safe.
    """
    async with session_scope() as session:
        product = await repo.get(session, product_id)
        if product is None:
            return

        if not force and not is_stale(product):
            return

        # The crawl is what the plan is mostly built from. Writing one before
        # the site has been read produces exactly the generic advice the
        # prompt spends half its length trying to prevent.
        if product.state == CrawlState.CRAWLING:
            log.info("plan.waiting_for_crawl", product_id=str(product_id))
            return

        snapshot = {
            "name": product.name,
            "url": product.canonical_url,
            "description": product.description or "",
            "goal": product.goal or "",
            "profile": product.profile,
        }

    # Outside the session: a model call can take half a minute and must not
    # hold a database connection open while it does.
    plan = await planner.make_plan(**snapshot)
    if plan is None:
        log.warning("plan.not_written", product_id=str(product_id))
        return

    # The model named repositories from memory; check them against the live
    # GitHub before anybody spends a search on them.
    #
    # The profile's own keywords make better queries than the domain does.
    # They are the short technical terms the field uses - "vector database",
    # "RAG" - and GitHub matches repository names and descriptions, so a
    # precise description of the product finds fewer real projects than a
    # vague description of its field.
    profile = snapshot["profile"] or {}
    queries = [profile.get("domain") or snapshot["name"], *(profile.get("keywords") or [])]

    product_text = "\n".join(
        str(part)
        for part in [
            profile.get("domain"),
            profile.get("summary"),
            "; ".join(profile.get("problems") or []),
            snapshot["description"],
        ]
        if part
    )

    notes = await planner.ground_repos(
        plan, queries, product_text, competitors=profile.get("competitors") or []
    )
    # Last, so it applies to every way a repository can get into the plan.
    notes += planner.drop_own_repos(plan, snapshot["name"], snapshot["url"])
    for note in notes:
        log.info("plan.repos_grounded", product_id=str(product_id), change=note)

    async with session_scope() as session:
        product = await repo.get(session, product_id)
        if product is None:
            return
        product.plan = plan.model_dump()
        product.plan_source_hash = planner.source_hash(
            product.profile, product.description or "", product.goal or ""
        )
        product.plan_made_at = datetime.now(UTC)
        log.info(
            "plan.saved",
            product_id=str(product_id),
            platforms=len(plan.platforms),
            actionable=len(plan.actionable),
        )
