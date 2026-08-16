"""Tests for title normalization and title_company_hash.

Core invariant: two reasonable labelings of "the same job" collide on the hash;
two different jobs don't.
"""

from __future__ import annotations

from job_finder.utils.hashing import normalize_title, title_company_hash


class TestNormalizeTitle:
    def test_strips_senior_prefix(self):
        assert normalize_title("Senior Software Engineer") == "software engineer"

    def test_strips_staff_prefix(self):
        assert normalize_title("Staff Backend Engineer") == "backend engineer"

    def test_strips_trailing_location(self):
        assert normalize_title("Software Engineer (Toronto)") == "software engineer"

    def test_strips_trailing_remote(self):
        assert normalize_title("Backend Engineer - Remote") == "backend engineer"

    def test_strips_multiple_modifiers(self):
        assert normalize_title("Software Engineer (Toronto) (Remote)") == "software engineer"

    def test_preserves_cpp_hash(self):
        out = normalize_title("Senior C++ Engineer")
        assert "c++" in out

    def test_lowercases(self):
        assert normalize_title("BACKEND ENGINEER") == "backend engineer"

    def test_collapses_whitespace(self):
        assert normalize_title("  Software    Engineer  ") == "software engineer"


class TestTitleCompanyHash:
    def test_same_title_same_company_collide(self):
        a = title_company_hash("Senior Software Engineer", "Cohere")
        b = title_company_hash("Software Engineer (Toronto)", "cohere")
        assert a == b

    def test_different_company_different_hash(self):
        a = title_company_hash("Software Engineer", "Cohere")
        b = title_company_hash("Software Engineer", "Waabi")
        assert a != b

    def test_different_title_different_hash(self):
        a = title_company_hash("Backend Engineer", "Cohere")
        b = title_company_hash("Frontend Engineer", "Cohere")
        assert a != b

    def test_deterministic(self):
        a = title_company_hash("Software Engineer", "Cohere")
        b = title_company_hash("Software Engineer", "Cohere")
        assert a == b

    def test_40_char_sha1(self):
        h = title_company_hash("Software Engineer", "Cohere")
        assert len(h) == 40
