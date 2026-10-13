"""
Where candidates and labels live.

Two files, both plain JSON so they can be read, edited and diffed by hand.

  candidates.json   every unique result any search has returned
  labels.json       your judgement of which ones are actually leads

Candidates accumulate automatically as you search. Labels are yours and are
never written by code - that is the whole point of them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DIR = Path(__file__).parent / "data"
CANDIDATES = DIR / "candidates.json"
LABELS = DIR / "labels.json"

#: What the labels mean. Deliberately three, not five: the difference between
#: "no" and "definitely no" changes nothing you would do, and every extra
#: grade is another judgement you have to make consistently at 11pm.
MEANING = {
    0: "not a lead  - wrong domain, building it, or nothing to sell to",
    1: "maybe       - real person, real problem, but weak fit or not asking",
    2: "lead        - would actually reply to this one",
}


def _read(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def load_candidates() -> dict[str, dict]:
    return _read(CANDIDATES)


def load_labels() -> dict[str, dict]:
    return _read(LABELS)


def save_labels(labels: dict[str, dict]) -> None:
    _write(LABELS, labels)


def key(conversation: Any) -> str:
    """Stable identity for one result, across runs and prompt versions."""
    source = getattr(conversation, "source", None) or conversation["source"]
    source_id = getattr(conversation, "source_id", None) or conversation["source_id"]
    return f"{source}:{source_id}"


def capture(conversations: list[Any], product: str) -> int:
    """
    Add anything new to the candidate pool. Returns how many were new.

    Called from the search endpoint, so the pool builds up as a side effect of
    ordinary use rather than needing a separate collection exercise. Existing
    entries are never overwritten: the first time we saw something is the
    honest record, and re-running with a better prompt should not quietly
    rewrite history.
    """
    pool = load_candidates()
    added = 0

    for conversation in conversations:
        k = key(conversation)
        if k in pool:
            continue
        data = conversation.model_dump(mode="json")
        data["_product"] = product
        pool[k] = data
        added += 1

    if added:
        _write(CANDIDATES, pool)
    return added
