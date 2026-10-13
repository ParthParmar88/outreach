"""
Suggest search keywords from what the user typed.

Replaces a checked-in list. A hardcoded set of keywords is correct for
exactly one product and quietly wrong for every other one - and worse, it
looks helpful while pointing the search somewhere the user never asked about.

One LLM call, cached on the description, so typing does not spend money on
every keystroke.
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
PROMPT_PATH = Path(__file__).parent / "llm" / "prompts" / "keywords.v1.md"
PROMPT_VERSION = "keywords.v1"
CACHE_PATH = Path(__file__).resolve().parents[3] / ".cache" / "keywords.json"

#: Below this there is not enough to suggest from, and asking anyway just
#: returns generic noise.
MIN_DESCRIPTION = 25


def _cache() -> dict[str, list[str]]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(cache: dict[str, list[str]]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    except OSError as exc:
        log.warning("keywords.cache_write_failed", error=str(exc))


async def suggest(description: str) -> list[str]:
    """
    Keywords for this description. Empty list when we cannot help.

    Never raises. An autocomplete that fails should offer nothing and let the
    user type, not break the form they are filling in.
    """
    description = " ".join(description.split())
    if len(description) < MIN_DESCRIPTION or not settings.openai_api_key:
        return []

    key = hashlib.sha256(
        f"{description}\x00{PROMPT_VERSION}\x00{settings.llm_model}".encode()
    ).hexdigest()[:32]

    cache = _cache()
    if key in cache:
        return cache[key]

    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").format(description=description)
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
                log.warning("keywords.failed", status=response.status_code)
                return []

            payload = json.loads(response.json()["choices"][0]["message"]["content"])
            raw = payload.get("keywords") or []
    except Exception as exc:
        log.warning("keywords.failed", error=str(exc))
        return []

    # The model is told 1-3 words and mostly obeys. Enforcing it here means a
    # stray sentence cannot reach a query where it would match nothing.
    keywords = [
        " ".join(str(k).split())
        for k in raw
        if isinstance(k, str) and 0 < len(str(k).split()) <= 3
    ][:15]

    cache[key] = keywords
    _save(cache)
    return keywords
