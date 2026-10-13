"""
The crawler, and the redirect that threw a whole crawl away.

Found on a real site: three different links in the documentation redirected
to one page. Each link was a new address, so each was fetched, and the page
they all landed on was kept three times. The table holds a page once per
product, so storing the crawl failed, nothing caught it, and the product sat
on "crawling" for good.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from outreach.config import settings
from outreach.connectors.http import http_client
from outreach.connectors.website import crawl
from outreach.connectors.website.discovery import Discovery

ROOT = "https://example.com/docs"


def page(title: str, links: list[str]) -> httpx.Response:
    anchors = "".join(f'<a href="{href}">{href}</a>' for href in links)
    words = " ".join(f"{title} explains one part of the product in plain words." for _ in range(40))
    body = f"<main><p>{words}</p>{anchors}</main>"
    html = f"<html><head><title>{title}</title></head><body>{body}</body></html>"
    return httpx.Response(200, html=html)


@pytest.mark.anyio
@respx.mock
async def test_links_that_redirect_to_one_page_keep_it_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "crawl_delay_seconds", 0)

    respx.get(ROOT).mock(
        return_value=page("Overview", ["/docs/sdk", "/docs/python-sdk", "/docs/js-sdk"])
    )
    respx.get(f"{ROOT}/sdk").mock(return_value=page("SDKs", []))
    # Two old addresses that now point at the same page.
    for old in ("python-sdk", "js-sdk"):
        respx.get(f"{ROOT}/{old}").mock(
            return_value=httpx.Response(301, headers={"location": f"{ROOT}/sdk"})
        )

    async with http_client() as client:
        result = await crawl(client, Discovery(mode="docs", seeds=[ROOT], docs_root=ROOT))

    urls = [p.url for p in result.pages]
    assert urls == [ROOT, f"{ROOT}/sdk"]
    # The table is unique on the address, so this is what storing relies on.
    assert len(urls) == len(set(urls))
