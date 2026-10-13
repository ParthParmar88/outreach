"""
Draft a reply to one post. Never posts it anywhere.

The gap this fills: the search finds somebody with the problem, and then the
user stares at a GitHub issue with no idea how to open. That blank moment is
where outreach dies, and it is why a list of good leads still produces
nothing.

Two things make a draft worth having rather than worth deleting:

  * It answers the person's actual problem. A reply that would be worth
    posting with our product deleted from existence is a good reply. One
    that would not is an advertisement, and it is remembered as the day we
    spammed an issue tracker.
  * It is allowed to say "do not reply to this". A bad reply costs more than
    no reply, so `skip_reason` is a first-class answer rather than a failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import structlog
from pydantic import BaseModel

from outreach.config import settings

log = structlog.get_logger(__name__)

CHAT_URL = "https://api.openai.com/v1/chat/completions"
PROMPT_PATH = Path(__file__).parent / "llm" / "prompts" / "draft_reply.v1.md"
#: Stored with the draft, so an old draft is recognisable as old rather than
#: passing for something the current prompt would write.
PROMPT_VERSION = "draft_reply.v1"

#: How much of the post the model reads.
#:
#: Issue bodies run to stack traces and pasted logs. The problem is almost
#: always in the first screen; the rest is evidence for it, and paying to
#: read 40kB of traceback buys nothing a reply can use.
MAX_BODY = 6_000

#: Shorter than this is not a reply, it is a fragment - usually the model
#: returning a refusal it should have put in `skip_reason`.
MIN_REPLY_CHARS = 80


class Draft(BaseModel):
    reply: str = ""
    mentions_product: bool = False
    answers: str = ""
    #: Non-empty means: do not reply to this post, and here is why.
    skip_reason: str = ""

    @property
    def is_usable(self) -> bool:
        return not self.skip_reason and len(self.reply.strip()) >= MIN_REPLY_CHARS


class MentionLeaked(Exception):
    """The model named the product after being told not to, twice running."""


#: What to tell the model about mentioning the product. Two separate
#: instructions rather than one flag, because "you may" and "do not" need
#: different words to be obeyed.
_MENTION_ALLOWED = (
    "You may mention the product, but only if it genuinely bears on what "
    "they asked. If the honest answer does not involve it, leave it out - "
    "that is the better reply and you are not being marked down for it."
)
_MENTION_FORBIDDEN = (
    "Do not mention the product at all. Not by name, not as 'a tool we "
    "build', not as a hint. This reply exists purely to be useful. Set "
    "`mentions_product` to false."
)


async def _ask(
    *,
    title: str,
    body: str,
    author: str,
    container: str,
    kind: str,
    product_name: str,
    product_summary: str,
    product_problems: list[str],
    allow_mention: bool,
) -> Draft | None:
    """One attempt. None when the model could not be reached or parsed."""
    problems = "\n".join(f"- {p}" for p in product_problems[:8]) or "- (not known)"

    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
            container=container or "unknown",
            kind=kind or "issue",
            title=title or "(no title)",
            author=author or "unknown",
            body=(body or "(the post has no body, only a title)")[:MAX_BODY],
            product_name=product_name,
            product_summary=product_summary or "(not known)",
            product_problems=problems,
            mention_rule=_MENTION_ALLOWED if allow_mention else _MENTION_FORBIDDEN,
        )

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                CHAT_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    # Higher than the extraction steps on purpose. This is the
                    # one place in the pipeline writing prose a human will
                    # send, and 0.2 produces the same four sentences every
                    # time - which reads as a template the moment anybody
                    # posts two of them in the same repository.
                    "temperature": 0.6,
                    "response_format": {"type": "json_object"},
                },
            )
            if response.status_code != 200:
                log.warning("reply.failed", status=response.status_code)
                return None

            payload = json.loads(response.json()["choices"][0]["message"]["content"])
            result = Draft(**payload)

    except Exception as exc:
        log.warning("reply.failed", error=str(exc))
        return None

    # Trust the text over the flag. The flag is what the model claims; the
    # text is what gets pasted, and only one of those two is real.
    result.reply = result.reply.strip()
    result.mentions_product = product_name.lower() in result.reply.lower()
    return result


async def draft(
    *,
    title: str,
    body: str,
    author: str,
    container: str,
    kind: str,
    product_name: str,
    product_summary: str,
    product_problems: list[str],
    allow_mention: bool,
) -> Draft | None:
    """
    Write a reply, or None if it could not be written.

    Raises only `MentionLeaked`, which the caller turns into something worth
    reading. Everything else returns None: a missing draft leaves the user
    where they already were, looking at the post themselves, which is worse
    rather than broken.
    """
    if not settings.openai_api_key:
        log.warning("reply.no_api_key")
        return None

    attempt_args = dict(
        title=title,
        body=body,
        author=author,
        container=container,
        kind=kind,
        product_name=product_name,
        product_summary=product_summary,
        product_problems=product_problems,
        allow_mention=allow_mention,
    )

    # Asking is not guaranteeing. When the user asked for a reply with no
    # mention, a model that names the product anyway would put an
    # advertisement in somebody's issue tracker under their name, so that
    # draft is thrown away rather than shown.
    #
    # Twice, because this is prose at temperature 0.6: the same prompt gives
    # a different reply on the second pass, and one retry turns most leaks
    # into a usable draft instead of an error.
    for attempt in (1, 2):
        result = await _ask(**attempt_args)
        if result is None:
            return None

        if allow_mention or not result.mentions_product:
            log.info(
                "reply.drafted",
                chars=len(result.reply),
                mentions=result.mentions_product,
                skipped=bool(result.skip_reason),
                attempt=attempt,
            )
            return result

        log.warning("reply.mention_leaked", product=product_name, attempt=attempt)

    raise MentionLeaked(
        "The model kept naming your product even though you asked for a "
        "reply without it. Try again, or allow the mention."
    )
