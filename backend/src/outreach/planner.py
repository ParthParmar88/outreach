"""
The planner agent: product profile + goal -> a marketing plan.

This is the step that turns a search tool into a marketing platform. Before
it, the user had to know which words to search for. After it, the agent reads
what the product is and what the owner wants, and writes the plan - including
the search terms our crawler then executes.

Two things it must not do, both of which an unguided model does by default:

  * Give advice that would fit any product. "Post on Reddit, engage with the
    community, build in public" is free and worth nothing.
  * Pretend we can search a platform we cannot. The plan is split into what
    we can act on and what is only advice, and the user is told which is
    which rather than clicking a LinkedIn card and finding nothing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import structlog
from pydantic import BaseModel, Field

from outreach import usage
from outreach.config import settings
from outreach.connectors import github as gh_syntax

log = structlog.get_logger(__name__)

CHAT_URL = "https://api.openai.com/v1/chat/completions"
PROMPT_PATH = Path(__file__).parent / "llm" / "prompts" / "planner.v1.md"
#: Bump on every prompt change: it is part of `source_hash`, so this is what
#: makes existing plans regenerate instead of sticking to the old rubric.
PROMPT_VERSION = "planner.v11"

#: Platforms we can actually search. Everything else is advice only.
#: The model is not asked to decide this - we know it, and letting it guess
#: is how a user ends up clicking "find posts" on LinkedIn.
SEARCHABLE = {"github", "hackernews"}

#: Not yet built, but the plan may still recommend it. Shown as "coming soon"
#: rather than as something you can run today.
#:
#: Empty since the Hacker News connector landed. Kept rather than deleted
#: because the distinction it draws is the useful one: "we cannot search
#: this yet" and "we never will" set completely different expectations, and
#: the next connector will want to sit here while it is being written.
COMING_SOON: set[str] = set()


class Platform(BaseModel):
    key: str
    name: str
    why: str = ""
    what_to_do: str = ""
    tone: str = ""
    search_terms: list[str] = Field(default_factory=list)
    target_places: list[str] = Field(default_factory=list)

    #: The same terms, grouped by which problem they are looking for.
    #:
    #: `search_terms` stays the flat list every existing caller reads, and is
    #: derived from this. Nothing is dropped to build it: the grouping exists
    #: to *create* coverage by asking for a term per problem, not to enforce
    #: spread by deleting terms - which was tried, and starved both the search
    #: and the repository discovery that counts hits from these same terms.
    #:
    #: Empty when the model returned a flat list, so an older plan still runs.
    term_groups: dict[str, list[str]] = Field(default_factory=dict)

    # Set by us, never by the model.
    searchable: bool = False
    available_now: bool = False


class MarketingPlan(BaseModel):
    strategy: str = ""
    audience: str = ""
    positioning: str = ""
    platforms: list[Platform] = Field(default_factory=list)
    content_ideas: list[str] = Field(default_factory=list)
    first_week: list[str] = Field(default_factory=list)

    competitors: list[str] = Field(default_factory=list)
    """
    Competing products, by name. Resolved to their repositories separately.

    A second source beside the profile's list, because that one can only
    report what the product's own website happens to mention - and a website
    naming two rivals while the field contains a dozen is normal, not a bug.
    One real product listed Haystack and GPTCache on its pages while mem0 and
    cognee, its closest neighbours, appeared nowhere and were never searched.

    Names only. Turning a name into a repository is a lookup, and a lookup
    beats recall every time.
    """

    @property
    def actionable(self) -> list[Platform]:
        """Searchable today. The centre of the dashboard."""
        return [p for p in self.platforms if p.available_now]

    @property
    def coming_soon(self) -> list[Platform]:
        """We will be able to search these; the connector is not built yet."""
        return [p for p in self.platforms if p.searchable and not p.available_now]

    @property
    def advice_only(self) -> list[Platform]:
        """
        We can never search these - Twitter, LinkedIn, Discord.

        Kept separate from `coming_soon` on purpose. "Not yet" and "not ever"
        set completely different expectations, and collapsing them means a
        user waits for posts that are never going to appear.
        """
        return [p for p in self.platforms if not p.searchable]


def source_hash(profile: dict | None, description: str, goal: str) -> str:
    """
    What the plan was built from.

    Changing the goal should produce a new plan; re-crawling a site that did
    not change should not. Both fall out of hashing the three inputs.

    `PROMPT_VERSION` is in here as well, and has to be. Without it a change
    to the prompt only reaches products created afterwards: every existing
    plan keeps its stored hash, looks fresh forever, and quietly goes on
    using terms written against a rubric that no longer exists. Bumping the
    version is then the one action that makes a prompt change take effect.
    """
    material = json.dumps(
        {
            "profile": profile or {},
            "description": description or "",
            "goal": goal or "",
            "prompt": PROMPT_VERSION,
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def make_plan(
    *,
    name: str,
    url: str,
    description: str,
    goal: str,
    profile: dict | None,
) -> MarketingPlan | None:
    """
    Write the plan. None if it cannot be done.

    Never raises. A product without a plan still works - the user can search
    manually, as they did before this existed.
    """
    if not settings.openai_api_key:
        return None

    profile_text = _profile_text(profile)
    if not (description or goal or profile_text):
        return None

    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
            name=name or "(unnamed)",
            url=url or "(none)",
            description=description or "(not given)",
            goal=goal or "(not given)",
            profile=profile_text or "(the website could not be read)",
        )
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                CHAT_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.planner_model,
                    "messages": [{"role": "user", "content": prompt}],
                    # A little warmth: a plan is writing, not classification,
                    # and at zero it produces the same four bland platforms
                    # for every product.
                    "temperature": 0.5,
                    "response_format": {"type": "json_object"},
                },
            )
            if response.status_code != 200:
                log.warning("planner.failed", status=response.status_code,
                            body=response.text[:200])
                return None

            reply = response.json()
            usage.record("plan", settings.planner_model, reply)

            payload = json.loads(reply["choices"][0]["message"]["content"])
            plan = MarketingPlan(**payload)
    except Exception as exc:
        log.warning("planner.failed", error=str(exc))
        return None

    _mark_platforms(plan)

    log.info(
        "planner.made",
        platforms=len(plan.platforms),
        actionable=len(plan.actionable),
    )
    return plan


#: Most terms a single platform may keep.
MAX_TERMS = 12


def _usable_terms(terms: list[str]) -> list[str]:
    """
    Drop the search terms that cannot work, keep the rest in the model's order.

    Two shapes are allowed, and they fail in opposite directions:

        prompt caching        an exact phrase, 1-3 words
        prompt caching + RAG  an intersection, 1-3 words a side

    A plain phrase longer than three words is sentence-shaped, and a sentence
    is searched as an exact string that nobody has ever typed twice. It
    matches nothing at all.

    An intersection is the narrowing tool, so its sides are allowed to be
    single words: `cache + retrieval` is precise because both must appear,
    where `cache` alone matches tens of thousands and is a lottery. More than
    two sides is not narrower in any useful way, just empty.

    ── Terms are NOT capped per concept, and that was tried ──────────────

    A previous version dropped terms once four of them shared a concept, to
    stop a plan spending every slot on the product's catchiest phrase. It
    was wrong, and expensively so: it cut a run from 140 classified posts to
    10 overnight.

    The reasoning was backwards. A cap cannot create coverage that does not
    exist - if a product genuinely is about one thing, capping does not
    produce terms for the other things, it just deletes two thirds of the
    good ones. And it starved twice over, because repository discovery
    counts hits from these same terms, so fewer terms meant fewer terms
    *and* fewer repositories.

    Terms clustering on one concept is not a bug to correct here. It is the
    planner reporting what the product is about, and when that concept is
    where the market turns out to be, every one of those terms earns its
    place. Breadth belongs in the product description, which is a decision
    for a person, not in a filter that silently throws work away.
    """
    kept: list[str] = []
    seen: set[str] = set()

    for term in terms:
        clean = _clean_term(term)
        if clean is None or clean.lower() in seen:
            continue

        seen.add(clean.lower())
        kept.append(clean)

        if len(kept) >= MAX_TERMS:
            break

    return kept


#: Words too broad to be half of an intersection.
#:
#: `prompt caching + RAG` narrows because both halves name something. `data
#: updates + AI` does not, because `AI` appears in most of the corpus and
#: matching on it excludes nothing - the term is a single phrase wearing a
#: `+`, and it comes back with hundreds of posts about nothing in particular.
#:
#: Two prompt revisions asked for this and two plans ignored it, which is the
#: usual sign that a rule belongs in code. The broad side is stripped rather
#: than the whole term dropped: `response time + AI` still has a real concept
#: in it, and `response time` is a term worth running.
BROAD_SIDES = frozenset(
    {
        "ai", "llm", "llms", "ml", "model", "models", "data", "software",
        "app", "apps", "system", "systems", "tool", "tools", "code",
        "agent", "agents", "api", "apis", "user", "users", "product",
    }
)


def _clean_term(term: str) -> str | None:
    """
    One term normalised, or None when its shape cannot match anything.

    Split out of `_usable_terms` so the grouped path applies exactly the same
    rules. A badly shaped term fails identically whether or not it arrived
    inside a branch, and two copies of these rules would drift the first time
    one of them was tuned.
    """
    if not term or not str(term).strip():
        return None

    sides = [" ".join(s.split()) for s in str(term).split(gh_syntax.INTERSECT)]
    sides = [s for s in sides if s]
    if not sides or len(sides) > 2:
        return None

    # Drop a side that narrows nothing, keeping whatever real concept the
    # term had. Only when there is another side to fall back on - a bare
    # `AI` with nothing beside it fails the length rule below anyway.
    if len(sides) == 2:
        useful = [s for s in sides if s.lower() not in BROAD_SIDES]
        # Both halves broad means the term narrows nothing at all, and
        # keeping either one would leave a single word that matches the
        # whole corpus. `AI + LLM` is not a search.
        if not useful:
            return None
        sides = useful
    if any(len(s.split()) > 3 for s in sides):
        return None
    # A single side must still carry enough to be a phrase rather than a
    # dragnet; two sides earn the right to be short by intersecting.
    if len(sides) == 1 and len(sides[0].split()) < 2:
        return None

    return f" {gh_syntax.INTERSECT} ".join(sides)


#: Problems a plan may name. More than this and each one gets too little
#: search budget to prove anything either way.
MAX_BRANCHES = 6

#: Terms per problem. This is a *quota*, not a cap on the plan: every branch
#: is entitled to this many, and a branch using fewer does not hand its share
#: to a louder one. That asymmetry is the whole point - the failure being
#: fixed is one problem taking every slot while the rest of the product goes
#: unsearched.
MAX_TERMS_PER_BRANCH = 4

#: Ceiling on the flattened list. Higher than `MAX_TERMS` because a grouped
#: plan is deliberately broader: six problems at four terms each is more
#: queries than one problem ever justified, and the request budget scales
#: with the query count rather than being fixed.
MAX_GROUPED_TERMS = 20


def _usable_groups(groups: dict[str, list[str]]) -> dict[str, list[str]]:
    """
    Validate an ontology, keeping every branch that has a usable term.

    Each term goes through exactly the same shape rules as `_usable_terms` -
    a phrase of 2-3 words, or an intersection of two 1-3 word sides - because
    a badly shaped term fails identically whether or not it is in a branch.

    What this deliberately does *not* do is drop a term for resembling
    another. Terms clustering on one idea is the planner reporting what the
    product is about, and deleting the surplus creates no coverage for the
    problems it skipped. Coverage comes from asking for a branch per problem,
    which is what the prompt now does.
    """
    kept: dict[str, list[str]] = {}
    seen: set[str] = set()
    total = 0

    for raw_name, terms in groups.items():
        name = " ".join(str(raw_name).split())[:40]
        if not name or not isinstance(terms, list):
            continue

        branch: list[str] = []
        for term in terms:
            if total >= MAX_GROUPED_TERMS:
                break
            clean = _clean_term(term)
            # Deduped across the whole ontology, not per branch: the same
            # query run twice costs a request and returns the same page.
            if clean is None or clean.lower() in seen:
                continue
            seen.add(clean.lower())
            branch.append(clean)
            total += 1
            if len(branch) >= MAX_TERMS_PER_BRANCH:
                break

        if branch:
            kept[name] = branch
        if len(kept) >= MAX_BRANCHES or total >= MAX_GROUPED_TERMS:
            break

    return kept


def _interleave(groups: dict[str, list[str]]) -> list[str]:
    """
    Flatten the ontology round robin: every branch's first term, then every
    branch's second, and so on.

    The order is the budget allocation, and this is the whole mechanism.
    `github.search` pages its queries round robin and stops dead when the
    request budget runs out, so whatever sits at the end of this list is what
    gets dropped when the run is short. Concatenating the branches would put
    the last branch there every single time - it would be in the plan, appear
    in the UI, and never actually run.

    Interleaved, a short run loses each branch's *weakest* term rather than
    one branch entirely. Coverage degrades evenly instead of alphabetically.
    """
    out: list[str] = []
    for position in range(MAX_TERMS_PER_BRANCH):
        for terms in groups.values():
            if position < len(terms):
                out.append(terms[position])
    return out


def branch_of(groups: dict[str, list[str]]) -> dict[str, str]:
    """Term -> the problem it belongs to, lowercased for lookup."""
    return {
        term.lower(): name for name, terms in groups.items() for term in terms
    }


def _mark_platforms(plan: MarketingPlan) -> None:
    """
    Decide what is actionable. Ours to say, not the model's.

    Also clears search terms on platforms we cannot search: a LinkedIn card
    showing search terms invites the user to expect posts that will never
    arrive.
    """
    for platform in plan.platforms:
        key = platform.key.strip().lower().replace(" ", "")
        platform.key = key
        platform.searchable = key in SEARCHABLE
        platform.available_now = platform.searchable and key not in COMING_SOON

        if not platform.searchable:
            platform.search_terms = []
            platform.target_places = []
            platform.term_groups = {}
            continue

        # An ontology wins when the model returned one, because the flat list
        # it also returns is the same terms in an order that loses a whole
        # branch the moment the run is short. Falling back keeps every plan
        # written before this existed runnable, rather than silently empty.
        platform.term_groups = _usable_groups(platform.term_groups)
        if platform.term_groups:
            platform.search_terms = _interleave(platform.term_groups)
        else:
            platform.search_terms = _usable_terms(platform.search_terms)

        # Capped by the same number `ground_repos` uses. Two different caps
        # here silently compounded: the model's list was cut to 15 and then
        # to 12, so raising either one on its own changed nothing.
        platform.target_places = [
            p.strip() for p in platform.target_places if p.strip()
        ][:MAX_REPOS]

    # Best first, actionable ahead of advice, so the top of the dashboard is
    # always something the user can press a button on.
    plan.platforms.sort(key=lambda p: (not p.available_now, not p.searchable))


#: Below this, nobody is asking for help there, however famous it is.
MIN_OPEN_ISSUES = 20

#: Repositories a plan may sweep.
#:
#: Raised from 12, because sweeps are measurably the best source in the run:
#: 845 of 1,509 candidates came from repository sweeps and about 660 from
#: every search term put together. More repositories is the cheapest way to
#: find more, and the only way to find more *in large projects* - a phrase
#: search covers all of GitHub and drags in the long tail of tiny ones, while
#: a sweep goes exactly where it is pointed.
#:
#: It is not free. The request budget is `queries x 2` capped at 60, so twenty
#: repositories alongside twelve terms means every query gets roughly two
#: pages instead of two and a half. That is the right trade here: page one is
#: GitHub's own best-match ordering, and breadth across thirty-two queries
#: beats depth on twenty-four.
MAX_REPOS = 20

#: Slots kept for repositories found by counting hits, before the model's own
#: names may take any.
#:
#: Without a reservation the weaker source wins by arriving first: the prompt
#: asks for as many repository names as there are slots, the model supplies
#: them, and evidence-based discovery is left with nowhere to put what it
#: found. Twelve of twenty means recall has to earn the rest.
HITS_RESERVED = 12

#: Slots kept for the issue trackers of competing products.
#:
#: A category nothing was looking for, and it shows: `mem0ai/mem0`,
#: `topoteretes/cognee` and `deepset-ai/haystack` score 0.39, 0.55 and 0.53
#: against one real product - above nearly every repository that did get
#: picked - and were still absent, because no step ever proposed them.
#:
#: They are missed because they are a different question. Hit-counting finds
#: where the *problem* is discussed, which is agent and tooling repositories.
#: A competitor's tracker is where people ask "does this handle X yet?" and
#: "why is this so slow on large corpora" - somebody already shopping in this
#: category, describing the gap in their current tool. That is a lead the
#: problem search cannot reach.
COMPETITOR_SLOTS = 4

#: How close a repository's description has to be to the product, by meaning.
#: Tuned against a real case: LangChain and Dify sit above it, TiDB and
#: OceanBase - SQL databases that grew vector columns - sit below.
MIN_SIMILARITY = 0.30

#: Returned instead of a similarity when the comparison could not be made.
#:
#: `_by_relevance` used to answer 1.0 - a perfect match - when the embedding
#: call failed or there was no product text to compare against. Every caller
#: then read "1.0" as "checked, and ideal", so one transient API error
#: silently switched the entire relevance filter off and let every candidate
#: through. It is how `wmww/Pinecone` (an unmaintained programming language,
#: 0.27) and `elastic/elasticsearch` (0.26) reached a plan whose gate they
#: both fail.
#:
#: A distinct value instead, because the two outcomes need opposite
#: treatment. "Scored badly" is a reason to drop a repository; "could not be
#: scored" is not - a network blip should not empty the plan - so these are
#: kept, and the run says so rather than passing them off as verified.
UNCHECKED = -1.0


def _passes(similarity: float) -> bool:
    """Keep this candidate? Unscored ones survive; badly-scored ones do not."""
    return similarity == UNCHECKED or similarity >= MIN_SIMILARITY


def _slug(text: str) -> str:
    """Letters and digits only, lowercased: "Lang-Fuse" and "langfuse" match."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def drop_own_repos(plan: MarketingPlan, name: str, url: str) -> list[str]:
    """
    Take the product's own repositories out of the places to search.

    Seen on a real run: the best result of the search was a discussion in the
    product's own repository. It scored well for the obvious reason - it is
    exactly about this product - and it is not a lead, because everybody
    writing there already uses it. Every way a repository gets into the plan
    favours this one: it matches the product's description better than any
    other, and its tracker is full of the product's own words.

    Returns notes saying what went, for the same reason `ground_repos` does.
    """
    own = own_names(name, url)

    notes: list[str] = []
    for platform in plan.platforms:
        if platform.key != "github":
            continue
        kept: list[str] = []
        for repo in platform.target_places:
            if is_own_repo(repo, own):
                notes.append(f"skipped {repo} - it is this product's own repository")
            else:
                kept.append(repo)
        platform.target_places = kept
    return notes


def own_names(name: str, url: str) -> set[str]:
    """The names a product goes by: its own, and the one in its web address."""
    own = {_slug(name)}
    host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    labels = [part for part in host.lower().split(".") if part and part != "www"]
    if len(labels) >= 2:
        own.add(_slug(labels[-2]))
    own.discard("")
    return own


def is_own_repo(repo: str | None, own: set[str]) -> bool:
    """
    Is "owner/name" the product's own repository?

    Yes when the owner or the name is one of the product's names. A
    repository that only mentions it - "awesome-acme" - is somebody else's.
    """
    if not repo or "/" not in repo or not own:
        return False
    owner, _, repo_name = repo.partition("/")
    return _slug(owner) in own or _slug(repo_name) in own


async def ground_repos(
    plan: MarketingPlan,
    queries: list[str],
    product_text: str = "",
    competitors: list[str] | None = None,
) -> list[str]:
    """
    Replace remembered repository names with ones GitHub actually has.

    The model names these from training data, which fails three ways at once,
    and one plan managed all three: `microsoft/DeepSpeed` had moved
    organisation, `haystack-ai/haystack` never existed, and
    `facebookresearch/detectron2` is real, popular, and about object
    detection. Recall is the wrong tool for a question with a live answer.

    So: check what it suggested, follow renames, drop the dead ones, then find
    the repositories where this problem is actually discussed and add what is
    missing. Returns notes describing what changed, because silently
    rewriting the agent's plan would be worse than the bad names.
    """
    github_platform = next(
        (p for p in plan.platforms if p.key == "github"), None
    )
    if github_platform is None:
        return []

    from outreach.connectors import github as gh

    notes: list[str] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        good: list[str] = []
        if github_platform.target_places:
            good, problems = await gh.check_repos(client, github_platform.target_places)
            notes.extend(problems)

    # Check the model's own names for relevance, not just the discovered ones.
    #
    # This used to be the one source that got waved through, which had it
    # exactly backwards: recall is the *least* reliable evidence here and was
    # the only kind going unexamined. It showed. One real plan came back with
    # `google-research/bert`, `tensorspace-team/tensorspace`, `apache/spark`
    # and `openai/gpt-3` - famous machine-learning repositories from years
    # ago, one of them an archived paper with no issue tracker at all, none of
    # them anywhere near a conversation about context caching.
    #
    # They are recalled because they are famous, and fame is not relevance.
    recalled: list[str] = []
    unchecked = False
    if good:
        async with httpx.AsyncClient(timeout=30.0) as client:
            described = await gh.repo_descriptions(client, good)
        ranked = await _by_relevance(
            [
                {"full_name": name, "description": described.get(name, ""),
                 "open_issues": 0}
                for name in good
            ],
            product_text,
        )
        for info, similarity in ranked:
            if similarity == UNCHECKED:
                unchecked = True
            elif not _passes(similarity):
                notes.append(
                    f"skipped {info['full_name']} - named from memory, but the "
                    f"project is about something else ({similarity:.2f})"
                )
                continue
            recalled.append(info["full_name"])

        if unchecked:
            # Loud, because the visible symptom is junk repositories with no
            # explanation next to them - which reads as a bad filter rather
            # than an absent one.
            notes.append(
                "could not compare repositories to the product, so none were "
                "filtered on relevance - anything unrelated in this list got "
                "in that way"
            )

    # Evidence gets first refusal on the slots.
    #
    # Ordering used to be the whole problem. The model's names were taken in
    # full up front, and since the prompt asks for as many as there are slots,
    # they filled every one - so the hit-counting below found its repositories,
    # checked them, and then broke out of the loop on the first iteration
    # because there was nowhere left to put them. The better source was dead
    # code whenever the weaker one did its job.
    #
    # Now the recalled names are held back to whatever the evidence does not
    # use, and get to fill the rest if it comes up short.
    seeded = recalled[: max(0, MAX_REPOS - HITS_RESERVED)]
    spare = recalled[len(seeded):]

    github_platform.target_places = list(seeded)
    have = {r.lower() for r in seeded}

    # Evidence: search for the problem and see whose repository the posts came
    # from. A repository that produced five posts about this in six months has
    # proved it belongs here, and nothing had to be inferred from a
    # description.
    try:
        by_hits = await gh.repos_by_hits(
            github_platform.search_terms, days=180, limit=MAX_REPOS
        )
    except Exception as exc:
        log.warning("planner.hit_discovery_failed", error=str(exc))
        by_hits = []

    # Hits are evidence of a conversation, not evidence of the right one.
    #
    # This path used to add whatever turned up, and it filled slots with
    # `jaegertracing/jaeger` and an F# version control system - projects whose
    # issues genuinely do contain the words "cache" and "latency", because
    # every system has caches. Two posts is a coincidence, not a market.
    #
    # So hits are now checked against the product the same way the
    # description path already was. Sweeping a wrong repository is no longer
    # cheap: at twenty repositories the sweeps are most of the request budget,
    # and one irrelevant name spends two pages finding nothing.
    if by_hits:
        async with httpx.AsyncClient(timeout=30.0) as client:
            described = await gh.repo_descriptions(
                client, [repo for repo, _ in by_hits]
            )
        checked = await _by_relevance(
            [
                {
                    "full_name": repo,
                    "description": described.get(repo, ""),
                    "open_issues": hits,
                }
                for repo, hits in by_hits
            ],
            product_text,
        )
        # Leave room for the competitor trackers below. They answer a
        # different question and would otherwise be squeezed out by whichever
        # source happened to run first - which is the exact bug that made
        # hit-counting dead code in the first place.
        hits_ceiling = MAX_REPOS - (COMPETITOR_SLOTS if competitors else 0)

        for info, similarity in checked:
            if len(github_platform.target_places) >= hits_ceiling:
                break
            repo = info["full_name"]
            if repo.lower() in have:
                continue
            if not _passes(similarity):
                notes.append(
                    f"skipped {repo} - posts matched, but the project is about "
                    f"something else ({similarity:.2f})"
                )
                continue
            have.add(repo.lower())
            github_platform.target_places.append(repo)
            notes.append(
                f"added {repo} ({info['open_issues']} posts about this problem)"
            )

    # The competing products themselves.
    #
    # Looked up by name rather than recalled, because recall is what left
    # these out: the model named them on one run and forgot them on the next,
    # and nothing else was asking. The profile already reads them off the
    # product's own website - they were simply never used for anything except
    # a line in the planner's prompt.
    # Both sources, the website's first: it reports what this product says
    # about itself, where the plan's list is the model's read of the field.
    rivals: list[str] = []
    for name in [*(competitors or []), *plan.competitors]:
        clean = " ".join(str(name).split())
        if clean and clean.lower() not in {r.lower() for r in rivals}:
            rivals.append(clean)

    # Resolve more names than there are slots, because some will not resolve
    # and some will be rejected below.
    resolved: list[dict] = []
    for name in rivals[: COMPETITOR_SLOTS * 2]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                matches = await gh.find_repo_candidates(client, name, min_stars=200)
        except Exception as exc:
            log.warning("planner.competitor_lookup_failed", name=name, error=str(exc))
            continue

        if not matches:
            notes.append(f"no repository found named {name}")
            continue

        resolved.extend(
            {**m, "competitor": name}
            for m in matches
            if m["full_name"].lower() not in have
        )

    # Competitors are relevance-checked like every other source.
    #
    # They used to be trusted on the strength of the name match alone, which
    # is how `wmww/Pinecone` - "an unmaintained programming language" - and
    # `matrix-org/pinecone` - a peer-to-peer network router - both ended up
    # being swept for a context-caching product. The name was right and
    # nothing else was.
    #
    # A name is evidence about identity, never about subject. Checking the
    # description costs nothing here and is the only thing that separates the
    # product from something that merely shares its word.
    if resolved:
        checked = await _by_relevance(resolved, product_text)
        # One repository per competitor. Several of an organisation's repos
        # can pass - Pinecone alone offers a RAG framework, a Python SDK and
        # a folder of notebooks - and sweeping all of them spends the whole
        # competitor allowance on a single rival.
        taken: set[str] = set()

        for info, similarity in checked:
            if len(github_platform.target_places) >= MAX_REPOS:
                break
            repo = info["full_name"]
            rival = info["competitor"]
            if repo.lower() in have or rival.lower() in taken:
                continue
            if not _passes(similarity):
                notes.append(
                    f"skipped {repo} - named as {rival}, but that project is "
                    f"about something else ({similarity:.2f})"
                )
                continue
            have.add(repo.lower())
            taken.add(rival.lower())
            github_platform.target_places.append(repo)
            notes.append(
                f"added {repo} (tracker for {rival}, a competing product, "
                f"{info['open_issues']:,} open issues)"
            )

    # Give the held-back names their slots if the evidence came up short.
    for repo in spare:
        if len(github_platform.target_places) >= MAX_REPOS:
            break
        if repo.lower() in have:
            continue
        have.add(repo.lower())
        github_platform.target_places.append(repo)

    if len(github_platform.target_places) >= MAX_REPOS:
        return notes

    # Only then fall back to asking GitHub which repositories *describe*
    # themselves this way, to fill any space left. Weaker evidence - a
    # description says what a project is, not that anybody there has this
    # problem - so it goes second and takes what is left.
    async with httpx.AsyncClient(timeout=30.0) as client:
        found: dict[str, dict] = {}
        for query in [q for q in queries if q.strip()][:4]:
            try:
                for repo_info in await gh.find_repos(
                    client, query, min_stars=500, limit=10
                ):
                    found.setdefault(repo_info["full_name"], repo_info)
            except Exception as exc:
                log.warning("planner.repo_discovery_failed", query=query, error=str(exc))

    # Nobody asking for help means nothing to find, whatever the star count.
    candidates = [
        r
        for r in found.values()
        if r["full_name"].lower() not in have and r["open_issues"] >= MIN_OPEN_ISSUES
    ]
    if not candidates:
        return notes

    # Judge relevance by what the repository is *about*, not how big it is.
    #
    # Size is a tempting filter and a wrong one: it drops LangChain and Dify,
    # which are exactly where these users are, while keeping TiDB and
    # OceanBase, which are SQL databases that grew a vector column. Comparing
    # the description to the product separates them properly.
    scored = await _by_relevance(candidates, product_text)

    for repo, similarity in scored:
        if len(github_platform.target_places) >= MAX_REPOS:
            break
        if not _passes(similarity):
            notes.append(
                f"skipped {repo['full_name']} - about something else "
                f"({similarity:.2f})"
            )
            continue

        github_platform.target_places.append(repo["full_name"])
        notes.append(
            f"added {repo['full_name']} ({repo['open_issues']:,} open issues, "
            f"match {similarity:.2f})"
        )

    return notes


async def _by_relevance(
    candidates: list[dict], product_text: str
) -> list[tuple[dict, float]]:
    """
    Sort repositories by how close their description is to the product.

    Falls back to open-issue count when there is nothing to compare against
    or the embedding fails. A worse ordering is survivable; refusing to
    suggest anything is not.
    """
    if not product_text.strip():
        return [
            (r, UNCHECKED) for r in sorted(candidates, key=lambda r: -r["open_issues"])
        ]

    from outreach import rank

    texts = [product_text] + [
        f"{r['full_name']}. {r['description']}" for r in candidates
    ]
    try:
        vectors = await rank.embed(texts)
    except Exception as exc:
        log.warning("planner.repo_ranking_failed", error=str(exc))
        return [
            (r, UNCHECKED) for r in sorted(candidates, key=lambda r: -r["open_issues"])
        ]

    product_vector, repo_vectors = vectors[0], vectors[1:]
    scored = [
        (repo, rank.cosine(product_vector, vector))
        for repo, vector in zip(candidates, repo_vectors, strict=True)
    ]
    return sorted(scored, key=lambda pair: -pair[1])


def _profile_text(profile: dict | None) -> str:
    """The extracted profile, flattened for the prompt."""
    if not profile:
        return ""

    lines: list[str] = []
    if profile.get("domain"):
        lines.append(f"Domain: {profile['domain']}")
    if profile.get("summary"):
        lines.append(f"Summary: {profile['summary']}")
    if profile.get("problems"):
        lines.append("Problems it solves: " + "; ".join(profile["problems"]))
    if profile.get("pain_words"):
        lines.append("How users describe the problem: " + ", ".join(profile["pain_words"]))
    if profile.get("competitors"):
        lines.append("Competitors: " + ", ".join(profile["competitors"]))
    if profile.get("buyer"):
        lines.append(f"Buyer: {profile['buyer']}")
    return "\n".join(lines)
