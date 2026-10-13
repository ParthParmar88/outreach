"""Deterministic URL canonicalization. Ordered steps, documented."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

#: Parameters that identify a marketing campaign, not a page. Two URLs that
#: differ only by these are the same page and must canonicalize identically.
TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "gclid",
        "fbclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "ref",
        "referrer",
        "source",
    }
)

DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class CanonicalUrl:
    """The result of canonicalizing. All fields are derived, never guessed."""

    url: str
    """Full canonical URL, e.g. https://example.com/docs/quickstart"""

    origin: str
    """Scheme and host only, e.g. https://example.com"""

    domain: str
    """Host without www. The identity of a product."""

    path: str
    """Path only, always starting with / and never ending with one."""


def canonicalize(raw: str) -> CanonicalUrl:
    """
    Turn whatever a user typed into one stable form.

    The steps run in this order and the order matters:

      1. strip surrounding whitespace
      2. add https:// when no scheme was given
      3. lowercase the scheme and the host, leave the path alone
         (paths are case sensitive on most servers, hosts are not)
      4. drop a leading "www." so that www.x.com and x.com are one page
      5. drop the port when it is the default for the scheme
      6. drop the fragment, it never reaches the server
      7. drop tracking parameters, then sort what remains
      8. drop every trailing slash, including on the root, so that the
         homepage has exactly one form and cannot be fetched twice

    Pure. No network, no clock, no randomness. Same input, same output,
    forever.
    """
    text = raw.strip()
    if not text:
        raise ValueError("URL is empty")

    # 2. scheme
    if "://" not in text:
        text = f"https://{text}"

    parts = urlsplit(text)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported scheme: {parts.scheme}")
    if not parts.hostname:
        raise ValueError(f"No host in URL: {raw}")

    # 3 and 4. lowercase scheme and host, drop www.
    scheme = parts.scheme.lower()
    host = _registrable(parts.hostname.lower())

    # 5. default port
    netloc = host
    if parts.port and parts.port != DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"

    # 7. query
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(kept))

    # 8. path. "" and "/" are the same page, and both canonicalize to "".
    path = (parts.path or "").rstrip("/")

    # 6. fragment dropped by passing ""
    url = urlunsplit((scheme, netloc, path, query, ""))
    origin = urlunsplit((scheme, netloc, "", "", ""))

    return CanonicalUrl(
        url=url,
        origin=origin,
        domain=host,
        # Reported as "/" for the root, because path rules read better that
        # way, while the URL itself carries no trailing slash.
        path=path or "/",
    )


def _registrable(host: str) -> str:
    """
    The domain we treat as the product's identity.

    Only strips a leading "www.". This is deliberately simple: a full public
    suffix list would be needed to tell example.co.uk from a subdomain, and
    the only thing that would buy us today is a slightly better duplicate
    check. Revisit if two products ever collide.
    """
    return host[4:] if host.startswith("www.") else host


def same_site(a: str, b: str) -> bool:
    """True when two URLs belong to the same product website."""
    try:
        return canonicalize(a).domain == canonicalize(b).domain
    except ValueError:
        return False


def is_under(url: str, prefix: str) -> bool:
    """
    True when `url` sits inside `prefix`.

    Used to keep a docs crawl inside the docs section. Compares canonical
    forms so that /docs, /docs/ and /Docs?utm_source=x behave predictably.
    """
    try:
        u = canonicalize(url)
        p = canonicalize(prefix)
    except ValueError:
        return False
    if u.domain != p.domain:
        return False
    if p.path == "/":
        return True
    return u.path == p.path or u.path.startswith(p.path + "/")
