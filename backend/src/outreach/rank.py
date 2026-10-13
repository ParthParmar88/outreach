"""
Rank conversations by what they mean, not which words they contain.

This is the step that separates the product from a keyword grep. "How to
upgrade the version" contains the word reindex and is worthless; "my bill
tripled because I re-embed the whole corpus nightly" contains none of our
keywords and is the lead. Only meaning tells them apart.

Everything here runs in memory. Embedding a few hundred results and sorting
them needs no database and no pgvector - that only matters later, when a
stored corpus of hundreds of thousands of documents has to be searched. Not
having built it yet is not a reason to wait.
"""

from __future__ import annotations

import math

import httpx
import structlog

from outreach import usage
from outreach.config import settings
from outreach.schemas.conversation import Conversation

log = structlog.get_logger(__name__)

EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"

#: Enough text to judge relevance. Issue bodies run to thousands of words of
#: stack traces and checklists, and none of it changes the topic.
MAX_CHARS = 2000

#: OpenAI accepts far more per request, but smaller batches fail smaller.
BATCH = 96


class RankError(Exception):
    """Something the user needs to know about, phrased for a person."""


def cosine(a: list[float], b: list[float]) -> float:
    """
    Similarity between two vectors, -1 to 1.

    Pure Python on purpose. A few hundred vectors takes milliseconds, and it
    saves adding numpy for one function.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts, in batches, preserving order."""
    if not settings.openai_api_key:
        raise RankError(
            "No OPENAI_API_KEY set in backend/.env, so results cannot be "
            "ranked by relevance."
        )

    vectors: list[list[float]] = []
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        for start in range(0, len(texts), BATCH):
            batch = [t[:MAX_CHARS] or " " for t in texts[start : start + BATCH]]
            response = await client.post(
                EMBEDDINGS_URL,
                headers=headers,
                json={"model": settings.embedding_model, "input": batch},
            )
            if response.status_code != 200:
                raise RankError(
                    f"OpenAI returned {response.status_code}: {response.text[:200]}"
                )
            payload = response.json()
            usage.record("rank", settings.embedding_model, payload)
            # The API may return out of order; `index` is authoritative.
            ordered = sorted(payload["data"], key=lambda d: d["index"])
            vectors.extend(item["embedding"] for item in ordered)

    return vectors


async def score_relevance(
    product: str,
    conversations: list[Conversation],
) -> list[Conversation]:
    """
    Attach a 0-1 relevance score to each conversation and sort by it.

    `product` is what we are looking for, in plain language: what the product
    does and which problems it solves. The better that text describes the
    *problem* rather than the product's features, the better this works -
    posts describe problems, not solutions.

    Scores are min-max scaled across the result set rather than used raw.
    Raw cosine over real text bunches into a narrow band - 0.72 to 0.83 is
    typical - which looks like "everything is equally relevant" to a human
    reading it. Scaling spreads the same ordering across 0 to 1. It is a
    display decision, not a ranking one: the order is identical either way.
    """
    if not conversations:
        return []

    texts = [product] + [c.text for c in conversations]
    vectors = await embed(texts)

    product_vector, doc_vectors = vectors[0], vectors[1:]
    raw = [cosine(product_vector, v) for v in doc_vectors]

    low, high = min(raw), max(raw)
    spread = high - low

    for conversation, score in zip(conversations, raw, strict=True):
        conversation.relevance = round((score - low) / spread if spread else 1.0, 4)
        conversation.relevance_raw = round(score, 4)

    log.info(
        "rank.scored",
        count=len(conversations),
        raw_low=round(low, 3),
        raw_high=round(high, 3),
    )

    return sorted(conversations, key=lambda c: c.relevance or 0.0, reverse=True)
