"""
Find real posts to reply to, for one product on one platform.

The plan already decided what to search for, so nothing here takes keywords
from the caller. That is the point of the planner: the user presses a button
on a platform card and the agent's own terms are what run.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel

from outreach import planner
from outreach.api.deps import CurrentUser, DbSession
from outreach.db.repositories import products as repo
from outreach.db.repositories import search_runs as run_repo
from outreach.services import opportunity_service as svc

router = APIRouter(tags=["opportunities"])


class StartIn(BaseModel):
    platform: str = "github"

    #: Override what the plan chose. **Absent** means "use the plan".
    #:
    #: Absent and empty are different, and the difference is load-bearing:
    #: `null` defers to the plan, `[]` says "search none of these on purpose"
    #: - which is a real request, as in "these repositories only, no
    #: phrases". A caller that sends `[]` for a field it simply had no value
    #: for is asking to search nothing, and gets exactly that.
    #:
    #: The planner is a good first guess and a poor last word - it has never
    #: seen the results. Letting the user correct it before spending a run is
    #: cheaper than making them rewrite the whole plan to change one word.
    terms: list[str] | None = None
    repos: list[str] | None = None


class StartOut(BaseModel):
    run_id: str


@router.post(
    "/products/{product_id}/opportunities",
    response_model=StartOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start(
    product_id: uuid.UUID,
    payload: StartIn,
    user: CurrentUser,
    session: DbSession,
    background: BackgroundTasks,
) -> StartOut:
    """
    Start a search. Returns immediately; poll GET for progress and results.

    Takes 30 to 90 seconds: GitHub is slow, and every result is read twice -
    once for meaning, once for intent.
    """
    product = await repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No product with that id.")

    # Asked of the planner rather than hardcoded here.
    #
    # This was `!= "github"` and it outlived the Hacker News connector by a
    # whole build: the connector worked, the plan offered the card, and the
    # button answered "only GitHub is connected". A second list of what is
    # runnable will always drift from the real one, so there is only the
    # planner's now.
    runnable = planner.SEARCHABLE - planner.COMING_SOON
    if payload.platform not in runnable:
        known = ", ".join(sorted(runnable)) or "nothing"
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"We cannot search {payload.platform} yet. Connected: {known}.",
        )

    run_id = svc.start(
        product_id,
        payload.platform,
        terms=payload.terms,
        repos=payload.repos,
    )
    background.add_task(svc.execute, run_id)
    return StartOut(run_id=run_id)


@router.get("/opportunities/{run_id}")
async def get_run(run_id: str, user: CurrentUser, session: DbSession) -> dict:
    """
    Progress and results, for a live run or one from months ago.

    Ownership is re-checked on every poll rather than trusted from the start
    call, because a run id in a URL is otherwise a way to read somebody
    else's results.
    """
    try:
        run = await svc.load(session, run_id)
    except svc.OpportunityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    product = await repo.get_owned(session, uuid.UUID(run["product_id"]), user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No run with that id.")

    return run


@router.get("/products/{product_id}/last-search")
async def last_search(
    product_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    platform: str | None = None,
) -> dict | None:
    """
    The most recent search for this product, or null if there has never been one.

    Null rather than 404: "you have not searched yet" is an ordinary state
    for a new product, and making the home page treat it as an error would
    put a red box on the screen every time somebody adds one.

    `?platform=github` narrows it to one source. Without it the answer is
    whichever source ran last, which means searching Hacker News hides the
    GitHub results and vice versa - both are still stored, they just had no
    way to be asked for.
    """
    product = await repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No product with that id.")

    return await svc.latest(session, product_id, platform)


class SearchSummary(BaseModel):
    """One line of history. Deliberately without the results."""

    id: str
    platform: str
    state: str
    result_count: int
    top_score: int
    started_at: datetime
    finished_at: datetime | None


@router.get("/products/{product_id}/searches", response_model=list[SearchSummary])
async def search_history(
    product_id: uuid.UUID, user: CurrentUser, session: DbSession, limit: int = 20
) -> list[SearchSummary]:
    """
    Every search run for this product, newest first.

    Summaries only. A run carries its full results as JSONB and ten of them
    is megabytes, which is a slow request to render a list of dates and
    counts. Opening one fetches that run in full.
    """
    product = await repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No product with that id.")

    rows = await run_repo.list_for_product(session, product_id, limit=limit)
    return [
        SearchSummary(
            id=row.id,
            platform=row.platform,
            # An interrupted run is reported as failed here too, so the
            # history never shows a spinner for something nobody is doing.
            state="failed" if run_repo.is_lost(row) else row.state,
            result_count=row.result_count,
            top_score=row.top_score,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )
        for row in rows
    ]
