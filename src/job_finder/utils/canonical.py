"""Canonicalize posting URLs so the DB unique index catches reposts."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Parameters that never change identity of a posting
TRACKING_PARAMS = frozenset(
    {
        # UTM family
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        # Google / Facebook / HubSpot tracking
        "gclid",
        "gclsrc",
        "dclid",
        "fbclid",
        "msclkid",
        "_hsenc",
        "_hsmi",
        "mc_cid",
        "mc_eid",
        # Generic session / referral
        "ref",
        "referrer",
        "source",
        "sid",
        "session",
        "sessionid",
        "s_cid",
        "cid",
        # ATS / board specific
        "gh_src",  # Greenhouse
        "lever-source",  # Lever
        "lever-origin",
        "ashby_jid",  # occasionally appended
        "src",
        "origin",
        "channel",
        "iis",
        "iisn",
    }
)


def canonicalize(url: str) -> str:
    """Return a stable, comparable form of a posting URL.

    - Lowercases scheme + host.
    - Drops fragment.
    - Removes tracking params.
    - Sorts remaining query params alphabetically.
    - Strips a trailing slash unless the path is '/'.
    """
    s = urlsplit(url.strip())
    scheme = s.scheme.lower() or "https"
    host = s.netloc.lower()

    # Strip default ports
    if host.endswith(":80") and scheme == "http":
        host = host[:-3]
    if host.endswith(":443") and scheme == "https":
        host = host[:-4]

    path = s.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    filtered = [
        (k, v) for k, v in parse_qsl(s.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS
    ]
    filtered.sort(key=lambda kv: (kv[0], kv[1]))
    query = urlencode(filtered)

    return urlunsplit((scheme, host, path, query, ""))
