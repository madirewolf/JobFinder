"""Pure tests for portfolio.extract — no network, no DB.

Exercises the URL-normalization, same-origin, and HTML→text paths. These
run the selectolax path when the lib is available; the naïve fallback has
its own direct test.
"""

from __future__ import annotations

import pytest

from job_finder.portfolio.extract import (
    _extract_naive,
    extract_page,
    normalize_url,
    same_origin,
)

BASE = "https://vimy.ai/"


# ---- normalize_url ────────────────────────────────────────────────────────


def test_normalize_absolute_url_preserved():
    assert normalize_url("https://vimy.ai/foo", BASE) == "https://vimy.ai/foo"


def test_normalize_relative_url_resolved():
    assert normalize_url("/foo", BASE) == "https://vimy.ai/foo"


def test_normalize_relative_without_slash():
    assert normalize_url("about", "https://vimy.ai/projects/") == "https://vimy.ai/projects/about"


def test_normalize_strips_fragment():
    assert normalize_url("/foo#bar", BASE) == "https://vimy.ai/foo"


def test_normalize_keeps_querystring():
    assert normalize_url("/foo?x=1", BASE) == "https://vimy.ai/foo?x=1"


def test_normalize_rejects_mailto():
    assert normalize_url("mailto:me@example.com", BASE) is None


def test_normalize_rejects_tel():
    assert normalize_url("tel:+14165551234", BASE) is None


def test_normalize_rejects_javascript():
    assert normalize_url("javascript:void(0)", BASE) is None


def test_normalize_rejects_empty_and_whitespace():
    assert normalize_url("", BASE) is None
    assert normalize_url("   ", BASE) is None


@pytest.mark.parametrize(
    "ext",
    [".pdf", ".png", ".jpg", ".svg", ".zip", ".mp4", ".css", ".js"],
)
def test_normalize_rejects_binary_extensions(ext: str):
    assert normalize_url(f"/resume{ext}", BASE) is None


def test_normalize_accepts_html_like_paths():
    assert normalize_url("/projects/nerf.html", BASE) == "https://vimy.ai/projects/nerf.html"


# ---- same_origin ──────────────────────────────────────────────────────────


def test_same_origin_true_for_matching_host():
    assert same_origin("https://vimy.ai/foo", "https://vimy.ai/")


def test_same_origin_true_for_subpath():
    assert same_origin("https://vimy.ai/projects/nerf", "https://vimy.ai")


def test_same_origin_false_for_subdomain():
    assert not same_origin("https://blog.vimy.ai/", "https://vimy.ai/")


def test_same_origin_false_for_different_scheme():
    assert not same_origin("http://vimy.ai/", "https://vimy.ai/")


def test_same_origin_false_for_different_host():
    assert not same_origin("https://5gcx.ai/", "https://vimy.ai/")


# ---- extract_page (selectolax path) ───────────────────────────────────────


SAMPLE_HTML = """
<!doctype html>
<html>
  <head>
    <title>Vimy — NeRF Demo</title>
    <script>window.foo = 1;</script>
    <style>body { color: red; }</style>
  </head>
  <body>
    <header><nav>Home / About</nav></header>
    <main>
      <h1>NeRF Demo</h1>
      <p>Real-time neural rendering at <b>60fps</b> on WebGPU.</p>
      <a href="/projects/gaussian-splat">Gaussian splatting</a>
      <a href="https://5gcx.ai/">External link</a>
      <a href="/resume.pdf">Resume PDF</a>
      <a href="#top">Back to top</a>
    </main>
    <footer>Copyright 2026</footer>
  </body>
</html>
"""


def test_extract_page_pulls_title():
    p = extract_page(SAMPLE_HTML, "https://vimy.ai/")
    assert "NeRF Demo" in p.title


def test_extract_page_skips_script_and_style_content():
    p = extract_page(SAMPLE_HTML, "https://vimy.ai/")
    assert "window.foo" not in p.text
    assert "color: red" not in p.text


def test_extract_page_keeps_body_text():
    p = extract_page(SAMPLE_HTML, "https://vimy.ai/")
    assert "Real-time neural rendering" in p.text
    assert "60fps" in p.text


def test_extract_page_strips_nav_and_footer():
    p = extract_page(SAMPLE_HTML, "https://vimy.ai/")
    # nav and footer are in STRIP_SELECTORS
    assert "Home / About" not in p.text
    assert "Copyright 2026" not in p.text


def test_extract_page_collects_internal_links():
    p = extract_page(SAMPLE_HTML, "https://vimy.ai/")
    assert "https://vimy.ai/projects/gaussian-splat" in p.links


def test_extract_page_keeps_external_links_in_raw_list():
    # The crawler filters by same_origin; extract_page returns all normalized
    # hrefs so callers can decide policy.
    p = extract_page(SAMPLE_HTML, "https://vimy.ai/")
    assert "https://5gcx.ai/" in p.links


def test_extract_page_drops_binary_links():
    p = extract_page(SAMPLE_HTML, "https://vimy.ai/")
    assert not any(link.endswith(".pdf") for link in p.links)


def test_extract_page_drops_fragment_only_anchors():
    p = extract_page(SAMPLE_HTML, "https://vimy.ai/")
    # "#top" resolves to the same page URL with fragment stripped; that's
    # still valid, but it points back at the current page, not a new one.
    # We don't special-case it here — crawler's `visited` set dedups it.
    assert all("#" not in link for link in p.links)


def test_extract_page_deduplicates_link_list():
    html = """<html><body>
      <a href="/a">1</a><a href="/a">2</a><a href="/a#x">3</a>
    </body></html>"""
    p = extract_page(html, "https://vimy.ai/")
    assert p.links.count("https://vimy.ai/a") == 1


# ---- extract_naive (fallback) ─────────────────────────────────────────────


def test_naive_extract_parity_on_text():
    p_naive = _extract_naive(SAMPLE_HTML, "https://vimy.ai/")
    assert "Real-time neural rendering" in p_naive.text
    assert "window.foo" not in p_naive.text
    assert "color: red" not in p_naive.text


def test_naive_extract_discovers_links():
    p_naive = _extract_naive(SAMPLE_HTML, "https://vimy.ai/")
    assert "https://vimy.ai/projects/gaussian-splat" in p_naive.links


def test_naive_extract_skips_binary_ext():
    p_naive = _extract_naive(SAMPLE_HTML, "https://vimy.ai/")
    assert not any(link.endswith(".pdf") for link in p_naive.links)


# ---- edge cases ───────────────────────────────────────────────────────────


def test_extract_page_empty_html():
    p = extract_page("", "https://vimy.ai/")
    assert p.text == ""
    assert p.links == []


def test_extract_page_title_falls_back_to_h1_then_url():
    html = "<html><body><h1>Hi</h1></body></html>"
    p = extract_page(html, "https://vimy.ai/")
    # Neither <title> nor a nice display name — "Hi" should surface from h1
    assert p.title == "Hi"

    html_no_title = "<html><body><p>no heading</p></body></html>"
    p2 = extract_page(html_no_title, "https://vimy.ai/nope")
    assert p2.title == "https://vimy.ai/nope"
