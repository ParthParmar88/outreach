"""
A product must not be sent to search its own repository.

Seen on a real run: the top result of a search was a discussion in the
product's own repository. It is the best possible match on every signal the
plan uses, and it is not a lead - the people writing there already use it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from outreach import planner
from outreach.planner import MarketingPlan, Platform
from outreach.schemas.conversation import Conversation
from outreach.services import opportunity_service as svc


def plan_with(repos: list[str]) -> MarketingPlan:
    return MarketingPlan(
        platforms=[
            Platform(key="github", name="GitHub", target_places=list(repos)),
            Platform(key="hackernews", name="Hacker News"),
        ]
    )


def places(plan: MarketingPlan) -> list[str]:
    return plan.platforms[0].target_places


def test_the_products_own_repositories_are_removed() -> None:
    plan = plan_with(["acme/acme", "acme/acme-docs", "someone/acme", "mlflow/mlflow"])

    notes = planner.drop_own_repos(plan, "Acme", "https://acme.dev")

    # Owned by the product, or named after it. The rest is somebody else's.
    assert places(plan) == ["mlflow/mlflow"]
    assert len(notes) == 3
    assert "acme/acme - it is this product's own repository" in notes[0]


def test_the_name_in_the_web_address_counts_too() -> None:
    """The product is called one thing and its organisation another."""
    plan = plan_with(["acmehq/sdk", "other/thing"])

    planner.drop_own_repos(plan, "Acme Cloud", "https://www.acmehq.com/docs")

    assert places(plan) == ["other/thing"]


def test_spelling_differences_do_not_hide_it() -> None:
    plan = plan_with(["Lang-Fuse/Lang_Fuse"])

    planner.drop_own_repos(plan, "LangFuse", "https://example.com")

    assert places(plan) == []


def test_a_repository_that_only_mentions_the_name_is_kept() -> None:
    """`acme-tools/awesome-acme` is about the product, not the product itself."""
    plan = plan_with(["acme-tools/awesome-acme"])

    assert planner.drop_own_repos(plan, "Acme", "https://acme.dev") == []
    assert places(plan) == ["acme-tools/awesome-acme"]


def test_nothing_to_compare_against_removes_nothing() -> None:
    plan = plan_with(["a/b"])

    assert planner.drop_own_repos(plan, "", "") == []
    assert places(plan) == ["a/b"]


def post(container: str, source: str = "github") -> Conversation:
    return Conversation(
        source=source,
        source_id=container,
        url="https://example.com/1",
        container=container,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_posts_from_the_products_own_repository_are_dropped_from_a_search() -> None:
    """
    Taking the repository out of the plan was not enough.

    A phrase search covers all of GitHub, so its posts came back anyway and
    took the top slot of the next real run.
    """
    own = planner.own_names("Acme", "https://acme.dev")
    found = [post("acme/acme"), post("mlflow/mlflow"), post("Acme is great", "hackernews")]

    kept, dropped = svc._drop_own(found, own, places=["mlflow/mlflow"])

    assert [c.container for c in kept] == ["mlflow/mlflow", "Acme is great"]
    assert dropped == 1


def test_a_repository_the_user_asked_for_by_name_is_searched() -> None:
    own = planner.own_names("Acme", "https://acme.dev")

    kept, dropped = svc._drop_own([post("acme/acme")], own, places=["Acme/Acme"])

    assert len(kept) == 1
    assert dropped == 0
