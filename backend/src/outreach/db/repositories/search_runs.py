"""All SQL for search runs. Nothing above this layer writes SQL."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from outreach.db.models.search_run import SearchRun

#: Past this with no update, a run marked "running" is not running.
#:
#: A run is 30 to 90 seconds of GitHub, so anything still claiming to work
#: after fifteen minutes died with the process that started it. Without this
#: the home page would show a spinner forever for a search nobody is doing.
LOST_AFTER = timedelta(minutes=15)


def is_lost(run: SearchRun) -> bool:
    """True when a run says it is working but nothing is working on it."""
    if run.state not in ("queued", "running"):
        return False
    return datetime.now(UTC) - run.started_at > LOST_AFTER


async def get(session: AsyncSession, run_id: str) -> SearchRun | None:
    return await session.get(SearchRun, run_id)


async def latest_for_product(
    session: AsyncSession, product_id: uuid.UUID, platform: str | None = None
) -> SearchRun | None:
    """
    The most recent search for this product, whatever happened to it.

    Not "the most recent successful one". A search that failed is still the
    last thing that happened, and hiding it would leave somebody looking at
    a week-old result wondering why yesterday's search never appeared.

    `platform` narrows it to one source. Without that, a product searched on
    both GitHub and Hacker News can only ever show whichever ran last, and
    running one hides the other's results even though both are still there.
    """
    stmt = select(SearchRun).where(SearchRun.product_id == product_id)
    if platform:
        stmt = stmt.where(SearchRun.platform == platform)
    stmt = stmt.order_by(SearchRun.started_at.desc()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_product(
    session: AsyncSession, product_id: uuid.UUID, limit: int = 20
) -> list[SearchRun]:
    stmt = (
        select(SearchRun)
        .where(SearchRun.product_id == product_id)
        .order_by(SearchRun.started_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def save(session: AsyncSession, run: dict) -> SearchRun:
    """
    Write the service's run dict to the table, creating or updating.

    Takes the dict rather than keyword arguments so the in-memory run stays
    the single description of a run. Two lists of fields drifting apart is
    exactly how a stored run ends up missing the one thing you wanted.
    """
    results = run.get("results") or []
    row = await session.get(SearchRun, run["id"])
    if row is None:
        row = SearchRun(id=run["id"], product_id=uuid.UUID(run["product_id"]))
        session.add(row)

    row.platform = run.get("platform") or "github"
    row.state = run.get("state") or "queued"
    row.terms = run.get("terms")
    row.repos = run.get("repos")
    row.results = results
    row.notes = run.get("notes") or []
    row.stages = run.get("stages") or []
    row.percent = int(run.get("percent") or 0)
    row.error = run.get("error")

    row.result_count = len(results)
    row.top_score = max((int(r.get("score") or 0) for r in results), default=0)

    row.started_at = _when(run.get("started_at")) or datetime.now(UTC)
    if row.state in ("succeeded", "failed"):
        row.finished_at = datetime.now(UTC)

    await session.flush()
    return row


def _when(value: str | datetime | None) -> datetime | None:
    """The service keeps timestamps as ISO strings; the column wants a date."""
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def to_dict(row: SearchRun) -> dict:
    """
    Back into the shape the run endpoint returns.

    A run loaded from the table has to be indistinguishable from one still
    in memory, or the results screen needs two code paths for the same
    thing.
    """
    lost = is_lost(row)
    return {
        "id": row.id,
        "product_id": str(row.product_id),
        "platform": row.platform,
        "terms": row.terms,
        "repos": row.repos,
        "state": "failed" if lost else row.state,
        "stages": row.stages,
        "percent": row.percent,
        "notes": row.notes,
        "results": row.results,
        "error": (
            "This search was interrupted, probably by the server restarting. "
            "Nothing was lost except the run itself - start it again."
            if lost
            else row.error
        ),
        "started_at": row.started_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }
