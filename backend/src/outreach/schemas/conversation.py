"""
Conversation - the one shape every source turns into.

GitHub issues, Hacker News stories and Reddit posts all become this, so
everything downstream reads one thing instead of three. Keep it small: add a
field when something actually needs it, not because a source happens to
return it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Conversation(BaseModel):
    source: str
    """"github", "hackernews", ..."""

    kind: str = "issue"
    """
    Which kind of thing this is within its source: "issue" or "discussion".

    Not folded into `source`, because everything downstream - dedup, the
    star filter, the insider filter, scoring - treats GitHub as one place and
    should keep doing so. This only exists because replying is different:
    an issue reply is a bug-tracker comment, a discussion reply is a forum
    answer, and the user needs to know which they are about to write.
    """

    source_id: str
    """Stable id within the source. Together with `source`, the identity."""

    url: str
    title: str | None = None
    body: str = ""

    author: str | None = None
    author_is_bot: bool = False
    """Bot chatter is the biggest source of noise in issue trackers, so it is
    marked when fetched rather than guessed at later."""

    created_at: datetime

    score: int = 0
    """Reactions, points, upvotes. Only comparable within one source."""

    comments: int = 0

    container: str | None = None
    """Where it lives: "run-llama/llama_index", a subreddit, etc."""

    author_association: str | None = None
    """
    GitHub only, and one of the strongest signals available.

    OWNER, MEMBER and COLLABORATOR mean the author is writing in their own
    project - a task ticket, a roadmap note, a self-assigned bug. There is
    nobody to sell to. NONE means an outsider turned up with a problem, which
    is precisely the lead we want.
    """

    labels: list[str] = []

    repo_stars: int | None = None
    """
    Stars on the repository this lives in. None when it was never looked up.

    Not a quality signal about the post - it is a reach signal about the room.
    The same comment under the same issue is read by a different number of
    people in a 1,600 star project and a 90,000 star one, and outreach is the
    one use of this data where that difference is the point.
    """

    found_by: str = ""
    """
    Which query first produced this: "phrase: re-embed + cost", "repo: owner/x".

    Recorded at fetch time because it cannot be recovered afterwards. A post
    matches whichever queries it matches, and the same post arrives from
    several - so asking later "which problem was this found under?" has no
    answer, while the query that actually returned it does.

    This is what the coverage report counts. Without it a run can search five
    problems, return results for one, and look identical to a run where the
    market only cared about one.
    """

    category: str | None = None
    """
    A GitHub Discussion's category: "Q&A", "Ideas", "Show and tell", ...

    The single cheapest quality signal this codebase gets for free. "Q&A" is
    somebody with a question; "Show and tell" is somebody announcing. Issues
    have no equivalent, so this is None for them.
    """

    is_answered: bool | None = None
    """
    Has a discussion been marked answered? None when it cannot be - issues,
    and discussion categories that are not Q&A.

    An unanswered question is the better outreach target of the two: there is
    a gap to fill rather than a resolved thread to arrive late to.
    """

    # ---- computed, not from the source ----------------------------------

    relevance: float | None = None
    """
    0-1, how well this matches what we are looking for. Filled in by
    rank.py, min-max scaled across one result set - so it compares results
    within a search and means nothing across two different searches.
    """

    relevance_raw: float | None = None
    """The unscaled cosine similarity, kept for tuning cutoffs."""

    # ---- from the classifier (stage 5) ----------------------------------

    intent: str | None = None
    """SOLUTION_SEEKING, COMPARISON, DIY_WORKAROUND, PROBLEM, SUPPORT,
    BUILDING, ANNOUNCEMENT or IRRELEVANT."""

    pain_point: str | None = None
    evidence_quote: str | None = None
    """Verbatim from the post, verified as a substring before storing. Empty
    when the model could not find real supporting text."""

    asking_for_help: bool = False

    post_domain: str | None = None
    """What kind of system the post is about, in the model's own words -
    "C++ code indexing", "LLM vector retrieval". Shown so a wrong domain
    judgement is visible rather than buried inside a score."""

    domain_match: str = "different"
    """
    How close the post's domain is to the product's: same, adjacent or
    different.

    Staleness, invalidation and expensive reindexing look identical in code
    indexers, databases, search engines and CI caches, so this has to be
    asked. It used to be a hard gate and zeroed anything but an exact match,
    which threw away the next room over - people running local inference,
    say - to catch the genuinely unrelated. Now it scales the fit instead.
    """

    same_domain: bool = False
    """Convenience for display: `domain_match == "same"`."""

    fit: str | None = None
    """strong, possible, weak or none."""

    product_fit: float | None = None
    """0-1: the judged fit, scaled by how close `domain_match` is."""

    reason: str | None = None

    # ---- from scoring (stage 6) -----------------------------------------

    opportunity: int | None = None
    """0-100. Relevance and intent are gates, so failing either scores near
    zero regardless of how popular or recent the post is."""

    @property
    def text(self) -> str:
        """Title and body together, for searching."""
        return f"{self.title}\n\n{self.body}".strip() if self.title else self.body
