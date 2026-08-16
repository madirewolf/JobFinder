"""Tests for URL canonicalization — verifies dedup across UTMs and source variants."""

from __future__ import annotations

from job_finder.utils.canonical import canonicalize


class TestCanonicalize:
    def test_strips_utm_params(self):
        url = "https://boards.greenhouse.io/cohere/jobs/123?utm_source=linkedin&utm_medium=feed"
        assert canonicalize(url) == "https://boards.greenhouse.io/cohere/jobs/123"

    def test_strips_fbclid_gclid(self):
        url = "https://example.com/job?gclid=xyz&fbclid=abc"
        assert canonicalize(url) == "https://example.com/job"

    def test_strips_greenhouse_gh_src(self):
        url = "https://boards.greenhouse.io/cohere/jobs/123?gh_src=newsletter"
        assert canonicalize(url) == "https://boards.greenhouse.io/cohere/jobs/123"

    def test_lowercases_host(self):
        url = "HTTPS://Boards.Greenhouse.IO/Cohere/jobs/123"
        assert canonicalize(url) == "https://boards.greenhouse.io/Cohere/jobs/123"

    def test_drops_fragment(self):
        url = "https://example.com/job#apply"
        assert canonicalize(url) == "https://example.com/job"

    def test_trailing_slash_removed_except_root(self):
        assert canonicalize("https://example.com/job/") == "https://example.com/job"
        assert canonicalize("https://example.com/") == "https://example.com/"

    def test_preserves_meaningful_query(self):
        url = "https://jobs.lever.co/waabi?location=toronto&team=research"
        out = canonicalize(url)
        # Params sorted alphabetically for stability
        assert out == "https://jobs.lever.co/waabi?location=toronto&team=research"

    def test_sorts_query_params(self):
        a = canonicalize("https://example.com/j?b=2&a=1")
        b = canonicalize("https://example.com/j?a=1&b=2")
        assert a == b

    def test_two_utm_variants_collide(self):
        a = canonicalize("https://boards.greenhouse.io/cohere/jobs/123?utm_campaign=x")
        b = canonicalize("https://boards.greenhouse.io/cohere/jobs/123?utm_source=y")
        assert a == b

    def test_default_ports_stripped(self):
        assert canonicalize("http://example.com:80/job") == "http://example.com/job"
        assert canonicalize("https://example.com:443/job") == "https://example.com/job"
