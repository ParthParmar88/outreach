"""
Stage 6: one number, 0-100, for how good an opportunity a post is.

── Why this multiplies instead of adding ─────────────────────────────────

The original plan had weights that summed: 30% relevance, 25% intent, and so
on. That arithmetic lets a post score 60 while being completely irrelevant,
because popularity and freshness can carry it there on their own. Users judge
the whole tool by the worst thing on the first page, so one such result costs
more than ten good ones earn.

Here match and intent are **gates**. Both are 0-1 and both multiply, so a
post that fails either one scores near zero no matter how popular or recent
it is. Freshness and engagement only modulate what survives, within a narrow
band, because they are tie-breakers rather than reasons.

Worked from the results this was built against:

  plur-ai/plur  relevance 1.00, intent BUILDING
    additive:        would score around 60  ← top of page one
    multiplicative:  scores 8               ← correctly buried
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from outreach.schemas.conversation import Conversation

#: How much each intent is worth as a lead. These are the most opinionated
#: numbers in the system and the first thing to tune once real leads have
#: been marked good or bad by a person.
#:
#: ── Why DIY_WORKAROUND scores near the top ───────────────────────────────
#:
#: It used to be folded into BUILDING at 0.10, on the reasoning that somebody
#: writing code is not shopping. For a product with switching costs that is
#: right. For a library it is backwards, and it was burying the best leads we
#: had: every one of the five best opportunities found by hand in a real run
#: was somebody hand-rolling context caching inside their own app.
#:
#: Think about what that person has already done for you. They hit the
#: problem, went looking, found nothing that solved it, and decided to spend
#: two weeks building it themselves. There is no qualification step left.
#: They are strictly further along than someone still asking what to do.
#:
#: The distinction that matters is not "writing code or not" - it is whether
#: they would *buy* this or *sell* something like it. Someone building a
#: workaround inside their own product is the first; someone building a
#: competing library is the second, and stays at BUILDING.
INTENT_WEIGHT = {
    "SOLUTION_SEEKING": 1.00,
    "COMPARISON": 0.90,
    "DIY_WORKAROUND": 0.85,
    "PROBLEM": 0.55,
    "SUPPORT": 0.15,
    "BUILDING": 0.10,
    "ANNOUNCEMENT": 0.05,
    "IRRELEVANT": 0.00,
}

#: Raw cosine from text-embedding-3-small runs roughly 0.25 for unrelated
#: text and 0.55 for a strong match. Mapping that band to 0-1 gives an
#: absolute score, unlike the min-max scaling used for display, which always
#: makes the best result in a set look perfect.
COSINE_FLOOR = 0.25
COSINE_CEILING = 0.55

#: Days for a post's freshness contribution to halve, per source.
#:
#: One number for both sources was a GitHub number applied to Hacker News,
#: and it is wrong there in both directions. An open GitHub issue from two
#: months ago is still live: it sits in the tracker, people are subscribed,
#: and a reply is read. A Hacker News thread is finished within about three
#: days of leaving the front page, so a reply to a month-old comment reaches
#: nobody at all.
#:
#: At thirty days a post scored 0.50 whichever source it came from, which
#: made a dead Hacker News thread look half as good as a live one, and left
#: almost nothing between day 3 and day 7 - the window where a Hacker News
#: reply is actually read.
FRESHNESS_HALF_LIFE = {
    "github": 30.0,
    "hackernews": 7.0,
}

#: For a source with no measured opinion yet. The conservative middle.
DEFAULT_HALF_LIFE = 21.0

#: Engagement above this adds nothing more.
ENGAGEMENT_SATURATION = 50.0

#: Star counts mapped onto 0-1, in log space, between these two points.
#:
#: ── Why reach is scored at all ───────────────────────────────────────────
#:
#: Because the product is outreach, not lead capture. The same comment under
#: the same issue is read by a different number of people depending on whose
#: repository it is in, and that difference is the entire reason for
#: commenting rather than emailing.
#:
#: Nothing used to know this. A real run put a post in a 1,655 star project
#: at the top of the page, above one in a 63,977 star project and another in
#: an 86,089 star project. All three were good posts; only one of them was
#: worth the half hour it takes to write a careful public reply.
#:
#: Log scale, because the difference between 500 stars and 5,000 is enormous
#: and the difference between 80,000 and 140,000 is not. The floor matches
#: `min_repo_stars`, since anything below it was dropped before scoring, and
#: the ceiling is set where a project is unambiguously well known.
REACH_FLOOR_STARS = 500
REACH_SATURATION_STARS = 50_000


def opportunity_score(conversation: Conversation, now: datetime | None = None) -> int:
    """0-100. Multiplicative, so a failed gate cannot be bought back."""
    now = now or datetime.now(UTC)

    match = _match(conversation)
    intent = INTENT_WEIGHT.get(conversation.intent or "IRRELEVANT", 0.0)

    # 0.60 to 1.00. Still deliberately narrow: reach, recency and popularity
    # reorder posts that already passed both gates, and none of them can make
    # an irrelevant post into a lead. Reach carries the largest share of the
    # three because it is the only one that changes how many people read the
    # reply, rather than how likely the thread is to still be live.
    modifier = (
        0.60
        + 0.15 * _reach(conversation)
        + 0.15 * _freshness(conversation, now)
        + 0.10 * _engagement(conversation)
    )

    return round(100 * match * intent * modifier)


#: Where the bands sit, and why they are not round numbers.
#:
#: These were set when scoring was additive, and never moved when it became
#: multiplicative. Two gates multiplying means real leads land far lower than
#: they used to: a genuinely good post scores in the forties, not the
#: seventies, because `match` is realistically around 0.6 rather than 1.0.
#:
#: Left alone, the thresholds quietly libelled the results. A whole page of
#: usable leads came back labelled "medium" with the best at 39, which reads
#: as "nothing here" to the person deciding whether to open any of them.
#:
#: Calibrated against a real run: a strong fit in an adjacent domain now
#: scores around 49 and reads `high`; a strong fit in the same domain can
#: reach the seventies and reads `very-high`.
VERY_HIGH = 65
HIGH = 40
MEDIUM = 20


def band(score: int) -> str:
    if score >= VERY_HIGH:
        return "very-high"
    if score >= HIGH:
        return "high"
    if score >= MEDIUM:
        return "medium"
    return "weak"


def breakdown(conversation: Conversation, now: datetime | None = None) -> dict:
    """
    Why this scored what it did, component by component.

    A marketer is about to post a public comment under their own name. They
    will not act on a number they cannot question, so every score has to be
    openable. The components must also add up to the score shown - a
    breakdown that does not reconcile is worse than none.
    """
    now = now or datetime.now(UTC)

    intent = INTENT_WEIGHT.get(conversation.intent or "IRRELEVANT", 0.0)
    freshness = _freshness(conversation, now)
    engagement = _engagement(conversation)
    reach = _reach(conversation)
    match = _match(conversation)

    # The gate is match x intent. Everything else only modulates it, which is
    # why they are shown as a separate band rather than as equal components.
    gate = match * intent
    modifier = 0.60 + 0.15 * reach + 0.15 * freshness + 0.10 * engagement

    stars = conversation.repo_stars
    reach_note = (
        f"{stars:,} stars in {conversation.container}"
        if stars is not None and stars >= 0
        else "star count unknown, scored as average"
    )

    return {
        "components": [
            {
                "name": "Intent",
                "raw": round(intent, 3),
                "weight": 1.0,
                "points": round(100 * match * intent * modifier),
                "note": conversation.intent or "unknown",
            },
            {
                "name": "Reach",
                "raw": round(reach, 3),
                "weight": 0.15,
                "points": round(100 * gate * 0.15 * reach),
                "note": reach_note,
            },
            {
                "name": "Freshness",
                "raw": round(freshness, 3),
                "weight": 0.15,
                "points": round(100 * gate * 0.15 * freshness),
                "note": f"{(now - conversation.created_at).days} days old",
            },
            {
                "name": "Engagement",
                "raw": round(engagement, 3),
                "weight": 0.10,
                "points": round(100 * gate * 0.10 * engagement),
                "note": f"{conversation.comments} comments, {conversation.score} reactions",
            },
        ],
        "relevance": round(match, 3),
        "subtotal": round(100 * intent * modifier),
        "final": conversation.opportunity or 0,
        "explain": (
            f"Product fit {match:.0%} multiplied by intent {intent:.0%}. "
            f"Reach, recency and engagement adjust the result by {modifier:.0%}."
        ),
    }


def apply(conversations: list[Conversation]) -> list[Conversation]:
    """Score everything and sort by it, best first."""
    now = datetime.now(UTC)
    for conversation in conversations:
        conversation.opportunity = opportunity_score(conversation, now)
    return sorted(conversations, key=lambda c: c.opportunity or 0, reverse=True)


# ---------------------------------------------------------------- components


def _match(conversation: Conversation) -> float:
    """
    How well this fits the product, 0-1.

    Two independent opinions, deliberately combined. The embedding knows the
    topic; the model knows whether *this person* could use the product. They
    disagree most on exactly the posts that matter - right topic, wrong
    author - and the model is the better judge there, so it carries more.
    """
    cosine = conversation.relevance_raw
    embedding_view = (
        _clamp((cosine - COSINE_FLOOR) / (COSINE_CEILING - COSINE_FLOOR))
        if cosine is not None
        else 0.5
    )

    model_view = conversation.product_fit
    if model_view is None:
        # Not classified: fall back to the embedding alone rather than
        # assuming the worst, but do not let it score as if it had passed.
        return embedding_view * 0.6

    return 0.35 * embedding_view + 0.65 * model_view


def _freshness(conversation: Conversation, now: datetime) -> float:
    """
    Exponential decay, not a linear age penalty.

    A thread's chance of still being live falls off fast at first and then
    flattens. Linear decay gets both ends wrong: it treats a two-day-old post
    as barely better than a ten-day-old one, and a ninety-day-old post as
    worthless when it is merely cold.

    How fast depends on the source, because "still live" means different
    things on each - see `FRESHNESS_HALF_LIFE`.
    """
    age_days = max((now - conversation.created_at).total_seconds() / 86400.0, 0.0)
    half_life = FRESHNESS_HALF_LIFE.get(conversation.source, DEFAULT_HALF_LIFE)
    return 0.5 ** (age_days / half_life)


def _reach(conversation: Conversation) -> float:
    """
    How many people a reply here would reach, 0-1.

    Unknown returns the midpoint rather than zero. A star count that was
    never looked up - a source with no equivalent, a failed request - is not
    evidence of an obscure project, and scoring it as one would quietly bury
    every result from any source that does not report stars.
    """
    stars = conversation.repo_stars
    if stars is None or stars < 0:
        return 0.5

    low = math.log1p(REACH_FLOOR_STARS)
    high = math.log1p(REACH_SATURATION_STARS)
    return _clamp((math.log1p(stars) - low) / (high - low))


def _engagement(conversation: Conversation) -> float:
    """
    Log-scaled, because the difference between 0 and 5 comments matters and
    the difference between 80 and 200 does not.
    """
    raw = conversation.comments * 2 + conversation.score
    return _clamp(math.log1p(raw) / math.log1p(ENGAGEMENT_SATURATION))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
