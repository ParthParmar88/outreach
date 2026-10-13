"""
Tests for lead state.

The database work is exercised against a real Postgres in `scripts` rather
than here - `record()` is one `ON CONFLICT` statement and mocking it would
only prove the mock works. What is worth pinning down in isolation is the
row mapping and the state machine, because those are pure and because both
have a rule that is easy to break by accident.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from outreach.db.models.lead import STATES, Lead
from outreach.db.repositories import leads as repo


def _result(**overrides) -> dict:
    result = {
        "id": "D_kwDOABCD",
        "url": "https://github.com/o/r/discussions/1",
        "title": "Prompt caching breaks with RAG",
        "container": "o/r",
        "score": 65,
    }
    result.update(overrides)
    return result


PRODUCT = uuid.UUID("11111111-1111-1111-1111-111111111111")


# ------------------------------------------------------------ row mapping


def test_a_result_becomes_a_new_lead():
    row = repo._row(PRODUCT, _result())

    assert row is not None
    assert row["source_id"] == "D_kwDOABCD"
    assert row["state"] == "new"
    assert row["score"] == 65
    # The pair "new" is counted from. Equal on insert, and only equal then.
    assert row["first_seen_at"] == row["last_seen_at"]


def test_a_result_with_no_identity_is_skipped():
    """
    Without a source id there is nothing to key on, so a lead would insert
    again on every run and could never be marked off.
    """
    assert repo._row(PRODUCT, _result(id="")) is None
    assert repo._row(PRODUCT, _result(url="")) is None


def test_a_missing_score_is_not_an_error():
    row = repo._row(PRODUCT, _result(score=None))
    assert row is not None and row["score"] == 0


def test_a_very_long_title_is_trimmed_to_fit():
    row = repo._row(PRODUCT, _result(title="x" * 5000))
    assert row is not None and len(row["title"]) == 2000


# ---------------------------------------------------------- state machine


def _lead(state: str = "new", note: str | None = None) -> Lead:
    now = datetime.now(UTC)
    return Lead(
        id=uuid.uuid4(),
        product_id=PRODUCT,
        source_id="D_1",
        url="u",
        title="t",
        state=state,
        note=note,
        score=10,
        first_seen_at=now,
        last_seen_at=now,
    )


class _Session:
    """Enough of a session for `set_state`, which only ever flushes."""

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_acting_on_a_lead_stamps_when():
    lead = _lead()
    await repo.set_state(_Session(), lead, "replied")

    assert lead.state == "replied"
    assert lead.acted_at is not None


@pytest.mark.asyncio
async def test_putting_a_lead_back_clears_the_stamp():
    """
    `new` is where a lead starts, so returning to it means "actually, I have
    not dealt with this" - and the timestamp has to go with it, or the lead
    reads as handled forever after.
    """
    lead = _lead(state="replied")
    lead.acted_at = datetime.now(UTC)

    await repo.set_state(_Session(), lead, "new")

    assert lead.state == "new"
    assert lead.acted_at is None


@pytest.mark.asyncio
async def test_changing_state_does_not_wipe_a_note():
    """Pressing a button must not destroy something somebody typed."""
    lead = _lead(note="asked about invalidation")

    await repo.set_state(_Session(), lead, "replied")

    assert lead.note == "asked about invalidation"


@pytest.mark.asyncio
async def test_an_empty_note_clears_it_rather_than_being_ignored():
    lead = _lead(note="old")

    await repo.set_state(_Session(), lead, "replied", note="   ")

    assert lead.note is None


@pytest.mark.asyncio
async def test_an_unknown_state_is_refused():
    """
    A state nothing can render is worse than an error: the row is written,
    looks fine in the table, and disappears from every screen.
    """
    with pytest.raises(ValueError, match="Unknown lead state"):
        await repo.set_state(_Session(), _lead(), "maybe-later")


def test_every_state_is_one_the_api_accepts():
    """
    The endpoint validates with a regex. If the two lists drift, one side
    accepts a value the other cannot store.
    """
    from pydantic import ValidationError

    from outreach.api.v1.leads import LeadUpdate

    for state in STATES:
        assert LeadUpdate(state=state).state == state

    with pytest.raises(ValidationError):
        LeadUpdate(state="archived")
