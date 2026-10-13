"""Shared httpx client: retries, backoff, ETag cache, user agent, Retry-After."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from outreach.config import settings

#: 5xx and connection problems are worth retrying. 4xx are not: the answer
#: will not change by asking again.
RETRYABLE = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)


@asynccontextmanager
async def http_client(**kwargs) -> AsyncIterator[httpx.AsyncClient]:
    """
    One client for the whole crawl.

    Reusing a client keeps connections open, which is both faster and more
    polite than opening a new socket per page.
    """
    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en",
    }
    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        follow_redirects=True,
        max_redirects=5,
        **kwargs,
    ) as client:
        yield client


@retry(
    retry=retry_if_exception_type(RETRYABLE),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET with backoff on transport failures. 4xx and 5xx come back as-is."""
    response = await client.get(url)

    # A server that asks us to wait is telling us we are being rude.
    if response.status_code == 429:
        raise httpx.ReadTimeout("Rate limited", request=response.request)

    return response


def is_html(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "")
    return "html" in content_type.lower()
