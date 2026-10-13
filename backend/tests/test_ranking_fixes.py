"""
Tests for the scoring, classification and query changes.

Each of these encodes a judgement that was wrong before and is expensive to
get wrong again, so the tests are written around the decision rather than
around the function: "a workaround outranks a competitor" survives a rewrite,
`INTENT_WEIGHT["DIY_WORKAROUND"] == 0.85` does not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from outreach import dedupe, score
from outreach.classify import Analysis
from outreach.connectors import github as gh
from outreach.connectors import github_discussions as gd
from outreach.planner import _usable_terms
from outreach.schemas.conversation import Conversation

SEARCH_URL = "https://api.github.com/search/issues"


def _conversation(**overrides) -> Conversation:
    base = {
        "source": "github",
        "source_id": "1",
        "url": "https://github.com/o/r/issues/1",
        "title": "t",
        "created_at": datetime.now(UTC) - timedelta(days=5),
        "relevance_raw": 0.45,
        "product_fit": 0.9,
        "intent": "SOLUTION_SEEKING",
        "comments": 3,
    }
    base.update(overrides)
    return Conversation(**base)


# ------------------------------------------------- fix 2: DIY_WORKAROUND


def test_hand_rolling_the_product_outranks_shipping_a_competitor():
    """
    The whole point of the new intent.

    Someone building a workaround inside their own app has proved the need
    and finished their search. Someone shipping a competing library never
    buys. Both write code, and the old rubric scored them identically at
    0.10.
    """
    workaround = score.opportunity_score(_conversation(intent="DIY_WORKAROUND"))
    competitor = score.opportunity_score(_conversation(intent="BUILDING"))

    assert workaround > competitor * 4


def test_workaround_ranks_near_the_top_but_below_asking_outright():
    weights = score.INTENT_WEIGHT
    assert weights["SOLUTION_SEEKING"] > weights["DIY_WORKAROUND"]
    assert weights["DIY_WORKAROUND"] > weights["PROBLEM"]


def test_unknown_intent_still_scores_zero():
    """A label we do not recognise must not score as if it passed."""
    assert score.opportunity_score(_conversation(intent="SOMETHING_NEW")) == 0


# ------------------------------------------------- fix 6: domain penalty


def test_adjacent_domain_survives_at_a_penalty():
    """
    Was a hard zero, which threw away the next room over.

    A KV-cache post in a local inference server is not the same domain and is
    full of exactly the right people.
    """
    same = Analysis(fit="strong", domain_match="same").product_fit
    adjacent = Analysis(fit="strong", domain_match="adjacent").product_fit

    assert adjacent > 0
    assert adjacent < same


def test_different_domain_is_still_effectively_dead():
    """
    The gate existed for a real reason and must keep working.

    A C++ language server reindexing after a header change is a perfect
    structural match and a completely different market.
    """
    strong_but_wrong = Analysis(fit="strong", domain_match="different").product_fit

    assert strong_but_wrong < 0.15


def test_domain_and_fit_multiply_rather_than_gate():
    assert Analysis(fit="none", domain_match="same").product_fit == 0.0
    weak_adjacent = Analysis(fit="weak", domain_match="adjacent").product_fit
    strong_adjacent = Analysis(fit="strong", domain_match="adjacent").product_fit
    assert weak_adjacent < strong_adjacent


def test_unrecognised_domain_value_is_treated_as_different():
    """A model that invents a value must not accidentally pass the gate."""
    assert Analysis(fit="strong", domain_match="sort of").product_fit < 0.15


def test_same_domain_bool_still_available_for_display():
    assert Analysis(domain_match="same").same_domain is True
    assert Analysis(domain_match="adjacent").same_domain is False


# ------------------------------------------------- fix 3: intersections


def test_plain_phrase_is_quoted_exactly():
    assert gh.render_phrase("stale embeddings") == '"stale embeddings"'


def test_intersection_becomes_two_anded_terms():
    """
    Unquoted terms are ANDed by GitHub, which the quoting rule hides.

    This is the form that finds posts about two things colliding, which is
    what every good lead turns out to be.
    """
    assert gh.render_phrase("prompt caching + RAG") == '"prompt caching" RAG'


def test_single_word_sides_stay_unquoted():
    assert gh.render_phrase("cache + retrieval") == "cache retrieval"


def test_intersection_survives_untidy_input():
    assert gh.render_phrase('  "prompt caching"  +   RAG  ') == '"prompt caching" RAG'


def test_both_connectors_read_the_same_syntax():
    """
    A term must mean the same thing on both sides of the search.

    Otherwise the same plan produces different searches depending on which
    connector ran it, which is the sort of thing nobody notices for months.
    """
    issues = gh.build_query("prompt caching + RAG", days=30)
    discussions = gd.build_query("prompt caching + RAG", days=30)

    assert '"prompt caching" RAG' in issues
    assert '"prompt caching" RAG' in discussions


def test_empty_intersection_does_not_produce_a_dangling_query():
    assert gh.render_phrase("+") == ""
    assert gh.render_phrase("") == ""


def test_intersection_that_finds_nothing_gets_the_opposite_advice():
    """
    An empty intersection is too narrow; an empty phrase is too long.

    Telling someone to shorten a term that was already too specific sends
    them the wrong way.
    """
    hint = gh._why_nothing("prompt caching + RAG")
    assert hint is not None and "dropping one side" in hint

    hint = gh._why_nothing("my index keeps going stale every night")
    assert hint is not None and "sentence-like" in hint


# ------------------------------------------------- fix 3: term validation


def test_sentence_shaped_terms_are_dropped():
    assert _usable_terms(["how do I stop re-embedding everything"]) == []


def test_bare_single_words_are_dropped():
    """`cache` matches tens of thousands and is a lottery, not a search."""
    assert _usable_terms(["cache"]) == []


def test_single_words_are_allowed_inside_an_intersection():
    """They earn it: both sides must appear, so the pair is precise."""
    assert _usable_terms(["cache + retrieval"]) == ["cache + retrieval"]


def test_three_sided_intersections_are_dropped():
    assert _usable_terms(["a + b + c"]) == []


def test_terms_are_normalised_and_deduplicated():
    assert _usable_terms(["stale index", "Stale  Index", "  stale index  "]) == [
        "stale index"
    ]


def test_intersection_spacing_is_normalised():
    assert _usable_terms(["prompt caching+RAG"]) == ["prompt caching + RAG"]


def test_model_order_is_preserved():
    terms = _usable_terms(["first term", "second term", "third term"])
    assert terms == ["first term", "second term", "third term"]


# ------------------------------------------------- term spread


def test_terms_about_one_concept_are_all_kept():
    """
    Clustering is not a bug, and treating it as one cost a run.

    A per-concept cap used to drop these, on the theory that it would force
    coverage of the product's other problems. It cannot: a cap does not
    create terms that were never written, it only deletes the ones that
    were. A real run went from 140 classified posts to 10 overnight, and the
    concept everything clustered on turned out to be where the market was.
    """
    clustered = [
        "prompt caching",
        "prompt caching + RAG",
        "caching strategy",
        "cache invalidation",
        "cached prefix",
        "context caching",
        "cache hit rate",
        "caching layer",
    ]

    assert _usable_terms(clustered) == clustered


def test_spread_across_problems_also_survives_intact():
    spread = [
        "prompt caching + RAG",
        "cached prefix + invalidated",
        "re-embed + cost",
        "stale embeddings",
        "chunk reuse",
        "retrieval + latency",
        "vector index + rebuild",
    ]

    assert _usable_terms(spread) == spread


def test_a_full_set_of_terms_reaches_the_search():
    """
    The regression this guards against was one of volume.

    Terms feed the phrase queries *and* repository discovery, so losing
    two thirds of them starves the run twice over.
    """
    terms = [f"cache angle{n} + detail" for n in range(12)]

    assert len(_usable_terms(terms)) == 12


def test_the_cap_is_still_the_hard_ceiling():
    """Diversity is unlimited; total count is not."""
    terms = [f"concept{n} + variant" for n in range(40)]

    assert len(_usable_terms(terms)) == 12


# ------------------------------------------------- band calibration


def test_a_strong_adjacent_lead_reads_as_high_not_medium():
    """
    The bands were set for additive scoring and never moved.

    A page of usable leads came back topping out at 39 and labelled
    "medium", which reads as "nothing here" to somebody deciding whether to
    open any of them.
    """
    from outreach.classify import Analysis

    fit = Analysis(fit="strong", domain_match="adjacent").product_fit
    lead = _conversation(intent="SOLUTION_SEEKING", product_fit=fit, relevance_raw=0.42)

    assert score.band(score.opportunity_score(lead)) in ("high", "very-high")


def test_a_wrong_domain_post_still_reads_weak():
    from outreach.classify import Analysis

    fit = Analysis(fit="strong", domain_match="different").product_fit
    junk = _conversation(intent="SOLUTION_SEEKING", product_fit=fit, relevance_raw=0.28)

    assert score.band(score.opportunity_score(junk)) == "weak"


def test_bands_stay_in_order():
    assert score.VERY_HIGH > score.HIGH > score.MEDIUM


# ------------------------------------------------- near-duplicates


TITLE = "Performance: zero prompt-cache hits + large tool-schema overhead"


def _post(i: int, title: str, author: str, comments: int = 0) -> Conversation:
    return _conversation(
        source_id=str(i), url=f"u{i}", title=title, author=author, comments=comments
    )


def test_the_same_person_posting_twice_is_collapsed():
    """
    Straight from a real run: identical title, author and quote, at
    positions four and five of page one.
    """
    kept, dropped = dedupe.collapse(
        [_post(1, TITLE, "zeros335882878"), _post(2, TITLE, "zeros335882878")]
    )

    assert dropped == 1
    assert len(kept) == 1


def test_the_copy_people_replied_to_is_the_one_kept():
    """A thread with five replies is a better place to arrive than a dead one."""
    kept, _ = dedupe.collapse(
        [
            _post(1, TITLE, "someone", comments=0),
            _post(2, TITLE, "someone", comments=5),
        ]
    )

    assert kept[0].comments == 5


def test_position_is_kept_when_a_later_copy_wins():
    """Replacing in place, so collapsing cannot reorder the results."""
    kept, _ = dedupe.collapse(
        [
            _post(1, "first", "a"),
            _post(2, TITLE, "someone", comments=0),
            _post(3, "last", "b"),
            _post(4, TITLE, "someone", comments=9),
        ]
    )

    assert [c.source_id for c in kept] == ["1", "4", "3"]


def test_tag_prefixes_do_not_hide_a_duplicate():
    """"[Bug] X" and "X" from one person are one post, filed twice."""
    _, dropped = dedupe.collapse(
        [_post(1, TITLE, "someone"), _post(2, f"[Bug] {TITLE}", "someone")]
    )

    assert dropped == 1


def test_an_issue_and_a_discussion_for_the_same_thing_collapse():
    """Different id spaces entirely, so only a content check finds these."""
    issue = _post(1, TITLE, "someone")
    discussion = _post(2, TITLE, "someone")
    discussion.kind = "discussion"

    _, dropped = dedupe.collapse([issue, discussion])

    assert dropped == 1


def test_different_people_with_the_same_title_are_left_alone():
    """
    Two people writing "Prompt caching" are usually asking different things,
    and losing one silently is worse than showing both.
    """
    kept, dropped = dedupe.collapse(
        [_post(1, "Prompt caching", "alice"), _post(2, "Prompt caching", "bob")]
    )

    assert dropped == 0
    assert len(kept) == 2


def test_untitled_posts_are_never_merged_together():
    """Otherwise every untitled post collapses into one, which reads as a filter."""
    kept, dropped = dedupe.collapse(
        [_post(1, "", "alice"), _post(2, "", "bob"), _post(3, "", "alice")]
    )

    assert dropped == 0
    assert len(kept) == 3


def test_genuinely_different_posts_survive():
    kept, dropped = dedupe.collapse(
        [
            _post(1, "prompt caching breaks with RAG", "a"),
            _post(2, "re-embedding costs too much", "a"),
            _post(3, "stale vector index", "a"),
        ]
    )

    assert dropped == 0
    assert len(kept) == 3


def test_empty_input_is_fine():
    assert dedupe.collapse([]) == ([], 0)


# ------------------------------------------------- stale plans


def test_a_prompt_change_makes_every_existing_plan_stale():
    """
    The bug that made two rounds of planner improvements invisible.

    Without the prompt version in the hash, a change reaches products
    created afterwards and nothing else: every existing plan keeps its
    stored hash, looks current forever, and goes on searching the old terms.
    """
    from outreach import planner

    profile = {"domain": "x"}
    before = planner.source_hash(profile, "desc", "goal")

    original = planner.PROMPT_VERSION
    try:
        planner.PROMPT_VERSION = "planner.test-next"
        after = planner.source_hash(profile, "desc", "goal")
    finally:
        planner.PROMPT_VERSION = original

    assert before != after


def test_an_unchanged_product_is_not_rewritten_for_no_reason():
    from outreach import planner

    profile = {"domain": "x"}
    assert planner.source_hash(profile, "d", "g") == planner.source_hash(
        profile, "d", "g"
    )


# ------------------------------------------------- fix 5: insider filter


def _item(association: str, **overrides) -> dict:
    item = {
        "node_id": f"N_{association}",
        "html_url": "https://github.com/some/repo/issues/1",
        "created_at": "2026-08-01T00:00:00Z",
        "title": "t",
        "body": "b",
        "user": {"login": "someone", "type": "User"},
        "author_association": association,
        "repository_url": "https://api.github.com/repos/some/repo",
        "comments": 1,
        "reactions": {"total_count": 1},
    }
    item.update(overrides)
    return item


@pytest.mark.asyncio
@respx.mock
async def test_contributors_are_kept():
    """
    The change that matters.

    A merged pull request usually means somebody fixed a typo once, not that
    they work on the project. Excluding them removed roughly 80% of results,
    and the engaged power user filing a thoughtful feature request is nearly
    always a CONTRIBUTOR.
    """
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200, json={"total_count": 1, "items": [_item("CONTRIBUTOR")]}
        )
    )

    result = await gh.search(["x"], outsiders_only=True, max_requests=1)

    assert len(result.conversations) == 1


@pytest.mark.asyncio
@respx.mock
async def test_people_who_run_the_repo_are_still_dropped():
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "total_count": 3,
                "items": [
                    _item("OWNER"),
                    _item("MEMBER"),
                    _item("COLLABORATOR"),
                    _item("NONE"),
                ],
            },
        )
    )

    result = await gh.search(["x"], outsiders_only=True, max_requests=1)

    assert [c.author_association for c in result.conversations] == ["NONE"]


@pytest.mark.asyncio
@respx.mock
async def test_new_association_values_are_kept_not_silently_dropped():
    """
    The cost of a blocklist, accepted deliberately.

    GitHub keeps adding values. A new one now falls through and is kept,
    which shows up as one extra result rather than as a whole category
    vanishing without a note.
    """
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "total_count": 1,
                "items": [_item("FIRST_TIME_CONTRIBUTOR"), _item("MANNEQUIN")],
            },
        )
    )

    result = await gh.search(["x"], outsiders_only=True, max_requests=1)

    assert len(result.conversations) == 2


# ------------------------------------------------- fix 7: repos by hits


@pytest.mark.asyncio
@respx.mock
async def test_repos_are_ranked_by_how_often_they_actually_come_up():
    """
    Evidence, not self-description.

    Ranking repositories by how closely their description matches the product
    reliably picks the big framework repos and misses where the conversation
    happens.
    """
    def item(repo: str, n: int) -> dict:
        return _item(
            "NONE",
            node_id=f"{repo}{n}",
            repository_url=f"https://api.github.com/repos/{repo}",
            html_url=f"https://github.com/{repo}/issues/{n}",
        )

    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "total_count": 6,
                "items": [
                    item("busy/repo", 1),
                    item("busy/repo", 2),
                    item("busy/repo", 3),
                    item("quiet/repo", 1),
                    item("quiet/repo", 2),
                    item("onceonly/repo", 1),
                ],
            },
        )
    )

    found = await gh.repos_by_hits(["x"], min_stars=0, max_requests=1)

    assert found[0] == ("busy/repo", 3)
    assert found[1] == ("quiet/repo", 2)


@pytest.mark.asyncio
@respx.mock
async def test_a_single_mention_is_not_evidence():
    """Every phrase has a long tail of repos that mentioned it once."""
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200, json={"total_count": 1, "items": [_item("NONE")]}
        )
    )

    assert await gh.repos_by_hits(["x"], min_stars=0, max_requests=1) == []


@pytest.mark.asyncio
async def test_no_phrases_costs_nothing():
    assert await gh.repos_by_hits([]) == []


# ------------------------------------------------- competitor lookup


REPO_SEARCH = "https://api.github.com/search/repositories"


def _repo(full_name: str, stars: int = 1000, open_issues: int = 10) -> dict:
    return {
        "full_name": full_name,
        "description": "d",
        "stargazers_count": stars,
        "open_issues_count": open_issues,
    }


@pytest.mark.asyncio
@respx.mock
async def test_a_famous_repo_that_merely_mentions_the_name_is_not_picked():
    """
    The bug this function exists for.

    Sorting by stars answers "the most popular repository that mentions this
    word", not "the repository called this" - which resolved `mem0` to a
    92,000 star project called claude-mem, and `Haystack` to funNLP.
    """
    respx.get(REPO_SEARCH).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    _repo("thedotmack/claude-mem", stars=92_000),
                    _repo("mem0ai/mem0", stars=30_000, open_issues=706),
                ]
            },
        )
    )

    async with httpx.AsyncClient() as client:
        found = await gh.find_repo_by_name(client, "mem0")

    assert found is not None
    assert found["full_name"] == "mem0ai/mem0"


@pytest.mark.asyncio
@respx.mock
async def test_punctuation_does_not_prevent_a_match():
    respx.get(REPO_SEARCH).mock(
        return_value=httpx.Response(200, json={"items": [_repo("zilliztech/GPT-Cache")]})
    )

    async with httpx.AsyncClient() as client:
        found = await gh.find_repo_by_name(client, "gptcache")

    assert found is not None


@pytest.mark.asyncio
@respx.mock
async def test_no_confident_match_returns_none_rather_than_a_guess():
    """
    A wrong repository is not a near miss.

    It is a whole sweep spent on a project unrelated to the product, which is
    worse than the empty slot it filled.
    """
    respx.get(REPO_SEARCH).mock(
        return_value=httpx.Response(
            200, json={"items": [_repo("someone/something-else", stars=80_000)]}
        )
    )

    async with httpx.AsyncClient() as client:
        assert await gh.find_repo_by_name(client, "acme-cache") is None


@pytest.mark.asyncio
@respx.mock
async def test_the_busiest_project_wins_a_shared_name():
    """Several projects share a name; only one has anybody filing issues."""
    respx.get(REPO_SEARCH).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    _repo("abandoned/zep", stars=9_000, open_issues=0),
                    _repo("getzep/zep", stars=3_000, open_issues=24),
                ]
            },
        )
    )

    async with httpx.AsyncClient() as client:
        found = await gh.find_repo_by_name(client, "zep")

    assert found is not None
    assert found["full_name"] == "getzep/zep"


@pytest.mark.asyncio
@respx.mock
async def test_the_query_restricts_matching_to_the_name():
    route = respx.get(REPO_SEARCH).mock(
        return_value=httpx.Response(200, json={"items": []})
    )

    async with httpx.AsyncClient() as client:
        await gh.find_repo_by_name(client, "mem0")

    assert "in:name" in route.calls[0].request.url.params["q"]


@pytest.mark.asyncio
@respx.mock
async def test_a_failed_lookup_is_not_an_exception():
    respx.get(REPO_SEARCH).mock(return_value=httpx.Response(503))

    async with httpx.AsyncClient() as client:
        assert await gh.find_repo_by_name(client, "mem0") is None


@pytest.mark.asyncio
async def test_an_unmakeable_comparison_is_not_reported_as_a_perfect_one():
    """
    The bug that switched the whole relevance filter off without saying so.

    `_by_relevance` answered 1.0 - a perfect match - when it could not
    compare, and every caller read that as "checked, and ideal". One
    transient embedding error therefore let every candidate through, which
    is how a repository scoring 0.27 against the gate ended up in a plan.
    """
    from outreach import planner

    scored = await planner._by_relevance(
        [{"full_name": "wmww/Pinecone", "description": "x", "open_issues": 1}],
        "",  # nothing to compare against
    )

    assert scored[0][1] == planner.UNCHECKED
    assert scored[0][1] != 1.0


def test_unscored_survives_but_badly_scored_does_not():
    """
    Opposite treatment on purpose.

    "Scored badly" is a reason to drop a repository. "Could not be scored" is
    not - a network blip should not empty the plan - so those are kept and
    the run says so instead of passing them off as verified.
    """
    from outreach import planner

    assert planner._passes(planner.UNCHECKED)
    assert planner._passes(0.55)
    assert not planner._passes(0.27)


@pytest.mark.asyncio
@respx.mock
async def test_rescuing_a_wrong_owner_uses_the_same_rules_as_a_lookup():
    """
    Two functions answered one question, and the fix landed in one of them.

    `resolve_repo` kept its own most-starred-exact-name rule, so asked to
    rescue `pinecone/pinecone` it returned `wmww/Pinecone` long after the
    other path had stopped doing that.
    """
    respx.get(REPO_SEARCH).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    _repo("wmww/Pinecone", stars=896, open_issues=40),
                    _repo("pinecone-io/canopy", stars=1_031, open_issues=12),
                ]
            },
        )
    )

    async with httpx.AsyncClient() as client:
        assert await gh.resolve_repo(client, "pinecone/pinecone") == "pinecone-io/canopy"


@pytest.mark.parametrize(
    ("owner", "product"),
    [
        ("pinecone-io", "pinecone"),   # suffix: io
        ("mem0ai", "mem0"),            # suffix: ai
        ("langchain-ai", "langchain"),
        ("getzep", "zep"),             # prefix: the plain name was taken
        ("weaviate", "weaviate"),      # exact
    ],
)
def test_an_organisation_named_after_the_product_is_recognised(owner, product):
    assert gh._is_owner_for(owner, product)


@pytest.mark.parametrize(
    ("owner", "product"),
    [
        # Each of these actually took the real product's slot in a run.
        ("zephyrproject-rtos", "zep"),   # an RTOS
        ("haystackeditor", "haystack"),  # a code editor
        ("langchain4j", "langchain"),    # the Java port, not the project
        ("matrix-org", "pinecone"),      # a p2p network router
        ("wmww", "pinecone"),            # "an unmaintained programming language"
    ],
)
def test_a_coincidental_prefix_is_not_an_organisation_match(owner, product):
    """
    `startswith` alone is far too loose, and every one of these proves it.

    The remainder has to look like something a company appends to its own
    name, not merely be any string at all.
    """
    assert not gh._is_owner_for(owner, product)


@pytest.mark.asyncio
@respx.mock
async def test_the_right_organisation_beats_a_more_popular_name_match():
    """
    Pinecone owns no repository called `pinecone`, so an exact-name rule
    rejected every correct answer and took two impostors instead.
    """
    respx.get(REPO_SEARCH).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    _repo("wmww/Pinecone", stars=896, open_issues=40),
                    _repo("matrix-org/pinecone", stars=488, open_issues=30),
                    _repo("pinecone-io/canopy", stars=1_031, open_issues=12),
                ]
            },
        )
    )

    async with httpx.AsyncClient() as client:
        found = await gh.find_repo_candidates(client, "Pinecone")

    assert [f["full_name"] for f in found] == ["pinecone-io/canopy"]


@pytest.mark.asyncio
@respx.mock
async def test_several_candidates_come_back_for_the_caller_to_judge():
    """
    The right organisation still has the wrong repository in it: Pinecone's
    busiest is a folder of notebooks. Only a description can separate those,
    so the choice belongs to the caller.
    """
    respx.get(REPO_SEARCH).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    _repo("pinecone-io/examples", open_issues=90),
                    _repo("pinecone-io/canopy", open_issues=12),
                ]
            },
        )
    )

    async with httpx.AsyncClient() as client:
        found = await gh.find_repo_candidates(client, "Pinecone")

    assert len(found) == 2
    assert found[0]["full_name"] == "pinecone-io/examples"  # busiest first
