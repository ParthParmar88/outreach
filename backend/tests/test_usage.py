"""
The token and cost total a run reports about itself.

The number is only worth printing if it is the real one, so these hold three
things in place: every concurrent call lands in the same counter, a cached
answer adds nothing, and a model with no known price is reported as unpriced
rather than quietly counted as free.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest

from outreach import classify, usage
from outreach.schemas.conversation import Conversation


def post(title: str) -> Conversation:
    return Conversation(
        source="github",
        source_id=title,
        url=f"https://example.com/{abs(hash(title))}",
        title=title,
        body="body text",
        author="someone",
        container="acme/thing",
        created_at=datetime.now(UTC),
    )


def chat_reply(prompt_tokens: int, completion_tokens: int) -> dict:
    return {"usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}}


def test_tokens_and_cost_add_up_per_stage() -> None:
    meter = usage.start()

    usage.record("rank", "text-embedding-3-small", {"usage": {"prompt_tokens": 1_000_000}})
    usage.record("judge", "gpt-4o-mini", chat_reply(1_000_000, 1_000_000))
    usage.record("judge", "gpt-4o-mini", chat_reply(1_000_000, 0))

    assert meter.tokens == 4_000_000
    # 0.02 for the embedding, then 0.15 + 0.60 and another 0.15 for the judge.
    assert meter.cost == pytest.approx(0.02 + 0.75 + 0.15)

    stages = meter.by_stage()
    assert list(stages) == ["rank", "judge"]
    assert stages["judge"].calls == 2
    assert stages["judge"].input_tokens == 2_000_000

    line = meter.summary()
    assert line.startswith("cost: 4,000,000 tokens, about $0.9200")
    assert "rank 1,000,000 tokens $0.0200" in line
    assert "judge 3,000,000 tokens $0.9000" in line


def test_nothing_spent_says_so() -> None:
    """All from cache is a real outcome and must not read as a missing line."""
    assert "nothing spent" in usage.start().summary()


def test_an_unknown_model_is_counted_but_not_priced() -> None:
    """
    Tokens are the fact, dollars are a lookup.

    A model missing from the price table must not make a run look free.
    """
    meter = usage.start()
    usage.record("judge", "some-new-model", chat_reply(500, 100))

    assert meter.tokens == 600
    assert meter.cost == 0.0
    assert meter.unpriced == ["some-new-model"]
    assert "no price on file for some-new-model" in meter.summary()


def test_a_reply_without_usage_is_ignored() -> None:
    meter = usage.start()

    usage.record("judge", "gpt-4o-mini", {})
    usage.record("judge", "gpt-4o-mini", {"usage": None})
    usage.record("judge", "gpt-4o-mini", {"usage": {"prompt_tokens": "many"}})

    assert meter.tokens == 0


def test_recording_outside_a_run_does_nothing() -> None:
    """The same code serves API calls that are not part of any run."""
    usage._METER.set(None)
    usage.record("judge", "gpt-4o-mini", chat_reply(10, 10))  # must not raise


@pytest.mark.anyio
async def test_concurrent_calls_share_one_counter() -> None:
    """
    The judge runs its posts through `asyncio.gather`.

    Each task gets a copy of the context, so this only works because the copy
    points at the same counter. If it ever stops, the total silently reports
    a fraction of the run.
    """
    meter = usage.start()

    async def call() -> None:
        await asyncio.sleep(0)
        usage.record("judge", "gpt-4o-mini", chat_reply(100, 10))

    await asyncio.gather(*(call() for _ in range(8)))

    assert meter.by_stage()["judge"].calls == 8
    assert meter.tokens == 880


class FakeResponse:
    status_code = 200

    def json(self) -> dict:
        content = json.dumps({"scores": [{"i": 0, "s": 3}, {"i": 1, "s": 0}]})
        return {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 30},
        }


class FakeClient:
    async def post(self, url: str, headers: dict, json: dict) -> FakeResponse:
        return FakeResponse()


@pytest.mark.anyio
async def test_the_triage_reports_what_the_model_billed() -> None:
    meter = usage.start()

    await classify._ask_triage(
        FakeClient(), "{product}\ncount={count}\n{titles}", "product", [post("a"), post("b")]
    )

    spent = meter.by_stage()["triage"]
    assert (spent.calls, spent.input_tokens, spent.output_tokens) == (1, 900, 30)
