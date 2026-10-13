"""
A draft must say which platform its post is on.

`source` used to default to "github" and the frontend never sent it, so
every Hacker News reply was counted as a GitHub one. Pinned here because the
failure is silent: nothing errors, one row of the activity page is just
wrong.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from outreach import planner
from outreach.api.v1.tracking import DraftIn

POST = {
    "source_id": "41234567",
    "url": "https://news.ycombinator.com/item?id=41234567",
}


def test_a_draft_without_a_source_is_rejected():
    with pytest.raises(ValidationError):
        DraftIn(**POST)


def test_the_source_sent_is_the_source_kept():
    assert DraftIn(source="hackernews", **POST).source == "hackernews"


def test_every_searchable_platform_is_a_valid_source():
    """The draft check and the search check read the same list."""
    for platform in planner.SEARCHABLE:
        assert DraftIn(source=platform, **POST).source == platform
