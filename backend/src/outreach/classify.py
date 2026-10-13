"""
Stage 5: an LLM reads each post and says what the author is actually doing.

Embeddings got us the right topic. They cannot tell "I found this bug in our
code, here is the migration to fix it" from "my index is broken, what do people
do?" - those two sentences are semantically almost identical and commercially
opposite. That judgement is what this stage buys.

Only ever runs on the top N after ranking. Classifying everything fetched
would be five times the cost and latency for results nobody will see.

── The cache is the point ────────────────────────────────────────────────
Intent never changes. An issue classified today is classified correctly next
month, so the answer is stored against a hash of the post's own text plus the
prompt and model versions. Searches overlap heavily - same repositories,
similar phrases - so most classifications after the first few runs are free.
That is also why each post gets its own call rather than being batched: a
batch cannot be cached per document.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

import httpx
import structlog
from pydantic import BaseModel

from outreach import usage
from outreach.config import settings
from outreach.schemas.conversation import Conversation

log = structlog.get_logger(__name__)

CHAT_URL = "https://api.openai.com/v1/chat/completions"
PROMPT_PATH = Path(__file__).parent / "llm" / "prompts" / "classify.v1.md"
#: Part of the cache key. Bump it whenever the prompt changes, so old
#: judgements are discarded instead of silently reused against a new rubric.
PROMPT_VERSION = "classify.v5"

#: Enough of a post to judge intent. Bodies run to thousands of words of
#: stack traces; the first part carries the intent.
MAX_BODY_CHARS = 3000

#: OpenAI tolerates far more, but eight keeps one search inside a few seconds
#: without tripping rate limits.
CONCURRENCY = 8

CACHE_PATH = Path(__file__).resolve().parents[3] / ".cache" / "classify.json"


#: A categorical judgement mapped to a number, rather than asking the model
#: for a float directly. Models reach for round numbers - every result came
#: back 0.86, then every result came back 0.90 - and four named bands with
#: written definitions are something they judge reliably.
FIT_VALUE = {
    "strong": 0.90,
    "possible": 0.55,
    "weak": 0.20,
    "none": 0.0,
}

#: How much a domain mismatch costs.
#:
#: This was a hard gate - anything but an exact domain match scored zero -
#: and it was too blunt. The gate exists for a real reason: staleness,
#: invalidation and expensive rebuilds look identical in code indexers,
#: databases, search engines and CI caches, and structural similarity is not
#: a market. A C++ language server reindexing after a header change must not
#: score as a lead.
#:
#: But "different domain" was doing two jobs at once. A post about KV-cache
#: reuse in a local inference server is not the same domain as a context
#: cache for agents, and it is not a C++ language server either - it is the
#: next room over, full of exactly the right people. Zeroing both equally
#: threw away real leads to catch fake ones.
#:
#: Three levels rather than two, so `adjacent` survives at a penalty and
#: `different` still dies.
#: `adjacent` was 0.35 and that was still too harsh. Measured against a real
#: run: a strong fit in an adjacent domain came out at 0.32, which after the
#: rest of the arithmetic capped the best result on the page at 39 - below the
#: threshold where the UI stops calling it mediocre. The model was doing its
#: job and the number was throwing the answer away.
#:
#: 0.55 is set so that a `strong` fit one room over lands in the high band
#: rather than the middle of it, while `same` still clearly outranks it.
DOMAIN_MULTIPLIER = {
    "same": 1.00,
    "adjacent": 0.55,
    "different": 0.10,
}


class Analysis(BaseModel):
    intent: str = "IRRELEVANT"
    pain_point: str = ""
    evidence_quote: str = ""
    asking_for_help: bool = False
    #: The model names both domains in its own words before comparing them.
    #: Making it commit to a category is what stops "index staleness" reading
    #: as one domain when it spans five - it cannot write "C++ code indexing"
    #: and "LLM vector retrieval" and then call them the same thing.
    post_domain: str = ""
    product_domain: str = ""
    domain_match: str = "different"
    fit: str = "none"
    reason: str = ""

    @property
    def same_domain(self) -> bool:
        """Kept for display and for everything downstream that reads a bool."""
        return self.domain_match.lower().strip() == "same"

    @property
    def product_fit(self) -> float:
        """0-1, for scoring. Fit as judged, scaled by how close the domain is."""
        fit = FIT_VALUE.get(self.fit.lower().strip(), 0.0)
        domain = DOMAIN_MULTIPLIER.get(self.domain_match.lower().strip(), 0.10)
        return fit * domain


class ClassifyError(Exception):
    """Something the user needs to know about, phrased for a person."""


# ------------------------------------------------------- stage 4a: the gate


#: The vocabulary of the world this product lives in.
#:
#: Deliberately broad and deliberately not product-specific. This gate is not
#: trying to decide whether a post is a lead - that is two stages away and
#: costs money. It is throwing out the "bump eslint to 9.2" and "fix typo in
#: README" that a repository sweep returns by the hundred, because a sweep
#: takes *every* recent issue in a repository and most of what any repository
#: does is not about us.
#:
#: A narrow gate here would be the most expensive mistake available: it runs
#: before anything has been read, so whatever it drops is gone silently and
#: without appeal. Hence one shared word is enough.
DOMAIN_WORDS = frozenset(
    {
        "llm", "llms", "gpt", "claude", "openai", "anthropic", "gemini",
        "rag", "agent", "agents", "agentic", "prompt", "prompts",
        "embedding", "embeddings", "embed", "vector", "vectors",
        "retrieval", "retrieve", "index", "indexing", "reindex",
        "cache", "cached", "caching", "context", "token", "tokens",
        "chunk", "chunks", "chunking", "inference", "completion",
        "memory", "semantic", "corpus", "knowledge", "langchain",
        "llamaindex", "ollama", "vllm", "transformer", "transformers",
    }
)

_WORD = re.compile(r"[a-z0-9_]+")


def gate(
    conversations: list[Conversation], terms: list[str] | None = None
) -> tuple[list[Conversation], str]:
    """
    Drop posts with no vocabulary in common with us. Free, no API call.

    Returns what survived and a note describing what went.

    The plan's own search terms are folded in, so a product whose words are
    not in `DOMAIN_WORDS` still passes its own results through. A post fetched
    *by* a phrase always contains that phrase, so phrase results are never at
    risk here - this only ever bites repository sweeps, which is exactly where
    the junk is.
    """
    vocabulary = set(DOMAIN_WORDS)
    for term in terms or []:
        vocabulary.update(w for w in _WORD.findall(term.lower()) if len(w) >= 3)

    kept: list[Conversation] = []
    for conversation in conversations:
        words = set(_WORD.findall(conversation.text[:MAX_BODY_CHARS].lower()))
        if words & vocabulary:
            kept.append(conversation)

    dropped = len(conversations) - len(kept)
    note = (
        f"gate: dropped {dropped} with nothing in common with this product"
        if dropped
        else "gate: everything shared vocabulary with this product"
    )
    return kept, note


# ----------------------------------------------------- stage 4b: the triage


TRIAGE_PROMPT_PATH = Path(__file__).parent / "llm" / "prompts" / "triage.v1.md"
TRIAGE_VERSION = "triage.v4"
TRIAGE_CACHE_PATH = CACHE_PATH.parent / "triage.json"

#: Titles per request.
#:
#: ── Why this is not larger ───────────────────────────────────────────────
#:
#: It was 40, and at 40 the model stopped answering about most of them. One
#: measured batch of 40 real Hacker News titles came back with **nine**
#: scores, and every one of those nine was a 2 or a 3: it had returned the
#: titles it liked and silently dropped the ones it rejected, because the
#: instructions asked it to *filter* a list rather than score one.
#:
#: That is invisible from outside. The reply is valid JSON, the run finishes,
#: and every skipped title takes the default below - 83% of a real cache was
#: that default. What reaches the judge is then decided by embedding rank,
#: which is the one thing this stage exists to correct.
#:
#: Twenty titles, an explicit count in the prompt, and a re-ask for whatever
#: comes back missing. Roughly 1.5x the tokens of the old batch size, which is
#: still a fraction of a cent per run.
TRIAGE_BATCH = 20

#: Below this a title is not worth the full judge. 2 is "plausibly this
#: problem", and the whole design of the rubric is that an unsure title lands
#: there rather than at 1.
TRIAGE_KEEP_FROM = 2

#: What a title is worth when the model would not score it.
#:
#: Below `TRIAGE_KEEP_FROM`, and deliberately different from what a *failed
#: request* gets. The two look alike in the code and mean opposite things:
#:
#:   * the request failed - nothing was read, so its titles keep 2 and stay
#:     eligible. Punishing a post for a network error would be absurd.
#:   * the request succeeded and the model skipped this title twice, once in
#:     its batch and again when asked on its own. That is an answer: it read
#:     the title and declined to keep it.
#:
#: Scoring the second case 2 is what filled ten judge slots with chatter.
TRIAGE_UNSCORED = 1


async def triage(
    product: str,
    conversations: list[Conversation],
    keep: int,
) -> tuple[list[Conversation], list[str]]:
    """
    Read the titles cheaply, and return the `keep` best for the real judge.

    ── Why this exists ──────────────────────────────────────────────────────

    The stage it replaces sorted by embedding similarity and took the top N.
    Measured against six leads found by hand, that signal was flat: 0.287 to
    0.363 raw cosine across the best and worst of them, inside a band where
    several hundred generic posts also sit. Sorting by it and cutting at ten
    is close to sampling at random from the top of the topic.

    A model reading the title is not flat. It costs about a fifth of a cent
    for a thousand titles - roughly a twentieth of what judging a hundred
    posts costs - and it answers the question the embedding cannot: is
    something *happening* here, or does this merely share our words.

    Falls back to the incoming order on any failure. A worse ordering is
    survivable; refusing to return anything is not.
    """
    if not conversations:
        return [], []

    scores, hits, failures = await triage_scores(product, conversations)

    # Stable within a score: the incoming order is embedding rank, which is a
    # weak signal but not a worthless one, so it breaks ties.
    ordered = sorted(
        range(len(conversations)),
        key=lambda p: (-scores.get(p, TRIAGE_KEEP_FROM), p),
    )
    worth_reading = [p for p in ordered if scores.get(p, 0) >= TRIAGE_KEEP_FROM]

    chosen = worth_reading[:keep]

    # The distribution, not just the total. "1458 worth a closer look" out of
    # 1511 says the triage passed everything and the ordering did the work,
    # which is a different system from the one intended - and indistinguishable
    # from a healthy run if only the total is reported.
    spread = {s: 0 for s in (3, 2, 1, 0)}
    for position in range(len(conversations)):
        spread[scores.get(position, TRIAGE_KEEP_FROM)] += 1

    notes = [
        f"triage: read {len(conversations)} titles ({hits} from cache) - "
        f"{spread[3]} clear, {spread[2]} maybe, {spread[1]} adjacent, "
        f"{spread[0]} unrelated; judging the best {len(chosen)}"
    ]
    if failures:
        notes.append(f"triage: {failures} titles could not be scored and were kept")
    if spread[3] > keep:
        notes.append(
            f"triage: {spread[3] - keep} more scored a clear match but were cut "
            f"by the {keep} judge limit - raise CLASSIFY_TOP to read them"
        )

    return [conversations[p] for p in chosen], notes


async def triage_scores(
    product: str,
    conversations: list[Conversation],
) -> tuple[dict[int, int], int, int]:
    """
    Score every title 0-3, keyed by its position in `conversations`.

    Also returns how many came from the cache and how many could not be
    scored because their request failed.

    Separate from `triage` so the scores themselves can be looked at. `triage`
    only says which posts it kept, and the evaluation needs to know what a
    title was given, not just whether it happened to make the cut of ten.
    """
    if not settings.openai_api_key:
        raise ClassifyError("No OPENAI_API_KEY set in backend/.env.")

    cache = _load_json(TRIAGE_CACHE_PATH)
    scores: dict[int, int] = {}
    pending: list[int] = []

    for position, conversation in enumerate(conversations):
        key = _triage_key(conversation, product)
        if key in cache:
            scores[position] = int(cache[key])
        else:
            pending.append(position)

    hits = len(scores)
    failures = 0

    if pending:
        template = TRIAGE_PROMPT_PATH.read_text(encoding="utf-8")
        batches = [
            pending[i : i + TRIAGE_BATCH]
            for i in range(0, len(pending), TRIAGE_BATCH)
        ]
        semaphore = asyncio.Semaphore(CONCURRENCY)

        async with httpx.AsyncClient(timeout=60.0) as client:

            async def one(batch: list[int]) -> None:
                nonlocal failures
                async with semaphore:
                    try:
                        got = await _ask_triage(
                            client, template, product,
                            [conversations[p] for p in batch],
                        )
                    except Exception as exc:
                        failures += len(batch)
                        log.warning("triage.failed", error=str(exc))
                        # Unscored, not zero. A batch that failed says
                        # nothing about its titles, and scoring them 0 would
                        # silently delete forty posts on one bad response.
                        for position in batch:
                            scores[position] = TRIAGE_KEEP_FROM
                        return

                for offset, position in enumerate(batch):
                    # Missing after the re-ask is a judgement, not a gap.
                    score = got.get(offset, TRIAGE_UNSCORED)
                    scores[position] = score
                    cache[_triage_key(conversations[position], product)] = score

            await asyncio.gather(*(one(b) for b in batches))

        _save_json(TRIAGE_CACHE_PATH, cache)

    return scores, hits, failures


def _triage_key(conversation: Conversation, product: str) -> str:
    material = "\x00".join(
        [
            conversation.title or "",
            conversation.container or "",
            product,
            TRIAGE_VERSION,
            settings.llm_model,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


async def _ask_triage(
    client: httpx.AsyncClient,
    template: str,
    product: str,
    batch: list[Conversation],
) -> dict[int, int]:
    """
    One batch of titles to {offset: score}.

    Asks once for the whole batch, then once more for whatever came back
    missing. The second ask is cheap - it carries only the titles that were
    skipped - and it is what separates "the model rejected this" from "the
    model stopped halfway down the list", which a gap alone cannot say.
    """
    scores = await _score_titles(
        client, template, product, batch, list(range(len(batch)))
    )

    missing = [i for i in range(len(batch)) if i not in scores]
    if missing:
        log.info("triage.incomplete", asked=len(batch), answered=len(scores))
        scores.update(await _score_titles(client, template, product, batch, missing))

    return scores


async def _score_titles(
    client: httpx.AsyncClient,
    template: str,
    product: str,
    batch: list[Conversation],
    indices: list[int],
) -> dict[int, int]:
    """
    Score the titles at `indices`, keyed by those same indices.

    The numbering shown to the model is the caller's, not a fresh 0-based run
    over the subset, so a re-ask cannot come back mapped onto the wrong posts.
    """
    if not indices:
        return {}

    titles = "\n".join(
        f"{i}. [{batch[i].container or '?'}] {(batch[i].title or '(no title)')[:160]}"
        for i in indices
    )
    prompt = template.format(
        product=product.strip(), count=len(indices), titles=titles
    )

    response = await client.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={
            "model": settings.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
    )
    if response.status_code != 200:
        raise ClassifyError(
            f"OpenAI returned {response.status_code}: {response.text[:200]}"
        )

    reply = response.json()
    usage.record("triage", settings.llm_model, reply)

    payload = json.loads(reply["choices"][0]["message"]["content"])
    wanted = set(indices)
    out: dict[int, int] = {}
    for entry in payload.get("scores") or []:
        try:
            index = int(entry["i"])
            score = int(entry["s"])
        except (KeyError, TypeError, ValueError):
            continue
        # Only what was asked for. A model that invents an index it was never
        # shown must not get to score a post nobody put in front of it.
        if index in wanted:
            out[index] = max(0, min(3, score))
    return out


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError as exc:
        log.warning("cache.write_failed", path=str(path), error=str(exc))


# ---------------------------------------------------------------- the cache


def _load_cache() -> dict[str, dict]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict[str, dict]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    except OSError as exc:
        # A cache that cannot be written is a slower system, not a broken one.
        log.warning("classify.cache_write_failed", error=str(exc))


def _cache_key(conversation: Conversation, product: str) -> str:
    """
    Identity of one judgement.

    Everything that could change the answer goes in: the post, the product we
    are judging against, the prompt, and the model. Change any of them and the
    old answer is correctly discarded rather than silently reused.
    """
    material = "\x00".join(
        [
            conversation.text[:MAX_BODY_CHARS],
            product,
            PROMPT_VERSION,
            settings.llm_model,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------- the work


async def classify_all(
    product: str,
    conversations: list[Conversation],
) -> tuple[list[Conversation], list[str]]:
    """
    Classify each conversation, in parallel, using the cache where possible.

    Returns the conversations with their analysis attached, plus notes for
    the caller to surface.
    """
    if not conversations:
        return [], []
    if not settings.openai_api_key:
        raise ClassifyError("No OPENAI_API_KEY set in backend/.env.")

    prompt_template = _read_prompt()
    cache = _load_cache()
    semaphore = asyncio.Semaphore(CONCURRENCY)
    hits = 0
    failures = 0

    async with httpx.AsyncClient(timeout=60.0) as client:

        async def one(conversation: Conversation) -> None:
            nonlocal hits, failures
            key = _cache_key(conversation, product)

            if key in cache:
                hits += 1
                _attach(conversation, Analysis(**cache[key]))
                return

            async with semaphore:
                try:
                    analysis = await _ask(client, prompt_template, product, conversation)
                except Exception as exc:
                    failures += 1
                    log.warning("classify.failed", url=conversation.url, error=str(exc))
                    return

            cache[key] = analysis.model_dump()
            _attach(conversation, analysis)

        await asyncio.gather(*(one(c) for c in conversations))

    _save_cache(cache)

    notes = [f"classified {len(conversations)} ({hits} from cache)"]
    if failures:
        notes.append(f"{failures} could not be classified and were left unscored")

    return conversations, notes


async def _ask(
    client: httpx.AsyncClient,
    template: str,
    product: str,
    conversation: Conversation,
) -> Analysis:
    prompt = template.format(
        product=product.strip(),
        container=conversation.container or "unknown",
        title=conversation.title or "(no title)",
        body=conversation.body[:MAX_BODY_CHARS],
    )

    response = await client.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={
            "model": settings.llm_model,
            "messages": [{"role": "user", "content": prompt}],
            # Classification should be repeatable. The same post must not get
            # a different intent on a re-run.
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
    )
    if response.status_code != 200:
        raise ClassifyError(f"OpenAI returned {response.status_code}: {response.text[:200]}")

    reply = response.json()
    usage.record("judge", settings.llm_model, reply)

    content = reply["choices"][0]["message"]["content"]
    analysis = Analysis(**json.loads(content))

    # The quote must exist in the post. An invented quote is worse than no
    # quote: it is the one thing a user will check, and the one thing that
    # destroys trust in every other number if it turns out to be fabricated.
    if analysis.evidence_quote and not _quote_is_real(analysis.evidence_quote, conversation):
        log.info("classify.quote_not_found", url=conversation.url)
        analysis.evidence_quote = ""

    return analysis


def _quote_is_real(quote: str, conversation: Conversation) -> bool:
    """Substring check, ignoring whitespace and case differences only."""
    haystack = " ".join(conversation.text.split()).lower()
    needle = " ".join(quote.split()).lower()
    return needle in haystack


def _attach(conversation: Conversation, analysis: Analysis) -> None:
    conversation.intent = analysis.intent
    conversation.pain_point = analysis.pain_point or None
    conversation.evidence_quote = analysis.evidence_quote or None
    conversation.asking_for_help = analysis.asking_for_help
    conversation.post_domain = analysis.post_domain or None
    conversation.domain_match = analysis.domain_match
    conversation.same_domain = analysis.same_domain
    conversation.fit = analysis.fit
    conversation.product_fit = analysis.product_fit
    conversation.reason = analysis.reason or None


def _read_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise ClassifyError(f"Cannot read {PROMPT_PATH.name}: {exc}") from exc
