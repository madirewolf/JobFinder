"""Fast HTML → plaintext for job descriptions."""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser

MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
MULTI_WS_RE = re.compile(r"[ \t]+")


def strip_html(html: str) -> str:
    """Return a readable plaintext version of a job description HTML body.

    - Drops <script>, <style>, <nav>, <footer>.
    - Preserves paragraph breaks (\\n\\n between block elements).
    - Collapses runs of whitespace.
    """
    if not html or not html.strip():
        return ""

    tree = HTMLParser(html)

    # Remove non-content elements
    for selector in ("script", "style", "nav", "footer", "header"):
        for node in tree.css(selector):
            node.decompose()

    # selectolax's .text(separator="\n") preserves block structure reasonably
    text = tree.body.text(separator="\n", strip=True) if tree.body else tree.text(separator="\n", strip=True)

    text = MULTI_WS_RE.sub(" ", text)
    text = MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()
