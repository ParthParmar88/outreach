"""
The evaluation command: the counting, and the two ways it could lie.

This is the tool every prompt change is judged with, so a mistake here does
not break one result - it gives a wrong verdict on all of them. Nothing in
this file calls a model; the two stages are replaced with canned answers.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eval import run as eval_run
from outreach import classify
from outreach.schemas.conversation import Conversation


def result(
    label: int, triage: int | None = None, opportunity: int | None = None
) -> eval_run.Result:
    conversation = Conversation(
        source="github",
        source_id=f"{label}-{triage}-{opportunity}",
        url="https://example.com/1",
        title=f"label {label} triage {triage} score {opportunity}",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        opportunity=opportunity,
        intent="PROBLEM" if opportunity is not None else None,
    )
    return eval_run.Result(
        key=conversation.source_id,
        label=label,
        product="a product",
        conversation=conversation,
        triage=triage,
        judged=opportunity is not None,
    )


def test_triage_is_right_when_leads_are_kept_and_junk_is_dropped() -> None:
    results = [
        result(2, triage=3),  # lead kept       right
        result(2, triage=2),  # lead kept       right
        result(2, triage=1),  # lead dropped    wrong
        result(0, triage=0),  # junk dropped    right
        result(0, triage=2),  # junk kept       wrong
    ]

    total = eval_run.tally(results, eval_run.kept_by_triage)

    assert (total.leads_passed, total.leads) == (2, 3)
    assert (total.junk_stopped, total.junk) == (1, 2)
    assert (total.right, total.counted) == (3, 5)
    assert total.accuracy == pytest.approx(0.6)


def test_judge_is_right_on_either_side_of_the_threshold() -> None:
    results = [
        result(2, opportunity=45),  # exactly on the line counts as a lead
        result(2, opportunity=44),
        result(0, opportunity=10),
        result(0, opportunity=80),
    ]

    total = eval_run.tally(results, eval_run.called_a_lead(45))

    assert (total.leads_passed, total.leads) == (1, 2)
    assert (total.junk_stopped, total.junk) == (1, 2)


def test_maybes_are_never_counted() -> None:
    """Either answer is defensible for a maybe, so neither is scored."""
    results = [result(1, triage=3, opportunity=90), result(1, triage=0, opportunity=0)]

    assert eval_run.tally(results, eval_run.kept_by_triage).counted == 0
    assert eval_run.tally(results, eval_run.called_a_lead(45)).counted == 0


def test_a_post_the_judge_could_not_answer_is_left_out_not_marked_wrong() -> None:
    unjudged = result(2)
    assert unjudged.judged is False

    total = eval_run.tally([unjudged, result(2, opportunity=60)], eval_run.called_a_lead(45))

    assert (total.leads_passed, total.leads) == (1, 1)


def test_a_lead_has_to_get_past_both_stages_to_be_shown() -> None:
    results = [
        result(2, triage=3, opportunity=70),  # shown
        result(2, triage=1, opportunity=70),  # the triage dropped it
        result(2, triage=3, opportunity=20),  # the judge rejected it
        result(0, triage=3, opportunity=70),  # junk that got through both
    ]

    total = eval_run.tally(results, eval_run.survives_both(45))

    assert (total.leads_passed, total.leads) == (1, 3)
    assert total.junk - total.junk_stopped == 1


CANDIDATE = {
    "source": "github",
    "source_id": "1",
    "url": "https://example.com/1",
    "title": "a title",
    "body": "a body",
    "created_at": "2026-01-01T00:00:00+00:00",
    "relevance_raw": 0.55,
    # What the judge said when this was first collected.
    "intent": "SOLUTION_SEEKING",
    "fit": "strong",
    "domain_match": "same",
    "product_fit": 0.9,
    "opportunity": 76,
    "_product": "a product",
}


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = {"github:1": {"label": 0}, "github:gone": {"label": 2}}
    monkeypatch.setattr(eval_run.store, "load_candidates", lambda: {"github:1": dict(CANDIDATE)})
    monkeypatch.setattr(eval_run.store, "load_labels", lambda: labels)


def test_the_old_judgement_is_cleared_before_judging_again(pool: None) -> None:
    """
    A candidate is stored with the verdict it got on the day it was found.

    Carried into a new run, a post the model failed to answer for would keep
    that old verdict and be reported as what today's prompt said.
    """
    results, skipped = eval_run.load_labelled()

    assert skipped == 0
    assert len(results) == 1  # the label with no candidate behind it is ignored
    conversation = results[0].conversation
    assert conversation.intent is None
    assert conversation.product_fit is None
    assert conversation.opportunity is None
    # The embedding score is not being measured, and the score needs it.
    assert conversation.relevance_raw == 0.55


@pytest.mark.anyio
async def test_the_score_does_not_drift_as_the_post_gets_older(
    pool: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two runs a year apart must give the same number for the same prompt."""

    async def fake_judge(product: str, conversations: list[Conversation]) -> tuple:
        for conversation in conversations:
            conversation.intent = "SOLUTION_SEEKING"
            conversation.product_fit = 0.9
        return conversations, []

    monkeypatch.setattr(classify, "classify_all", fake_judge)

    results, _ = eval_run.load_labelled()
    await eval_run.run_judge(results)

    assert results[0].judged is True
    # Worked by hand for a seven day old GitHub post with unknown stars:
    #   match    0.35 * 1.0 + 0.65 * 0.9                      = 0.935
    #   modifier 0.60 + 0.15 * 0.5 + 0.15 * 0.5 ** (7 / 30)   = 0.8026
    assert results[0].opportunity == 75


@pytest.mark.anyio
async def test_the_report_says_how_many_each_stage_got_right(
    pool: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fake_triage(product: str, conversations: list[Conversation]) -> tuple:
        return {0: 3}, 0, 0

    async def fake_judge(product: str, conversations: list[Conversation]) -> tuple:
        for conversation in conversations:
            conversation.intent = "ANNOUNCEMENT"
            conversation.product_fit = 0.0
        return conversations, []

    monkeypatch.setattr(classify, "triage_scores", fake_triage)
    monkeypatch.setattr(classify, "classify_all", fake_judge)

    assert await eval_run.evaluate(threshold=45, stage="all") == 0

    out = capsys.readouterr().out
    # The one labelled post is junk: the triage kept it, the judge rejected it.
    assert "triage    0 of 1 right  (0%)" in out
    assert "judge     1 of 1 right  (100%)" in out
    assert "junk shown     0 of 1" in out
    # One label is not a measurement, and the report has to say so.
    assert "Only 1 labels are counted" in out
    assert "cost: nothing spent" in out


@pytest.mark.anyio
async def test_nothing_labelled_is_an_instruction_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(eval_run.store, "load_candidates", lambda: {})
    monkeypatch.setattr(eval_run.store, "load_labels", lambda: {})

    assert await eval_run.evaluate(threshold=45, stage="all") == 1
    assert "eval.label" in capsys.readouterr().out
