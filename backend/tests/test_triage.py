"""
The title filter, and the failure that made it useless.

Measured on a real run: asked about 40 titles, the model answered about nine
and dropped the rest. Every dropped title was then filled in with "maybe",
which is how ten judge slots went to Hacker News chatter while sixteen clear
matches sat unread. These tests hold the fix in place.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from outreach import classify
from outreach.schemas.conversation import Conversation


def post(title: str, container: str = "acme/thing") -> Conversation:
    return Conversation(
        source="github",
        source_id=title,
        url=f"https://example.com/{abs(hash(title))}",
        title=title,
        body="body text",
        author="someone",
        container=container,
        created_at=datetime.now(UTC),
    )


class FakeResponse:
    status_code = 200

    def __init__(self, scores: list[dict]) -> None:
        self._scores = scores

    def json(self) -> dict:
        content = json.dumps({"scores": self._scores})
        return {"choices": [{"message": {"content": content}}]}


class FakeClient:
    """Replies with a canned answer per call, and records what it was asked."""

    def __init__(self, replies: list[list[dict]]) -> None:
        self._replies = replies
        self.prompts: list[str] = []

    async def post(self, url: str, headers: dict, json: dict) -> FakeResponse:
        self.prompts.append(json["messages"][0]["content"])
        return FakeResponse(self._replies[len(self.prompts) - 1])


TEMPLATE = "{product}\ncount={count}\n{titles}"


@pytest.mark.anyio
async def test_missing_titles_are_asked_again() -> None:
    """
    A reply that skips titles triggers one more request, for those only.

    This is the whole fix. The model treats the task as filtering and returns
    only what it likes, so the gap has to be chased rather than filled in.
    """
    batch = [post(f"title {i}") for i in range(5)]
    client = FakeClient(
        [
            # First ask: answers about two of five.
            [{"i": 1, "s": 3}, {"i": 3, "s": 2}],
            # Re-ask: the other three, and it rejects all of them.
            [{"i": 0, "s": 0}, {"i": 2, "s": 1}, {"i": 4, "s": 0}],
        ]
    )

    scores = await classify._ask_triage(client, TEMPLATE, "product", batch)

    assert scores == {0: 0, 1: 3, 2: 1, 3: 2, 4: 0}
    assert len(client.prompts) == 2

    # The re-ask carries only the skipped titles, keeping their original
    # numbers - renumbering would map answers onto the wrong posts.
    second = client.prompts[1]
    assert "count=3" in second
    assert "0. [acme/thing] title 0" in second
    assert "title 1" not in second


@pytest.mark.anyio
async def test_a_complete_reply_is_not_asked_twice() -> None:
    batch = [post(f"title {i}") for i in range(3)]
    client = FakeClient([[{"i": 0, "s": 1}, {"i": 1, "s": 2}, {"i": 2, "s": 3}]])

    scores = await classify._ask_triage(client, TEMPLATE, "product", batch)

    assert scores == {0: 1, 1: 2, 2: 3}
    assert len(client.prompts) == 1


@pytest.mark.anyio
async def test_still_missing_after_the_re_ask_scores_below_the_keep_line() -> None:
    """
    Skipped twice is an answer, not a gap.

    It used to be `TRIAGE_KEEP_FROM`, which meant a title the model declined
    to score reached the judge ahead of one it had actually read and rated 1.
    """
    batch = [post("kept"), post("ignored")]

    scores = await classify._ask_triage(
        FakeClient([[{"i": 0, "s": 3}], []]), TEMPLATE, "product", batch
    )
    assert scores == {0: 3}
    assert 1 not in scores
    assert classify.TRIAGE_UNSCORED < classify.TRIAGE_KEEP_FROM

    # End to end: the ignored title does not reach the judge, even though
    # there is room for it.
    kept, notes = await _triage_with(
        FakeClient([[{"i": 0, "s": 3}], []]), batch, keep=2
    )
    assert [c.title for c in kept] == ["kept"]
    assert "1 clear" in notes[0]


@pytest.mark.anyio
async def test_a_failed_request_keeps_its_titles_eligible() -> None:
    """
    The opposite case, and it must stay opposite.

    Nothing was read, so nothing was judged. Dropping these would delete
    twenty posts over one network error.
    """

    class BrokenClient(FakeClient):
        async def post(self, url: str, headers: dict, json: dict):
            raise RuntimeError("connection reset")

    batch = [post("a"), post("b")]
    kept, notes = await _triage_with(BrokenClient([]), batch, keep=2)

    assert [c.title for c in kept] == ["a", "b"]
    assert any("could not be scored" in n for n in notes)


@pytest.mark.anyio
async def test_indices_never_shown_are_ignored() -> None:
    """A model that invents an index must not score a post nobody asked about."""
    batch = [post("a"), post("b")]
    client = FakeClient([[{"i": 0, "s": 3}, {"i": 7, "s": 3}], [{"i": 1, "s": 1}]])

    scores = await classify._ask_triage(client, TEMPLATE, "product", batch)

    assert scores == {0: 3, 1: 1}


def test_batches_are_small_enough_to_be_answered_fully() -> None:
    """
    Forty was measured returning nine.

    Not a style preference: the larger the list, the more of it the model
    silently drops.
    """
    assert classify.TRIAGE_BATCH <= 20


def test_the_prompt_demands_one_entry_per_title() -> None:
    """
    The cause was the wording, not the model.

    The old first line said "filter a list of post titles down to the ones
    worth reading", and the model did exactly that.
    """
    text = classify.TRIAGE_PROMPT_PATH.read_text(encoding="utf-8")

    assert "{count}" in text
    assert "Score **every** post title" in text.splitlines()[0]
    assert "never an omission" in text


async def _triage_with(client: FakeClient, batch: list[Conversation], keep: int):
    """Run the real triage against the fake client, with the cache bypassed."""
    from unittest.mock import patch

    with (
        patch.object(classify, "_load_json", return_value={}),
        patch.object(classify, "_save_json"),
        patch.object(classify.httpx, "AsyncClient", return_value=_Ctx(client)),
        patch.object(classify.settings, "openai_api_key", "test-key"),
    ):
        return await classify.triage("product", batch, keep)


class _Ctx:
    def __init__(self, client: FakeClient) -> None:
        self._client = client

    async def __aenter__(self) -> FakeClient:
        return self._client

    async def __aexit__(self, *exc: object) -> bool:
        return False


def test_the_rubric_knows_a_workaround_from_a_launch() -> None:
    """
    Both were measured wrong, in opposite directions.

    "Cutting (Claude Code) token spend on dynamic workflows 80%" - an Ask HN
    post, and the best lead two runs in a row - scored 2, because a title that
    reports a result reads like an announcement. Meanwhile `Show HN:` launches
    of competing products scored 3 and filled four of the six clear slots.

    With the distinction written down: the workaround scores 3, the launch 1.
    """
    text = classify.TRIAGE_PROMPT_PATH.read_text(encoding="utf-8")

    assert "`Show HN:` is a product launch. Score it 1." in text
    assert "solved this by hand, for their own use, is a 3" in text
    assert "does not make it a launch" in text
