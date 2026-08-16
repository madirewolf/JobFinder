"""Tests for the resume-render transforms.

Covers the three new (April 2026) transforms:
  - _replace_summary: tailored_summary overrides master Summary; falls back
    to master when empty.
  - _reorder_skills: categories reordered; categories not in skills_order
    dropped; within-category items reordered.
  - Naming-note blockquote is stripped by the polish pass (June 2026 operator
    request — HR-form info, not résumé content; it was briefly kept earlier).
"""

from __future__ import annotations

import textwrap

import pytest

from job_finder.resume.render import (
    _replace_summary,
    _reorder_skills,
    _strip_polish,
)


SAMPLE_MD = textwrap.dedent("""\
    # Mohammad Abu Dagar

    > Naming note: my legal/passport spelling is **Mohammad Abu Dagar**; my email
    > and several public profiles transliterate the Arabic ق as **Daqer**.

    ---

    ## Summary

    Long master summary that mentions everything and ends with the hardcoded
    Targeting line.

    ---

    ## Skills

    **Languages**
    Python · C++17 · Rust · Kotlin · TypeScript

    **Robotics, Autonomy & Control**
    ROS · LVI-SAM · NMPC · MAVLink

    **Trading & Quant**
    IBKR · ib_async · ForecastEx
""")


class TestReplaceSummary:
    def test_replaces_when_tailored_summary_provided(self):
        out = _replace_summary(SAMPLE_MD, "Short per-posting summary.")
        assert "Short per-posting summary." in out
        assert "Long master summary" not in out
        # H2 header is preserved
        assert "## Summary" in out

    def test_no_op_when_tailored_summary_empty(self):
        out = _replace_summary(SAMPLE_MD, "")
        assert "Long master summary" in out

    def test_no_op_when_tailored_summary_whitespace(self):
        out = _replace_summary(SAMPLE_MD, "   \n  \t  ")
        assert "Long master summary" in out

    def test_does_not_eat_subsequent_sections(self):
        out = _replace_summary(SAMPLE_MD, "New summary.")
        # Skills section must still be there after replacement
        assert "## Skills" in out
        assert "Robotics, Autonomy & Control" in out


class TestReorderSkills:
    def test_categories_reordered_per_skills_order(self):
        out = _reorder_skills(
            SAMPLE_MD,
            skills_order=["Robotics, Autonomy & Control", "Languages"],
            skills_item_order=None,
        )
        # Robotics now appears before Languages
        rob_pos = out.find("Robotics, Autonomy & Control")
        lang_pos = out.find("Languages")
        assert rob_pos > 0 and lang_pos > 0
        assert rob_pos < lang_pos

    def test_unlisted_categories_are_dropped(self):
        out = _reorder_skills(
            SAMPLE_MD,
            skills_order=["Languages"],   # only one kept
            skills_item_order=None,
        )
        assert "Languages" in out
        assert "Robotics, Autonomy & Control" not in out
        assert "Trading & Quant" not in out

    def test_within_category_item_order_applied(self):
        out = _reorder_skills(
            SAMPLE_MD,
            skills_order=["Languages"],
            skills_item_order={"Languages": ["TypeScript", "Python"]},
        )
        # TypeScript should come BEFORE Python now
        ts = out.find("TypeScript")
        py = out.find("Python")
        assert ts > 0 and py > 0
        assert ts < py
        # Items not mentioned (Rust, Kotlin, C++17) get dropped
        assert "Rust" not in out
        assert "Kotlin" not in out

    def test_no_op_when_skills_order_empty(self):
        out = _reorder_skills(SAMPLE_MD, skills_order=None, skills_item_order=None)
        assert out == SAMPLE_MD

    def test_handles_master_without_skills_section(self):
        no_skills = "# Name\n\n## Summary\n\nText.\n"
        out = _reorder_skills(no_skills, skills_order=["Languages"], skills_item_order=None)
        assert out == no_skills


class TestNamingNoteStripped:
    def test_strip_polish_drops_naming_note(self):
        out = _strip_polish(
            SAMPLE_MD,
            variant="ml_graphics",
            drop_additional_projects=False,
        )
        # Naming-note blockquote (including continuation lines) must be gone
        assert "Naming note" not in out
        assert "Daqer" not in out
        # ...but the name header itself survives
        assert "# Mohammad Abu Dagar" in out
