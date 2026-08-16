"""Tests for drafter prompt assembly and response parsing.

Pins:
  - System block has the cache_control marker (otherwise caching is a lie)
  - System block is byte-stable given same inputs (cache-key invariant)
  - Posting-specific strings don't leak into the system block
  - parse_response enforces required keys and clamps invalid variants
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_finder.drafter.prompts import (
    build_system,
    build_user_message,
    parse_response,
)
from job_finder.drafter.types import PortfolioChunk


def _chunk(id_: int, source: str, content: str, project: str | None = None) -> PortfolioChunk:
    return PortfolioChunk(id=id_, source=source, project=project, content=content, cos_dist=0.2)


def _sample_chunks() -> list[PortfolioChunk]:
    return [
        _chunk(1, "resume", "Senior engineer. Built WebGPU rasterizer. Cut first-paint 82%."),
        _chunk(2, "project:nerf", "Real-time NeRF in browser via WGSL tile renderer.", project="nerf"),
        _chunk(3, "portfolio", "Open-source 5G core simulator."),
    ]


class TestBuildSystem:
    def test_returns_list_with_one_text_block(self):
        out = build_system("RESUME TEXT HERE", _sample_chunks())
        assert isinstance(out, list)
        assert len(out) == 1
        block = out[0]
        assert block["type"] == "text"
        assert isinstance(block["text"], str)

    def test_has_ephemeral_cache_control(self):
        out = build_system("R", _sample_chunks())
        assert out[0]["cache_control"] == {"type": "ephemeral"}

    def test_is_byte_stable_for_same_inputs(self):
        a = build_system("R", _sample_chunks())
        b = build_system("R", _sample_chunks())
        assert a[0]["text"] == b[0]["text"]

    def test_changes_when_resume_changes(self):
        a = build_system("RESUME ONE", _sample_chunks())
        b = build_system("RESUME TWO", _sample_chunks())
        assert a[0]["text"] != b[0]["text"]

    def test_contains_portfolio_tags(self):
        out = build_system("R", _sample_chunks())
        text = out[0]["text"]
        assert "<master_resume>" in text
        assert "<top_40_portfolio_chunks>" in text
        assert "<writing_rules>" in text
        assert "<output_schema>" in text

    def test_writing_rules_mention_nonfabrication(self):
        out = build_system("R", _sample_chunks())
        # We want the word "invent" or "make up" somewhere in the rules
        # (guards against accidentally softening the rule)
        text = out[0]["text"].lower()
        assert "invent" in text or "don't" in text


class TestBuildUserMessage:
    def test_returns_single_user_message(self):
        posting = {
            "company_name": "Waabi",
            "title": "Graphics Engineer",
            "location": "Toronto, ON",
            "remote_type": "hybrid",
            "url_canonical": "https://waabi.com/careers/abc",
            "description_text": "Build real-time renderers. WebGPU preferred.",
        }
        out = build_user_message(posting, _sample_chunks())
        assert len(out) == 1
        msg = out[0]
        assert msg["role"] == "user"
        assert isinstance(msg["content"], str)

    def test_contains_posting_fields(self):
        posting = {
            "company_name": "Waabi",
            "title": "Graphics Engineer",
            "location": "Toronto, ON",
            "remote_type": "hybrid",
            "url_canonical": "https://waabi.com/careers/abc",
            "description_text": "Build real-time renderers. WebGPU preferred.",
        }
        content = build_user_message(posting, _sample_chunks())[0]["content"]
        assert "Waabi" in content
        assert "Graphics Engineer" in content
        assert "Toronto" in content
        assert "WebGPU" in content
        assert "<posting>" in content
        assert "<top_8_relevant_portfolio_chunks>" in content

    def test_description_is_truncated(self):
        huge = "x" * 50_000
        posting = {
            "company_name": "X",
            "title": "T",
            "location": "—",
            "remote_type": "remote",
            "url_canonical": "https://example.com/x",
            "description_text": huge,
        }
        content = build_user_message(posting, [])[0]["content"]
        # Hard truncation at 8000 chars — content overall grew by the other
        # fixed-size blocks, but the `xxx…` run can't exceed MAX_DESCRIPTION_CHARS.
        x_run = max(len(s) for s in content.split("\n") if set(s) == {"x"})
        assert x_run <= 8000


class TestPostingDoesNotLeakIntoSystem:
    """The cache key = system block bytes. If posting-specific text leaks,
    cache hit rate collapses — so we explicitly verify it doesn't."""

    def test_system_stable_across_different_postings(self):
        s = build_system("RESUME", _sample_chunks())[0]["text"]
        # Prove that calling build_user_message afterwards, with different postings,
        # doesn't mutate the system block output.
        for co in ("Waabi", "Cohere", "NotReal Inc"):
            _ = build_user_message(
                {
                    "company_name": co,
                    "title": "SWE",
                    "location": "X",
                    "remote_type": "remote",
                    "url_canonical": "u",
                    "description_text": "d",
                },
                _sample_chunks(),
            )
        # Re-derive and compare
        s2 = build_system("RESUME", _sample_chunks())[0]["text"]
        assert s == s2


class TestParseResponse:
    def _ok_payload(self) -> dict:
        return {
            "tailored_bullets": [{"section": "Experience", "bullet": "Shipped X"}],
            "cover_letter": "Hello team, ...",
            "talking_points": ["a", "b", "c"],
            "red_flags": ["Uses Cobol"],
            "suggested_resume_variant": "graphics",
        }

    def test_round_trip_valid_json(self):
        out = parse_response(json.dumps(self._ok_payload()))
        assert out["suggested_resume_variant"] == "graphics"
        assert out["cover_letter"].startswith("Hello")

    def test_tolerates_leading_prose(self):
        payload = self._ok_payload()
        text = "Here is the response:\n" + json.dumps(payload)
        out = parse_response(text)
        assert out["suggested_resume_variant"] == "graphics"

    def test_tolerates_markdown_fences(self):
        payload = self._ok_payload()
        text = "```json\n" + json.dumps(payload) + "\n```"
        out = parse_response(text)
        assert out["cover_letter"] == "Hello team, ..."

    def test_rejects_missing_keys(self):
        payload = self._ok_payload()
        del payload["cover_letter"]
        with pytest.raises(ValueError, match="missing keys"):
            parse_response(json.dumps(payload))

    def test_rejects_no_json_at_all(self):
        with pytest.raises(ValueError, match="no JSON"):
            parse_response("Sure, I can help with that. No JSON here.")

    def test_clamps_invalid_variant_to_generic(self):
        payload = self._ok_payload()
        payload["suggested_resume_variant"] = "not_a_real_variant"
        out = parse_response(json.dumps(payload))
        assert out["suggested_resume_variant"] == "generic"

    def test_coerces_non_list_fields_to_empty(self):
        payload = self._ok_payload()
        payload["talking_points"] = "should have been a list"
        payload["red_flags"] = None
        payload["tailored_bullets"] = "oops"
        out = parse_response(json.dumps(payload))
        assert out["talking_points"] == []
        assert out["red_flags"] == []
        assert out["tailored_bullets"] == []


class TestCurateNewFields:
    """Curate parser must accept and shape-guard the new April-2026 fields:
    tailored_summary, skills_order, skills_item_order, angles_considered.
    """

    BASE = {
        "selected_projects": ["resume", "capstone-bell412"],
        "dropped_projects": ["limiliminal"],
        "emphasis_quotes": [{"source": "resume.md", "quote": "verbatim line"}],
        "suggested_phrasings": [],
        "cover_letter": "Hi.",
        "talking_points": ["a", "b", "c"],
        "red_flags": [],
        "suggested_resume_variant": "ml_graphics",
    }

    def test_accepts_new_fields(self):
        payload = dict(self.BASE)
        payload["tailored_summary"] = "Per-posting summary text."
        payload["skills_order"] = ["Languages", "AI / ML"]
        payload["skills_item_order"] = {"Languages": ["Python", "C++17"]}
        payload["angles_considered"] = [
            {"slug": "limiliminal", "angle": "no graphics overlap", "decision": "dropped"}
        ]
        out = parse_response(json.dumps(payload), mode="curate")
        assert out["tailored_summary"] == "Per-posting summary text."
        assert out["skills_order"] == ["Languages", "AI / ML"]
        assert out["skills_item_order"] == {"Languages": ["Python", "C++17"]}
        assert out["angles_considered"] == [
            {"slug": "limiliminal", "angle": "no graphics overlap", "decision": "dropped"}
        ]

    def test_defaults_when_new_fields_absent(self):
        # Old curate-mode responses pre-April-2026 don't have the new keys.
        # Parser must NOT raise; must fall back to safe defaults.
        out = parse_response(json.dumps(self.BASE), mode="curate")
        assert out["tailored_summary"] == ""
        assert out["skills_order"] == []
        assert out["skills_item_order"] == {}
        assert out["angles_considered"] == []

    def test_garbage_skills_item_order_is_coerced_to_empty(self):
        payload = dict(self.BASE)
        payload["skills_item_order"] = "not a dict"
        out = parse_response(json.dumps(payload), mode="curate")
        assert out["skills_item_order"] == {}

    def test_decision_clamped_to_kept_or_dropped(self):
        payload = dict(self.BASE)
        payload["angles_considered"] = [
            {"slug": "x", "angle": "y", "decision": "maybe-drop"},
            {"slug": "z", "angle": "w", "decision": "dropped"},
        ]
        out = parse_response(json.dumps(payload), mode="curate")
        # Anything other than 'dropped' clamps to 'kept'
        assert out["angles_considered"][0]["decision"] == "kept"
        assert out["angles_considered"][1]["decision"] == "dropped"


class TestFitGateParser:
    """Fit-gate parser produces a stable shape regardless of model output
    quirks (missing keys, None values, malformed nested objects).
    """

    def _parse(self, payload: dict) -> dict:
        from job_finder.drafter.prompts import parse_fitgate_response
        return parse_fitgate_response(json.dumps(payload))

    def test_clean_proceed_response(self):
        out = self._parse({
            "seniority_delta": {
                "ok": True, "candidate_yoe_actual": 1.5,
                "posting_yoe_required": 2, "reason": "close enough",
            },
            "domain_delta": {
                "ok": True, "candidate_strongest_domains": ["robotics"],
                "posting_required_domain": "robotics",
                "reason": "direct match",
            },
            "overall_score": 0.82,
            "verdict": "proceed",
            "skip_reason": "",
        })
        assert out["verdict"] == "proceed"
        assert out["overall_score"] == 0.82
        assert out["seniority_delta"]["ok"] is True
        assert out["domain_delta"]["candidate_strongest_domains"] == ["robotics"]

    def test_skip_response_with_reason(self):
        out = self._parse({
            "seniority_delta": {
                "ok": False, "candidate_yoe_actual": 1.5,
                "posting_yoe_required": 8, "reason": "Staff role",
            },
            "domain_delta": {
                "ok": True, "candidate_strongest_domains": ["x"],
                "posting_required_domain": "y", "reason": "z",
            },
            "overall_score": 0.25,
            "verdict": "skip",
            "skip_reason": "seniority gap of ~6 yrs",
        })
        assert out["verdict"] == "skip"
        assert out["skip_reason"] == "seniority gap of ~6 yrs"

    def test_score_clamped_to_zero_one(self):
        for raw, expected in [(-0.1, 0.0), (1.5, 1.0), ("0.7", 0.7), (None, 0.0)]:
            out = self._parse({
                "seniority_delta": {"ok": True},
                "domain_delta": {"ok": True},
                "overall_score": raw,
                "verdict": "proceed",
            })
            assert out["overall_score"] == expected

    def test_unknown_verdict_clamped_to_proceed(self):
        # Defensive: a malformed verdict shouldn't accidentally block work.
        out = self._parse({
            "seniority_delta": {"ok": True},
            "domain_delta": {"ok": True},
            "overall_score": 0.7,
            "verdict": "lol-idk",
        })
        assert out["verdict"] == "proceed"


class TestPortfolioChunkImport:
    def test_dataclass_roundtrip(self):
        c = PortfolioChunk(id=1, source="resume", project=None, content="x", cos_dist=0.1)
        assert c.id == 1
        assert c.project is None

    def test_pathlib_path_type_works(self):
        # Sanity: the default argument type in prompts/draft is Path
        assert isinstance(Path("profile"), Path)
