"""
Crawl a website and print what we would store. No database needed.

The fastest way to see whether discovery picked the right pages and whether
the markdown is any good, before wiring anything up.

    cd backend
    .venv/Scripts/python.exe ../scripts/try_crawl.py https://example.com
    .venv/Scripts/python.exe ../scripts/try_crawl.py https://example.com --save out.md
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from pathlib import Path

from outreach.connectors.http import http_client
from outreach.connectors.website import crawl, discover
from outreach.connectors.website.extract import combine
from outreach.domain.canonical_url import canonicalize


async def main() -> int:
    # Windows consoles default to cp1252 and choke on the dashes and quotes
    # that real websites are full of. The stored markdown is always UTF-8.
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Crawl one product website.")
    parser.add_argument("url", help="Product website, e.g. https://example.com")
    parser.add_argument("--save", help="Write the combined markdown to this file")
    parser.add_argument("--max-pages", type=int, help="Override the page seatbelt")
    args = parser.parse_args()

    if args.max_pages:
        from outreach.config import settings

        settings.crawl_max_pages = args.max_pages

    canonical = canonicalize(args.url)
    print(f"\n  input     {args.url}")
    print(f"  canonical {canonical.origin}")
    print(f"  domain    {canonical.domain}\n")

    async with http_client() as client:
        print("  looking for documentation ...")
        discovery = await discover(client, canonical.origin)

        for note in discovery.notes:
            print(f"    - {note}")

        print(f"\n  MODE      {discovery.mode.upper()}")
        if discovery.docs_root:
            print(f"  docs root {discovery.docs_root}")
        print(f"  seeds     {len(discovery.seeds)}")
        for seed in discovery.seeds[:8]:
            print(f"    - {seed}")
        if len(discovery.seeds) > 8:
            print(f"    ... and {len(discovery.seeds) - 8} more")

        print("\n  crawling ...\n")
        result = await crawl(client, discovery)

    usable = result.usable
    thin = [p for p in result.pages if p.content.is_thin]

    for page in usable[:40]:
        title = (page.content.title or "")[:60]
        print(f"    {page.content.word_count:>6} words  {title:<62} {page.url}")
    if len(usable) > 40:
        print(f"    ... and {len(usable) - 40} more")

    markdown = combine([(p.content.title, p.url, p.content.markdown) for p in usable])

    print("\n  " + "-" * 72)
    print(f"  pages fetched   {len(result.pages)}")
    print(f"  usable          {len(usable)}")
    print(f"  nearly empty    {len(thin)}")
    print(f"  total words     {sum(p.content.word_count for p in usable):,}")
    print(f"  downloaded      {result.bytes_fetched / 1_000_000:.1f} MB")
    print(f"  markdown size   {len(markdown) / 1000:.1f} KB")
    if result.truncated:
        print(f"  TRUNCATED       {result.stop_reason}")
    print("  " + "-" * 72)

    if not usable:
        print("\n  Nothing readable. The site probably renders with JavaScript.\n")
        return 1

    if args.save:
        Path(args.save).write_text(markdown, encoding="utf-8")
        print(f"\n  written to {args.save}\n")
    else:
        print("\n  first 1200 characters of the combined markdown:\n")
        print("  " + markdown[:1200].replace("\n", "\n  "))
        print("\n  ... use --save out.md to write the whole thing\n")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
