"""
Collapse the same post appearing twice.

Exact-id dedup already happens inside each connector, and it is not enough.
What survives it is the same *content* under two different ids:

  * somebody files the same request twice, days apart, after the first one
    got no reply - which is common enough that a real run had one at
    position four and five of page one, identical title, identical author,
    identical quote.
  * somebody opens an issue and a discussion for the same thing, and those
    live in different id spaces entirely.
  * a maintainer converts an issue into a discussion, leaving both.

Every one of those costs a classification call, a slot in the top N, and -
worst - looks careless on a page somebody is about to act on. You only want
to reply once.
"""

from __future__ import annotations

import re

import structlog

from outreach.schemas.conversation import Conversation

log = structlog.get_logger(__name__)

_NOISE = re.compile(r"[^a-z0-9 ]+")

#: Prefixes people put on titles that say nothing about the subject. Two
#: posts differing only by "[Bug]" and "[Feature]" are still the same post.
_TAGS = re.compile(
    r"^\s*(\[[^\]]{0,30}\]"
    r"|\([^)]{0,30}\)"
    r"|(feat|fix|bug|feature|request|question|rfc)\s*[:\-])\s*",
    re.I,
)


def normalise(title: str) -> str:
    """
    A title reduced to what it is about.

    Strips leading tags, punctuation and case, then collapses whitespace.
    Everything here is deliberately conservative - it should only ever merge
    posts a person would agree are the same one, because merging two
    different posts silently loses a lead, which is worse than showing a
    duplicate.
    """
    text = title or ""
    # Twice: "[Bug] [P1] title" is two tags deep and not unusual.
    for _ in range(2):
        text = _TAGS.sub("", text)
    text = _NOISE.sub(" ", text.lower())
    return " ".join(text.split())


def _attention(conversation: Conversation) -> int:
    """Which copy to keep: the one people actually engaged with."""
    return conversation.comments * 2 + conversation.score


def collapse(conversations: list[Conversation]) -> tuple[list[Conversation], int]:
    """
    Merge near-duplicates. Returns (kept, how many went).

    Keyed on author plus normalised title, which is the pattern that actually
    occurs - the same person posting the same thing more than once. Two
    different people writing the same title are usually writing about
    genuinely different things, so they are left alone.

    Order is preserved, and where copies differ the most engaged one wins:
    a thread with five replies is a better place to arrive than the identical
    thread with none.
    """
    best: dict[tuple[str, str], int] = {}
    kept: list[Conversation] = []
    dropped = 0

    for conversation in conversations:
        title = normalise(conversation.title or "")

        # Nothing to compare on. Keep it rather than guess - an untitled post
        # is rare, and merging every one of them together would be a bug
        # that looks exactly like a filter.
        if not title or not conversation.author:
            kept.append(conversation)
            continue

        key = (conversation.author.lower(), title)
        seen_at = best.get(key)

        if seen_at is None:
            best[key] = len(kept)
            kept.append(conversation)
            continue

        dropped += 1
        if _attention(conversation) > _attention(kept[seen_at]):
            kept[seen_at] = conversation

    if dropped:
        log.info("dedupe.collapsed", dropped=dropped, kept=len(kept))

    return kept, dropped
