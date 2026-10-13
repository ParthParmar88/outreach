"""
Decide what to crawl.

Two outcomes, exactly as specified:

  docs mode  the site has documentation, so we read only that
  site mode  no documentation, so we read the pages most likely to
             explain what the product is and what it solves
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.robotparser import RobotFileParser

import httpx
from lxml import etree

from outreach.connectors.http import get, is_html
from outreach.connectors.website.extract import extract, link_texts
from outreach.domain.canonical_url import canonicalize

# ---------------------------------------------------------------- docs hints

DOC_PATHS = (
    "/docs",
    "/documentation",
    "/doc",
    "/guide",
    "/guides",
    "/manual",
    "/learn",
    "/reference",
    "/api-reference",
    "/developers",
    "/handbook",
)

DOC_SUBDOMAINS = ("docs", "help", "developer", "developers", "support", "learn")

DOC_LINK_WORDS = ("docs", "documentation", "developer docs", "api docs", "guides", "reference")

# ------------------------------------------------------- site mode ranking

#: Pages that usually say what the product is and what it solves.
HIGH_VALUE = (
    "/features",
    "/product",
    "/products",
    "/how-it-works",
    "/how_it_works",
    "/use-cases",
    "/usecases",
    "/solutions",
    "/platform",
    "/capabilities",
    "/pricing",
    "/faq",
    "/why",
    "/overview",
    "/what-is",
)

MEDIUM_VALUE = ("/about", "/company", "/technology", "/integrations", "/security")

#: Removed on purpose. Blog posts and job adverts are the biggest source of
#: material that reads like the product but is not about the product.
NEVER = (
    "/blog",
    "/news",
    "/press",
    "/careers",
    "/jobs",
    "/legal",
    "/privacy",
    "/terms",
    "/cookie",
    "/login",
    "/signin",
    "/sign-in",
    "/signup",
    "/sign-up",
    "/register",
    "/contact",
    "/events",
    "/webinar",
    "/community",
    "/changelog",
    "/status",
)


@dataclass
class Discovery:
    mode: str
    """"docs" or "site"."""

    seeds: list[str]
    """Where the crawl starts. In docs mode this is the docs root."""

    docs_root: str | None = None
    robots: RobotFileParser | None = None
    sitemap_urls: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    """Human readable trail of what was checked and what was found."""


async def discover(client: httpx.AsyncClient, origin: str) -> Discovery:
    """
    Four checks for documentation, in order, stopping at the first real hit.

      1. the usual paths, /docs and friends
      2. a docs subdomain, docs.example.com
      3. sitemap.xml, looking for docs URLs inside it
      4. the homepage's own links, looking for one that says "Docs"

    If none of them hit, fall back to ranking the site's own pages.
    """
    notes: list[str] = []
    robots, sitemaps = await _robots(client, origin)

    # 1 and 2 --------------------------------------------------------------
    candidates = [f"{origin}{path}" for path in DOC_PATHS]
    candidates += _subdomain_candidates(origin)

    for candidate in candidates:
        if robots and not robots.can_fetch("*", candidate):
            continue
        if await _looks_like_docs(client, candidate):
            notes.append(f"Found documentation at {candidate}")
            return Discovery(
                mode="docs",
                seeds=[candidate],
                docs_root=candidate,
                robots=robots,
                sitemap_urls=sitemaps,
                notes=notes,
            )

    notes.append("No documentation at the usual addresses")

    # 3 --------------------------------------------------------------------
    sitemap_pages = await _sitemap_pages(client, origin, sitemaps)
    docs_from_sitemap = [u for u in sitemap_pages if _has_doc_path(u)]
    if docs_from_sitemap:
        root = _common_prefix(docs_from_sitemap)
        notes.append(
            f"Documentation found in sitemap.xml, {len(docs_from_sitemap)} pages under {root}"
        )
        return Discovery(
            mode="docs",
            seeds=[root, *docs_from_sitemap[:200]],
            docs_root=root,
            robots=robots,
            sitemap_urls=sitemaps,
            notes=notes,
        )

    # 4 --------------------------------------------------------------------
    homepage = await _fetch_html(client, origin)
    if homepage:
        for text, href in link_texts(homepage, origin):
            looks_like_a_docs_link = any(word in text for word in DOC_LINK_WORDS)
            if looks_like_a_docs_link and await _looks_like_docs(client, href):
                notes.append(f'Homepage links to documentation at {href} (link text: "{text}")')
                return Discovery(
                    mode="docs",
                    seeds=[href],
                    docs_root=href,
                    robots=robots,
                    sitemap_urls=sitemaps,
                    notes=notes,
                )

    # site mode ------------------------------------------------------------
    notes.append("No documentation anywhere, reading the most informative pages instead")

    pool = sitemap_pages or (_same_site_links(homepage, origin) if homepage else [])
    seeds = rank_site_pages(pool, origin)
    if origin not in seeds:
        seeds.insert(0, origin)

    notes.append(f"{len(seeds)} candidate pages after removing blog, careers and legal")

    return Discovery(
        mode="site",
        seeds=seeds,
        robots=robots,
        sitemap_urls=sitemaps,
        notes=notes,
    )


# ---------------------------------------------------------------- ranking


def rank_site_pages(urls: list[str], origin: str) -> list[str]:
    """
    Sort candidate pages by how likely they are to explain the product.

    Pure function so it can be tested without a network.
    """
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()

    for url in urls:
        try:
            canonical = canonicalize(url)
        except ValueError:
            continue
        if canonical.domain != canonicalize(origin).domain:
            continue
        if canonical.url in seen:
            continue
        seen.add(canonical.url)

        path = canonical.path.lower()
        if any(path.startswith(bad) for bad in NEVER):
            continue

        if path == "/":
            score = 90
        elif any(path.startswith(good) for good in HIGH_VALUE):
            score = 100 - path.count("/")
        elif any(path.startswith(ok) for ok in MEDIUM_VALUE):
            score = 60 - path.count("/")
        else:
            score = 30 - path.count("/")

        scored.append((score, canonical.url))

    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [url for _, url in scored]


# ---------------------------------------------------------------- helpers


async def _robots(
    client: httpx.AsyncClient, origin: str
) -> tuple[RobotFileParser | None, list[str]]:
    """
    Read robots.txt before touching anything else.

    A site with no robots.txt is treated as allowing everything, which is
    the standard reading. A site we cannot reach at all is also treated as
    allowing, because the alternative is refusing to crawl any site whose
    robots endpoint is slow.
    """
    try:
        response = await get(client, f"{origin}/robots.txt")
    except Exception:
        return None, []

    if response.status_code != 200 or not response.text:
        return None, []

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())

    sitemaps = [
        line.split(":", 1)[1].strip()
        for line in response.text.splitlines()
        if line.lower().startswith("sitemap:")
    ]
    return parser, sitemaps


async def _fetch_html(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await get(client, url)
    except Exception:
        return None
    if response.status_code != 200 or not is_html(response):
        return None
    return response.text


async def _looks_like_docs(client: httpx.AsyncClient, url: str) -> bool:
    """
    A real docs section, not a redirect back to the homepage.

    Three conditions, all required:
      the request succeeded,
      we did not get bounced somewhere unrelated,
      and there is enough text on the page to be worth reading.
    """
    try:
        response = await get(client, url)
    except Exception:
        return False

    if response.status_code != 200 or not is_html(response):
        return False

    final = str(response.url)
    try:
        landed = canonicalize(final).path.lower()
        asked = canonicalize(url).path.lower()
    except ValueError:
        return False

    # Sites without docs very often redirect /docs to the homepage.
    if landed == "/" and asked != "/":
        return False

    # Or bounce us to something unrelated. Compare the first path segment.
    if _first_segment(landed) != _first_segment(asked):
        return False

    return extract(response.text, final).word_count >= 80


def _first_segment(path: str) -> str:
    parts = path.strip("/").split("/")
    return parts[0] if parts and parts[0] else ""


def _subdomain_candidates(origin: str) -> list[str]:
    canonical = canonicalize(origin)
    return [f"https://{prefix}.{canonical.domain}" for prefix in DOC_SUBDOMAINS]


def _has_doc_path(url: str) -> bool:
    try:
        path = canonicalize(url).path.lower()
    except ValueError:
        return False
    return any(path.startswith(doc) for doc in DOC_PATHS)


def _common_prefix(urls: list[str]) -> str:
    """The shared root of a set of docs URLs, e.g. https://x.com/docs."""
    first = canonicalize(urls[0])
    segments = first.path.strip("/").split("/")
    return f"{first.origin}/{segments[0]}" if segments and segments[0] else first.origin


def _same_site_links(html: str, origin: str) -> list[str]:
    from outreach.connectors.website.extract import links

    domain = canonicalize(origin).domain
    out: list[str] = []
    for href in links(html, origin):
        try:
            if canonicalize(href).domain == domain:
                out.append(href)
        except ValueError:
            continue
    return out


async def _sitemap_pages(
    client: httpx.AsyncClient, origin: str, declared: list[str]
) -> list[str]:
    """
    Read sitemap.xml, following sitemap index files one level down.

    Sitemaps are the cheapest possible way to learn a site's shape: one
    request instead of crawling to find out.
    """
    queue = list(declared) or [f"{origin}/sitemap.xml"]
    pages: list[str] = []
    seen: set[str] = set()

    while queue and len(pages) < 5000:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)

        try:
            response = await get(client, url)
        except Exception:
            continue
        if response.status_code != 200:
            continue

        try:
            root = etree.fromstring(response.content)
        except Exception:
            continue

        tag = etree.QName(root).localname
        locations = [
            str(node.text).strip()
            for node in root.iter()
            if etree.QName(node).localname == "loc" and node.text
        ]

        if tag == "sitemapindex":
            queue.extend(locations[:50])
        else:
            pages.extend(locations)

    return pages
