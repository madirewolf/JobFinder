"""Pure HTML → text extraction helpers.

No network, no DB. All the fiddly bits (URL normalization, link discovery,
HTML stripping) live here so they're easy to test. `crawler.py` imports these
to drive the actual fetching.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlparse


# CSS selectors we strip before extracting text. Boilerplate cut-outs: we
# don't want "Cookies: accept" in the portfolio-chunk store.
STRIP_SELECTORS = (
    "script",
    "style",
    "noscript",
    "template",
    "nav",
    "header",
    "footer",
    "form",
    "iframe",
    "svg",
    "aside",
    "[role=navigation]",
    "[role=banner]",
    "[role=contentinfo]",
    "[aria-hidden=true]",
)

# File extensions we won't follow even if linked — would blow up fetch budgets
# and almost never add portfolio value.
SKIP_EXTS = (
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".mp4",
    ".mov",
    ".webm",
    ".zip",
    ".tar",
    ".gz",
    ".css",
    ".js",
)


@dataclass(slots=True)
class ExtractedPage:
    url: str
    title: str
    text: str
    links: list[str]


def normalize_url(href: str, base: str) -> str | None:
    """Resolve `href` against `base` and strip fragments.

    Returns None for:
      - non-http(s) schemes (mailto:, tel:, javascript:)
      - obviously-binary file extensions
      - empty/blank inputs
    """
    if not href or not href.strip():
        return None
    # Drop fragments like /page#section so #section, #top etc. don't multiply
    href = href.strip()
    resolved = urljoin(base, href)
    resolved, _frag = urldefrag(resolved)
    p = urlparse(resolved)
    if p.scheme not in {"http", "https"}:
        return None
    low = p.path.lower()
    if any(low.endswith(ext) for ext in SKIP_EXTS):
        return None
    return resolved


def same_origin(url: str, origin: str) -> bool:
    """True when `url` shares scheme+host with `origin` (any port combo)."""
    a, b = urlparse(url), urlparse(origin)
    return (a.scheme, a.hostname) == (b.scheme, b.hostname)


def extract_page(html: str, url: str) -> ExtractedPage:
    """Pull title, visible text, and same-document link hrefs from `html`.

    Falls back to a naïve implementation if selectolax is unavailable at
    import time (e.g. bare test environments). The test suite runs through
    this path so we keep it dependency-light.
    """
    try:
        from selectolax.parser import HTMLParser
    except ImportError:  # pragma: no cover - optional dep fallback
        return _extract_naive(html, url)

    tree = HTMLParser(html)

    # Yank boilerplate out of the tree before text extraction
    for sel in STRIP_SELECTORS:
        for node in tree.css(sel):
            node.decompose()

    title_node = tree.css_first("title")
    h1 = tree.css_first("h1")
    title = (
        (title_node.text(strip=True) if title_node else None)
        or (h1.text(strip=True) if h1 else None)
        or url
    )

    body_node = tree.body or tree.root
    text = (body_node.text(separator="\n", strip=True) if body_node else "").strip()
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())

    raw_links = [a.attributes.get("href") for a in tree.css("a[href]")]
    norm_links: list[str] = []
    for href in raw_links:
        if href is None:
            continue
        n = normalize_url(href, url)
        if n:
            norm_links.append(n)

    # Stable-dedup
    seen: set[str] = set()
    dedup: list[str] = []
    for link in norm_links:
        if link not in seen:
            seen.add(link)
            dedup.append(link)

    return ExtractedPage(url=url, title=title, text=text, links=dedup)


def _extract_naive(html: str, url: str) -> ExtractedPage:
    """Very basic HTML→text fallback used when selectolax isn't importable.

    Matches `extract_page`'s return shape so tests are identical under both
    code paths. Not robust to complex markup — good enough for CI sanity.
    """
    import re

    # Drop whole boilerplate blocks (tag AND contents). Match what STRIP_SELECTORS
    # does in the selectolax path so downstream text is consistent.
    strip_tags = ("script", "style", "noscript", "nav", "header", "footer", "form", "aside")
    cleaned = html
    for tag in strip_tags:
        cleaned = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>",
            " ",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )

    title_m = re.search(r"<title[^>]*>(.*?)</title>", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if title_m and title_m.group(1).strip():
        title = title_m.group(1).strip()
    else:
        h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", cleaned, flags=re.IGNORECASE | re.DOTALL)
        if h1_m and h1_m.group(1).strip():
            # Strip any nested tags inside the h1
            title = re.sub(r"<[^>]+>", "", h1_m.group(1)).strip()
        else:
            title = url

    hrefs = re.findall(r'href="([^"]+)"', cleaned, flags=re.IGNORECASE)
    stripped = re.sub(r"<[^>]+>", " ", cleaned)
    text = re.sub(r"\s+", " ", stripped).strip()

    links: list[str] = []
    seen: set[str] = set()
    for h in hrefs:
        n = normalize_url(h, url)
        if n and n not in seen:
            seen.add(n)
            links.append(n)

    return ExtractedPage(url=url, title=title, text=text, links=links)
