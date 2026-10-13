"""
The coverage line: which of the plan's problems found something.

Seen on a real Hacker News run. The search returned 402 posts, and the line
underneath said every problem "matched nothing at all, so those terms are
wrong". Hacker News labels its results differently from GitHub, and only
GitHub's label was being counted.
"""

from __future__ import annotations

from datetime import UTC, datetime

from outreach.schemas.conversation import Conversation
from outreach.services import opportunity_service as svc

GROUPS = {"Token cost": ["token cost"], "Debugging": ["LLM debugging + issue"]}


def found(by: str, source: str = "hackernews") -> Conversation:
    return Conversation(
        source=source,
        source_id=by,
        url="https://example.com/1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        found_by=by,
    )


def test_hacker_news_results_count_towards_their_problem() -> None:
    posts = [
        found("story: token cost"),
        found("comment: token cost"),
        found("comment: LLM debugging + issue"),
    ]

    counts, swept = svc._tally(posts, GROUPS)

    assert counts == {"Token cost": 2, "Debugging": 1}
    assert swept == 0


def test_github_phrases_and_sweeps_still_count() -> None:
    posts = [
        found("phrase: Token Cost", "github"),  # matched without regard to case
        found("repo: acme/thing", "github"),
    ]

    counts, swept = svc._tally(posts, GROUPS)

    assert counts == {"Token cost": 1, "Debugging": 0}
    assert swept == 1


def test_a_problem_is_only_called_unmatched_when_it_found_nothing() -> None:
    line = svc._coverage([found("comment: token cost")], [], GROUPS)

    assert "Token cost 1->0" in line
    assert "Debugging 0->0" in line
    assert "Debugging matched nothing at all" in line
    assert "Token cost, Debugging matched nothing" not in line
