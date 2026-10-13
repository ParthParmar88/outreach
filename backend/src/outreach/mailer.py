"""
Getting a link to a person.

There is no mail provider wired up, and pretending otherwise would be the
worst outcome: a reset flow that silently sends nothing looks identical to
one that works, right up until somebody is locked out of a real account.

So this is honest about it. With no provider configured the link is written
to the server log, loudly, and the caller is told it was not actually sent.
Wiring a real provider later means filling in `_send` and nothing else.
"""

from __future__ import annotations

import structlog

from outreach.config import settings

log = structlog.get_logger(__name__)


def is_configured() -> bool:
    """Whether email can actually leave this machine."""
    return bool(getattr(settings, "smtp_host", ""))


def reset_link(token: str) -> str:
    """The URL a person clicks. Points at the app, not at the API."""
    base = (settings.app_url or "http://localhost:5173").rstrip("/")
    return f"{base}/reset-password?token={token}"


async def send_password_reset(email: str, link: str) -> bool:
    """
    Send the reset link. Returns whether it actually went anywhere.

    Never raises. A mail server having a bad day must not turn into a 500 on
    a form somebody is already frustrated to be filling in.
    """
    if not is_configured():
        # WARNING, not INFO. Somebody is locked out and this is the only
        # place the link exists - it should be hard to miss in a log.
        log.warning(
            "mail.not_configured",
            to=email,
            link=link,
            hint="No SMTP_HOST set. Copy the link above to finish the reset.",
        )
        return False

    try:
        await _send(email, link)
        log.info("mail.reset_sent", to=email)
        return True
    except Exception as exc:
        log.warning("mail.reset_failed", to=email, error=str(exc), link=link)
        return False


async def _send(email: str, link: str) -> None:
    """
    The one function to fill in when a provider is chosen.

    Deliberately left unimplemented rather than half-written against an API
    nobody has picked yet. `is_configured` gates every call, so this is
    never reached until the settings exist to reach it with.
    """
    raise NotImplementedError(
        "No mail transport is implemented. Set SMTP_HOST and write _send()."
    )
