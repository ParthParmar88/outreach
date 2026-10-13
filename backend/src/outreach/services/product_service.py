"""Orchestrates the website crawl. Talks to connectors, domain and db."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from outreach import profile as profile_reader
from outreach.connectors.http import http_client
from outreach.connectors.website import crawl, discover
from outreach.connectors.website.extract import combine
from outreach.db.models.product import CrawlMode, CrawlState, Product, ProductPage
from outreach.db.repositories import products as repo
from outreach.db.session import session_scope
from outreach.domain.canonical_url import canonicalize
from outreach.schemas.product import ProductCreate

log = structlog.get_logger(__name__)


class ProductError(Exception):
    """Something the user needs to know about, phrased for a person."""


async def get_or_create(
    session: AsyncSession, payload: ProductCreate, user_id: uuid.UUID
) -> tuple[Product, bool]:
    """
    Register a product, or hand back the one this account already has for
    that domain.

    Returns (product, created). When created is False the caller must NOT
    start a crawl: we already read that site once, and re-reading only ever
    happens when a person presses the button.

    Asking for the same site twice is not an error. It is what happens when
    somebody comes back to a product they already added, which is normal.
    """
    try:
        canonical = canonicalize(payload.url)
    except ValueError as exc:
        raise ProductError(f"That does not look like a website address: {payload.url}") from exc

    existing = await repo.get_by_domain(session, canonical.domain, user_id)
    if existing is not None:
        return existing, False

    product = Product(
        user_id=user_id,
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        goal=(payload.goal or "").strip() or None,
        input_url=payload.url.strip(),
        canonical_url=canonical.origin,
        domain=canonical.domain,
        state=CrawlState.QUEUED,
    )
    return await repo.add(session, product), True


async def run_crawl(product_id: uuid.UUID) -> None:
    """
    The background job.

    Opens its own database session, because the request that started it has
    already returned. Every exit path writes a final state, so a product can
    never be left stuck on "crawling" if something throws.
    """
    async with session_scope() as session:
        product = await repo.get(session, product_id)
        if product is None:
            log.warning("crawl.product_missing", product_id=str(product_id))
            return

        product.state = CrawlState.CRAWLING
        product.crawl_started_at = datetime.now(UTC)
        product.failure_reason = None
        await session.commit()

    try:
        async with http_client() as client:
            async with session_scope() as session:
                product = await repo.get(session, product_id)
                if product is None:
                    return
                origin = product.canonical_url

            discovery = await discover(client, origin)
            log.info(
                "crawl.discovered",
                domain=origin,
                mode=discovery.mode,
                docs_root=discovery.docs_root,
                seeds=len(discovery.seeds),
            )
            result = await crawl(client, discovery)

    except Exception as exc:
        log.exception("crawl.failed", product_id=str(product_id))
        await _mark_failed(product_id, exc)
        return

    # Storing is inside its own guard. It used to sit outside the one above,
    # so a page the database refused left the product on "crawling" with
    # nothing running and nothing logged.
    try:
        async with session_scope() as session:
            product = await repo.get(session, product_id)
            if product is None:
                return

            await repo.clear_pages(session, product_id)

            rows: list[ProductPage] = []
            for index, page in enumerate(result.pages):
                rows.append(
                    ProductPage(
                        product_id=product_id,
                        url=page.url,
                        title=page.content.title,
                        markdown=page.content.markdown,
                        word_count=page.content.word_count,
                        content_hash=page.content.content_hash,
                        http_status=page.http_status,
                        is_thin=page.content.is_thin,
                        order_index=index,
                        fetched_at=page.fetched_at,
                    )
                )
            await repo.add_pages(session, rows)

            usable = result.usable
            markdown = combine(
                [(p.content.title, p.url, p.content.markdown) for p in usable]
            )

            product.mode = CrawlMode.DOCS if discovery.mode == "docs" else CrawlMode.SITE
            product.docs_root = discovery.docs_root
            product.markdown = markdown or None
            product.content_hash = (
                hashlib.sha256(markdown.encode("utf-8")).hexdigest() if markdown else None
            )
            product.page_count = len(usable)
            product.word_count = sum(p.content.word_count for p in usable)
            product.bytes_fetched = result.bytes_fetched
            product.truncated = result.truncated
            product.stop_reason = result.stop_reason
            product.crawl_finished_at = datetime.now(UTC)

            # Fetching worked but there was nothing to read. Say so plainly
            # instead of storing an empty document and calling it ready.
            product.state = CrawlState.READY if usable else CrawlState.THIN
            if not usable:
                product.failure_reason = (
                    "Nothing readable came back. Either the site renders with JavaScript, "
                    "which plain fetching cannot see, or there is genuinely very little "
                    "text on it. Describe the product by hand instead."
                )

            log.info(
                "crawl.finished",
                product_id=str(product_id),
                state=product.state.value,
                pages=product.page_count,
                words=product.word_count,
                truncated=product.truncated,
            )

            markdown_for_profile = product.markdown
            source_hash = product.content_hash
            needs_profile = bool(
                markdown_for_profile and source_hash != product.profile_source_hash
            )
    except Exception as exc:
        log.exception("crawl.save_failed", product_id=str(product_id))
        await _mark_failed(product_id, exc)
        return

    # Reading the site is separate from crawling it, and happens outside the
    # session above so a slow model call does not hold a database connection
    # open. A product with no profile still works; the search falls back to
    # what the user typed.
    if not needs_profile:
        return

    extracted = await profile_reader.extract(markdown_for_profile)
    if extracted is None:
        return

    async with session_scope() as session:
        product = await repo.get(session, product_id)
        if product is None:
            return
        product.profile = extracted.model_dump()
        product.profile_source_hash = source_hash
        log.info("profile.saved", product_id=str(product_id), domain=extracted.domain)

    # The whole chain runs off one button: read the site, understand it, then
    # write the marketing plan. Imported here rather than at module level
    # because plan_service imports the planner, which imports this module's
    # settings - a circular import at load time otherwise.
    from outreach.services import plan_service

    await plan_service.ensure_plan(product_id)


async def _mark_failed(product_id: uuid.UUID, exc: Exception) -> None:
    """Record that the crawl broke, so the product is never left looking busy."""
    async with session_scope() as session:
        product = await repo.get(session, product_id)
        if product is not None:
            product.state = CrawlState.FAILED
            product.failure_reason = str(exc)[:2000]
            product.crawl_finished_at = datetime.now(UTC)


def is_stale(product: Product) -> bool:
    """
    A crawl that has outlived its own time limit.

    The crawl runs inside the API process, so restarting the server, or a
    crash, leaves a product marked "crawling" with nothing actually running.
    Without this check that row is stuck forever: re-crawl refuses because
    it looks busy, and it never stops looking busy.

    Anything past the crawl's own ceiling plus a minute is dead, because a
    live crawl would have hit its seatbelt and finished by then.
    """
    from outreach.config import settings

    if product.state != CrawlState.CRAWLING:
        return False
    if product.crawl_started_at is None:
        return True
    age = (datetime.now(UTC) - product.crawl_started_at).total_seconds()
    return age > settings.crawl_max_seconds + 60


async def reset_for_recrawl(session: AsyncSession, product: Product) -> None:
    """Only ever called from the button. There is no automatic refresh."""
    product.state = CrawlState.QUEUED
    product.failure_reason = None
    product.stop_reason = None
    product.truncated = False
    product.crawl_started_at = None
    product.crawl_finished_at = None
