"""
Website connector.

Given a product URL, work out what to read, read it, and turn it into
markdown. Contains no AI: fetching and text conversion only.

    discovery.py   docs section or informative pages
    crawler.py     fetch, in scope, politely, with seatbelts
    extract.py     html to markdown
"""

from outreach.connectors.website.crawler import CrawledPage, CrawlResult, crawl
from outreach.connectors.website.discovery import Discovery, discover

__all__ = ["CrawlResult", "CrawledPage", "Discovery", "crawl", "discover"]
