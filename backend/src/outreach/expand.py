"""
Step 1 of a run: turn the user's few keywords into a fuller search.

The user types four terms. Someone with the problem writes it in words the
user never considered - that gap is exactly what a keyword-only search loses,
and it is the reason this step exists.

The important part is not the expansion, it is that **the user sees it and
can delete any of it before anything runs**. Adding words silently means bad
results with no explanation, and the user blames the product rather than the
term that caused it. So every added term carries a reason written for a
person, and nothing executes until they have looked.

One LLM call, cached on the inputs, so re-opening a plan costs nothing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import structlog

from outreach.config import settings

log = structlog.get_logger(__name__)

CHAT_URL = "https://api.openai.com/v1/chat/completions"
PROMPT_PATH = Path(__file__).parent / "llm" / "prompts" / "expand.v1.md"
PROMPT_VERSION = "expand.v1"
CACHE_PATH = Path(__file__).resolve().parents[3] / ".cache" / "expand.json"

MIN_DESCRIPTION = 25
MAX_TERMS = 10


def _cache() -> dict[str, list[dict]]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(cache: dict[str, list[dict]]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    except OSError as exc:
        log.warning("expand.cache_write_failed", error=str(exc))


async def expand(description: str, keywords: list[str]) -> list[dict[str, str]]:
    """
    Extra terms, each with a reason. Returns [] when we cannot help.

    Never raises. A plan that compiles without expansion is a smaller search;
    a plan that fails to compile is a broken product.
    """
    description = " ".join(description.split())
    existing = [" ".join(k.split()) for k in keywords if k.strip()]

    if len(description) < MIN_DESCRIPTION or not settings.openai_api_key:
        return []

    key = hashlib.sha256(
        "\x00".join(
            [description, *sorted(existing), PROMPT_VERSION, settings.llm_model]
        ).encode()
    ).hexdigest()[:32]

    cache = _cache()
    if key in cache:
        return cache[key]

    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
            description=description,
            keywords="\n".join(f"- {k}" for k in existing) or "(none)",
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                CHAT_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                },
            )
            if response.status_code != 200:
                log.warning("expand.failed", status=response.status_code)
                return []
            payload = json.loads(response.json()["choices"][0]["message"]["content"])
            raw = payload.get("terms") or []
    except Exception as exc:
        log.warning("expand.failed", error=str(exc))
        return []

    terms = _clean(raw, existing)
    cache[key] = terms
    _save(cache)
    return terms


def _clean(raw: list, existing: list[str]) -> list[dict[str, str]]:
    """
    Enforce what the prompt asks for, because asking is not guaranteeing.

    Three rules, all of which the model breaks occasionally: no duplicates of
    what the user typed, nothing longer than three words, and nothing without
    a reason. A term with no reason cannot be judged by the user, which
    defeats the point of showing it to them.
    """
    seen = {k.lower() for k in existing}
    out: list[dict[str, str]] = []

    for item in raw:
        if not isinstance(item, dict):
            continue
        term = " ".join(str(item.get("term") or "").split())
        reason = " ".join(str(item.get("reason") or "").split())

        if not term or not reason:
            continue
        if len(term.split()) > 3:
            continue
        if term.lower() in seen:
            continue

        seen.add(term.lower())
        out.append({"term": term, "reason": reason})

    return out[:MAX_TERMS]
