"""HTML to markdown. Pure text work, no network and no AI."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import trafilatura
from lxml import html as lxml_html

from outreach.config import settings


@dataclass(frozen=True)
class Extracted:
    title: str | None
    markdown: str
    word_count: int
    content_hash: str
    is_thin: bool


_WHITESPACE = re.compile(r"\n{3,}")


def extract(html: str, url: str) -> Extracted:
    """
    Keep the article, throw away everything around it.

    trafilatura removes the navigation, the footer, the cookie banner and
    the sidebar, and writes what is left as markdown. That boilerplate
    removal matters more than it sounds: a menu repeated on 200 pages
    would otherwise dominate the document.
    """
    markdown = (
        trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_links=False,
            include_tables=True,
            include_comments=False,
            favor_recall=True,
        )
        or ""
    )

    markdown = _WHITESPACE.sub("\n\n", markdown).strip()
    words = len(markdown.split())

    return Extracted(
        title=_title(html),
        markdown=markdown,
        word_count=words,
        content_hash=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        # Almost always means the page is rendered by JavaScript and plain
        # fetching cannot see it. Recorded rather than silently dropped.
        is_thin=words < settings.thin_page_words,
    )


def _title(html: str) -> str | None:
    try:
        tree = lxml_html.fromstring(html)
    except Exception:
        return None

    for xpath in ("//h1//text()", "//title/text()", "//meta[@property='og:title']/@content"):
        found = tree.xpath(xpath)
        if found:
            text = " ".join(str(f) for f in found).strip()
            if text:
                return text[:500]
    return None


def links(html: str, base_url: str) -> list[str]:
    """
    Every href on the page, made absolute.

    Anchors, mailto, tel and javascript are dropped here rather than in the
    crawler, so the crawler only ever sees things it could actually fetch.
    """
    try:
        tree = lxml_html.fromstring(html)
    except Exception:
        return []

    tree.make_links_absolute(base_url, resolve_base_href=True)

    found: list[str] = []
    for href in tree.xpath("//a/@href"):
        value = str(href).strip()
        if not value or value.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        if not value.startswith(("http://", "https://")):
            continue
        found.append(value.split("#", 1)[0])
    return found


def link_texts(html: str, base_url: str) -> list[tuple[str, str]]:
    """(text, absolute url) pairs. Used to spot a link that says "Docs"."""
    try:
        tree = lxml_html.fromstring(html)
    except Exception:
        return []

    tree.make_links_absolute(base_url, resolve_base_href=True)

    pairs: list[tuple[str, str]] = []
    for anchor in tree.xpath("//a[@href]"):
        href = str(anchor.get("href", "")).strip()
        if not href.startswith(("http://", "https://")):
            continue
        text = " ".join(anchor.itertext()).strip().lower()
        if text:
            pairs.append((text, href.split("#", 1)[0]))
    return pairs


def combine(pages: list[tuple[str | None, str, str]]) -> str:
    """
    Join the pages into the single document the AI will read.

    Each page keeps its title as a heading and its URL underneath, so a
    claim can always be traced back to the page it came from.
    """
    blocks: list[str] = []
    for title, url, markdown in pages:
        heading = title or url
        blocks.append(f"## {heading}\n\nSource: {url}\n\n{markdown}")
    return "\n\n---\n\n".join(blocks).strip()
