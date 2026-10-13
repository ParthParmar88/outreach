"""
Turn a crawled website into a product profile.

The crawler produces a large markdown document. Nothing could use it: the
search needs to know *what problem this product solves and in what words*,
and that is buried in fifty pages of prose. This is the step that reads it
once and writes down the answer.

Runs after a crawl finishes, keyed on the page content, so it only re-runs
when a re-crawl actually changed something.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import structlog
from pydantic import BaseModel, Field

from outreach.config import settings

log = structlog.get_logger(__name__)

CHAT_URL = "https://api.openai.com/v1/chat/completions"
PROMPT_PATH = Path(__file__).parent / "llm" / "prompts" / "profile.v1.md"
PROMPT_VERSION = "profile.v1"

#: Enough of the site to understand it. The whole document can be hundreds of
#: kilobytes, and the front pages carry the positioning.
MAX_CHARS = 24_000


class Profile(BaseModel):
    summary: str = ""
    domain: str = ""
    problems: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    pain_words: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    buyer: str = ""

    def as_search_text(self) -> str:
        """
        The profile as one paragraph, for embedding and for the classifier.

        Written the way a post would be written, not the way the website is.
        The pain words carry most of the weight here: they are the only part
        phrased the way somebody with the problem actually types.
        """
        parts = []
        if self.domain:
            parts.append(f"Domain: {self.domain}.")
        if self.summary:
            parts.append(self.summary)
        if self.problems:
            parts.append("Problems: " + "; ".join(self.problems) + ".")
        if self.pain_words:
            parts.append("People describe it as: " + ", ".join(self.pain_words) + ".")
        if self.buyer:
            parts.append(f"Who has this problem: {self.buyer}")
        return " ".join(parts)

    @property
    def is_usable(self) -> bool:
        """Enough to be worth using instead of what the user typed."""
        return bool(self.domain and (self.problems or self.pain_words))


async def extract(markdown: str) -> Profile | None:
    """
    Read the crawled site and return a profile. None if it cannot be done.

    Never raises. A product without a profile still works - the search falls
    back to the description the user typed.
    """
    if not markdown or not settings.openai_api_key:
        return None

    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
            markdown=markdown[:MAX_CHARS]
        )
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                CHAT_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            if response.status_code != 200:
                log.warning("profile.failed", status=response.status_code)
                return None

            payload = json.loads(response.json()["choices"][0]["message"]["content"])
            profile = Profile(**payload)
    except Exception as exc:
        log.warning("profile.failed", error=str(exc))
        return None

    # Pain words are only useful if they are short enough for someone to have
    # actually typed them. A sentence here means the model copied a heading.
    profile.pain_words = [
        " ".join(w.split()) for w in profile.pain_words if 0 < len(w.split()) <= 4
    ][:15]

    log.info(
        "profile.extracted",
        domain=profile.domain,
        problems=len(profile.problems),
        pain_words=len(profile.pain_words),
    )
    return profile
