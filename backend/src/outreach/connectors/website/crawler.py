"""
Fetch the pages discovery chose.

Breadth first, one page at a time, with a delay between requests. It is
someone else's server and there is no hurry.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
import structlog

from outreach.config import settings
from outreach.connectors.http import get, is_html
from outreach.connectors.website.discovery import NEVER, Discovery
from outreach.connectors.website.extract import Extracted, extract, links
from outreach.domain.canonical_url import canonicalize, is_under

log = structlog.get_logger(__name__)


@dataclass
class CrawledPage:
    url: str
    http_status: int
    fetched_at: datetime
    content: Extracted


@dataclass
class CrawlResult:
    pages: list[CrawledPage] = field(default_factory=list)
    bytes_fetched: int = 0
    truncated: bool = False
    stop_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def usable(self) -> list[CrawledPage]:
        """Pages with real text on them, in crawl order."""
        return [p for p in self.pages if not p.content.is_thin]


async def crawl(client: httpx.AsyncClient, discovery: Discovery) -> CrawlResult:
    """
    Follow links from the seeds, staying in scope, until a seatbelt trips.

    Scope is the whole point:
      docs mode  only URLs under the docs root
      site mode  only URLs on the same domain, minus the never-crawl list
    """
    result = CrawlResult(notes=list(discovery.notes))

    queue: deque[str] = deque()
    seen: set[str] = set()
    stored: set[str] = set()

    for seed in discovery.seeds:
        _enqueue(queue, seen, seed, discovery)

    started = time.monotonic()

    while queue:
        stop = _seatbelt(result, started, len(result.pages))
        if stop:
            result.truncated = True
            result.stop_reason = stop
            log.warning("crawl.truncated", reason=stop, pages=len(result.pages))
            break

        url = queue.popleft()

        if discovery.robots and not discovery.robots.can_fetch("*", url):
            continue

        try:
            response = await get(client, url)
        except Exception as exc:
            log.info("crawl.fetch_failed", url=url, error=str(exc))
            continue

        result.bytes_fetched += len(response.content)

        if response.status_code != 200 or not is_html(response):
            continue

        final_url = str(response.url)

        # Several links can redirect to the same page. `seen` only knows the
        # addresses that were asked for, so where they landed is checked
        # here. Without it one page is kept once per link that led to it,
        # and the table holds a page once per product - the whole crawl was
        # then thrown away over a duplicate.
        landed = _landed_on(final_url)
        if landed in stored:
            continue
        stored.add(landed)

        content = extract(response.text, final_url)

        result.pages.append(
            CrawledPage(
                url=final_url,
                http_status=response.status_code,
                fetched_at=datetime.now(UTC),
                content=content,
            )
        )

        for href in links(response.text, final_url):
            _enqueue(queue, seen, href, discovery)

        # Politeness. Sequential and slow beats fast and rude.
        if settings.crawl_delay_seconds:
            await asyncio.sleep(settings.crawl_delay_seconds)

    if not result.usable and result.pages:
        result.notes.append(
            "Every page came back nearly empty. The site probably renders with "
            "JavaScript, which plain fetching cannot read."
        )

    return result


# ---------------------------------------------------------------- internals


def _landed_on(url: str) -> str:
    """The page a request ended up at, in the form used to compare pages."""
    try:
        return canonicalize(url).url
    except ValueError:
        return url


def _enqueue(queue: deque[str], seen: set[str], url: str, discovery: Discovery) -> None:
    try:
        canonical = canonicalize(url)
    except ValueError:
        return

    if canonical.url in seen:
        return
    if not _in_scope(canonical.url, canonical.path, discovery):
        return

    seen.add(canonical.url)
    queue.append(canonical.url)


def _in_scope(url: str, path: str, discovery: Discovery) -> bool:
    if discovery.mode == "docs" and discovery.docs_root:
        return is_under(url, discovery.docs_root)

    # site mode: same domain, and not something we never want.
    if not discovery.seeds:
        return False
    try:
        home = canonicalize(discovery.seeds[0])
    except ValueError:
        return False
    if canonicalize(url).domain != home.domain:
        return False
    return not any(path.lower().startswith(bad) for bad in NEVER)


def _seatbelt(result: CrawlResult, started: float, page_count: int) -> str | None:
    """
    Not a target. A stop line, so one enormous documentation site cannot run
    for hours or cost real money.
    """
    if page_count >= settings.crawl_max_pages:
        return f"Stopped at the {settings.crawl_max_pages} page limit"
    if time.monotonic() - started >= settings.crawl_max_seconds:
        return f"Stopped after {settings.crawl_max_seconds} seconds"
    if result.bytes_fetched >= settings.crawl_max_bytes:
        return f"Stopped at {settings.crawl_max_bytes // 1_000_000} MB downloaded"
    return None
