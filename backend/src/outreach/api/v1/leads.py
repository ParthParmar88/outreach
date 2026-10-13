"""
Leads: the opportunities you are actually working, across every search.

A search is a moment; a lead outlives it. These endpoints are the only way
the state a person put on a lead - replied, ignored, won - gets read back,
and they are deliberately the only place it can be written.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from outreach.api.deps import CurrentUser, DbSession
from outreach.db.models.lead import STATES
from outreach.db.repositories import leads as repo
from outreach.db.repositories import products as product_repo

router = APIRouter(tags=["leads"])

NOT_FOUND = "No lead with that id."


class LeadOut(BaseModel):
    id: str
    source_id: str
    url: str
    title: str
    container: str | None
    state: str
    note: str | None
    score: int
    first_seen_at: str
    last_seen_at: str
    acted_at: str | None


class LeadList(BaseModel):
    """The list plus the counts, because the screen always needs both."""

    leads: list[LeadOut]
    counts: dict[str, int]


class LeadUpdate(BaseModel):
    #: One of the four states. Validated here so a typo is a 422 rather
    #: than a row in a state nothing knows how to render.
    state: str = Field(pattern="^(new|replied|ignored|won)$")
    #: Omitted leaves the note alone; empty clears it. Pressing "replied"
    #: must not wipe what somebody wrote.
    note: str | None = Field(default=None, max_length=4000)


@router.get("/products/{product_id}/leads", response_model=LeadList)
async def list_leads(
    product_id: uuid.UUID,
    user: CurrentUser,
    session: DbSession,
    state: Annotated[list[str] | None, Query()] = None,
) -> LeadList:
    """
    Every lead for this product, best first.

    `state` may be repeated to filter - `?state=new&state=replied`. The
    counts are always for the whole product, not the filtered view: a
    filter that also changed the totals would make the tabs above it
    disagree with themselves the moment one was pressed.
    """
    product = await product_repo.get_owned(session, product_id, user.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No product with that id.")

    wanted = [s for s in (state or []) if s in STATES]
    rows = await repo.list_for_product(session, product_id, states=wanted or None)

    return LeadList(
        leads=[LeadOut(**repo.to_dict(row)) for row in rows],
        counts=await repo.counts_by_state(session, product_id),
    )


@router.patch("/leads/{lead_id}", response_model=LeadOut)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    user: CurrentUser,
    session: DbSession,
) -> LeadOut:
    """
    Move a lead, and optionally leave a note on it.

    Ownership is checked through the lead's product rather than trusted
    from the id, because a lead id in a URL is otherwise a way to write to
    somebody else's list.
    """
    lead = await repo.get(session, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    product = await product_repo.get_owned(session, lead.product_id, user.id)
    if product is None:
        # Same answer as a missing lead. Telling somebody a lead exists but
        # is not theirs is more than they need to know.
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    updated = await repo.set_state(session, lead, payload.state, payload.note)
    return LeadOut(**repo.to_dict(updated))
