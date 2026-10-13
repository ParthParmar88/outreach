"""
One screen answering one question: what has outreach done for me?

Account-wide rather than per product. A person wants to know whether the
tool is worth the time, and that answer does not live inside any single
product.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from outreach import planner
from outreach.api.deps import CurrentUser, DbSession
from outreach.db.repositories import activity as repo
from outreach.db.repositories import products as product_repo

router = APIRouter(tags=["activity"])

#: Every platform worth a row, whether or not it has been used.
#:
#: Reddit appears with zeroes and a "not connected" tag, instead of being
#: silently absent - a missing row reads as "we found you nothing there",
#: which is a claim about Reddit rather than about us.
#:
#: Whether a row is connected is asked of the planner, not written here.
#: This list used to say so itself, and Hacker News stayed "not connected"
#: on this screen long after its connector shipped.
PLATFORMS: list[dict[str, str]] = [
    {"key": "github", "name": "GitHub"},
    {"key": "hackernews", "name": "Hacker News"},
    {"key": "reddit", "name": "Reddit"},
    {"key": "linkedin", "name": "LinkedIn"},
]

_EMPTY_SEARCH = {"searches": 0, "results": 0}
_EMPTY_REPLY = {"written": 0, "posted": 0, "answered": 0, "skipped": 0}


@router.get("/activity")
async def get_activity(
    user: CurrentUser, session: DbSession, product_id: uuid.UUID | None = None
) -> dict:
    """
    Totals for one product, or for the whole account when none is given.

    Counted in SQL over every row rather than by paging through them, so the
    numbers do not silently stop at a display limit.

    An unknown or someone else's `product_id` is not an error - the
    ownership join simply matches nothing and every total is zero. That is
    the same answer a product with no activity gives, so a wrong id cannot
    be used to find out whose it is.
    """
    product = None
    if product_id is not None:
        product = await product_repo.get_owned(session, product_id, user.id)

    searches = await repo.searches_by_platform(session, user.id, product_id)
    replies = await repo.replies_by_platform(session, user.id, product_id)

    rows = []
    # A platform the user somehow has data for but that is not in the list
    # above still gets a row: better an unexpected name on screen than
    # totals that do not add up to the sum of their parts.
    known = {p["key"] for p in PLATFORMS}
    extra = [
        {"key": key, "name": key}
        for key in sorted((searches.keys() | replies.keys()) - known)
    ]
    runnable = planner.SEARCHABLE - planner.COMING_SOON

    for platform in [*PLATFORMS, *extra]:
        key = platform["key"]
        found = searches.get(key, _EMPTY_SEARCH)
        wrote = replies.get(key, _EMPTY_REPLY)
        rows.append(
            {
                "key": key,
                "name": platform["name"],
                "connected": key in runnable,
                "searches": found["searches"],
                "results": found["results"],
                "written": wrote["written"],
                "posted": wrote["posted"],
                "answered": wrote["answered"],
                "skipped": wrote["skipped"],
            }
        )

    totals = {
        field: sum(int(row[field]) for row in rows)
        for field in ("searches", "results", "written", "posted", "answered", "skipped")
    }

    return {
        "products": await repo.product_count(session, user.id),
        # Which product these numbers are about, so the screen can name it
        # rather than trusting the caller to remember what it asked for.
        "product": (
            {"id": str(product.id), "name": product.name, "domain": product.domain}
            if product
            else None
        ),
        "totals": totals,
        "platforms": rows,
        "outcomes": await repo.outcomes(session, user.id, product_id),
    }
