"""All SQL for leads. Nothing above this layer writes SQL."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from outreach.db.models.lead import STATES, Lead


async def get(session: AsyncSession, lead_id: uuid.UUID) -> Lead | None:
    return await session.get(Lead, lead_id)


async def list_for_product(
    session: AsyncSession,
    product_id: uuid.UUID,
    states: list[str] | None = None,
    limit: int = 200,
) -> list[Lead]:
    """Best first, because that is the order anybody works a list in."""
    stmt = select(Lead).where(Lead.product_id == product_id)
    if states:
        stmt = stmt.where(Lead.state.in_(states))
    stmt = stmt.order_by(Lead.score.desc(), Lead.last_seen_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def counts_by_state(
    session: AsyncSession, product_id: uuid.UUID
) -> dict[str, int]:
    """
    How many in each state. Every state present, including the empty ones.

    Returning zeros rather than omitting them means the caller never has to
    write `counts.get("won", 0)`, which is the sort of thing that is right
    everywhere until the one place it is forgotten.
    """
    stmt = (
        select(Lead.state, func.count())
        .where(Lead.product_id == product_id)
        .group_by(Lead.state)
    )
    found = {state: n for state, n in (await session.execute(stmt)).all()}
    return {state: found.get(state, 0) for state in STATES}


async def record(
    session: AsyncSession, product_id: uuid.UUID, results: list[dict]
) -> int:
    """
    Fold a finished run's results into the lead list. Returns how many are new.

    ── Why this is one statement and not a loop ─────────────────────────

    A read-then-write loop over a few hundred results is both slow and
    wrong: two runs finishing together would each find nothing, each
    insert, and one would lose to the unique constraint. `ON CONFLICT` lets
    the database settle it, which is what it is for.

    ── What an existing lead keeps ──────────────────────────────────────

    Everything a person put there. `state` and `note` are never touched by
    a search - the entire purpose of the table is that marking something
    replied survives the next run. `score` moves up but never down, so a
    prompt change cannot quietly demote a lead somebody is working, and
    `first_seen_at` stays as it was so "new" keeps its meaning.
    """
    rows = [_row(product_id, r) for r in results]
    rows = [r for r in rows if r is not None]
    if not rows:
        return 0

    # Same post twice inside one run would make ON CONFLICT fire against a
    # row this very statement is inserting, which Postgres refuses. Dedupe
    # first, keeping the best-scoring copy.
    best: dict[str, dict] = {}
    for row in rows:
        seen = best.get(row["source_id"])
        if seen is None or row["score"] > seen["score"]:
            best[row["source_id"]] = row

    stmt = insert(Lead).values(list(best.values()))
    stmt = stmt.on_conflict_do_update(
        constraint="uq_lead_product_source",
        set_={
            "last_seen_at": stmt.excluded.last_seen_at,
            # Titles get edited on GitHub; keep the current one.
            "title": stmt.excluded.title,
            "url": stmt.excluded.url,
            "score": func.greatest(Lead.score, stmt.excluded.score),
        },
    # `xmax = 0` is Postgres' own answer to "did this row get inserted or
    # updated", and it is worth using rather than inferring it from the
    # timestamps: an inference would quietly start lying the day somebody
    # adds `first_seen_at` to the update set above.
    ).returning(literal_column("(xmax = 0)").label("inserted"))

    written = (await session.execute(stmt)).all()
    return sum(1 for (inserted,) in written if inserted)


async def set_state(
    session: AsyncSession, lead: Lead, state: str, note: str | None = None
) -> Lead:
    """
    Move a lead. `note` is left alone when not given, cleared when empty.

    The distinction matters: pressing "replied" should not wipe a note, and
    clearing the note box should not be ignored.
    """
    if state not in STATES:
        raise ValueError(f"Unknown lead state: {state}")

    lead.state = state
    # `new` is where a lead starts, so returning to it means "actually, I
    # have not dealt with this" - and the timestamp should go with it.
    lead.acted_at = None if state == "new" else datetime.now(UTC)

    if note is not None:
        lead.note = note.strip() or None

    await session.flush()
    return lead


def _row(product_id: uuid.UUID, result: dict) -> dict | None:
    """One result to one row, or None when there is no identity to key on."""
    source_id = str(result.get("id") or "").strip()
    url = str(result.get("url") or "").strip()
    if not source_id or not url:
        return None

    now = datetime.now(UTC)
    return {
        "id": uuid.uuid4(),
        "product_id": product_id,
        "source_id": source_id,
        "url": url,
        "title": str(result.get("title") or "")[:2000],
        "container": (str(result.get("container")) if result.get("container") else None),
        "state": "new",
        "score": int(result.get("score") or 0),
        "first_seen_at": now,
        "last_seen_at": now,
    }


def to_dict(row: Lead) -> dict:
    return {
        "id": str(row.id),
        "source_id": row.source_id,
        "url": row.url,
        "title": row.title,
        "container": row.container,
        "state": row.state,
        "note": row.note,
        "score": row.score,
        "first_seen_at": row.first_seen_at.isoformat(),
        "last_seen_at": row.last_seen_at.isoformat(),
        "acted_at": row.acted_at.isoformat() if row.acted_at else None,
    }
