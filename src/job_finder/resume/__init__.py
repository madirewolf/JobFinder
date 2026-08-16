"""Tailored-résumé renderer (markdown + curate-mode selection → PDF).

Cost: $0 — pure templating over data already in `applications.curate_payload`
and the master `profile/resume.md`. No LLM calls.
"""

from __future__ import annotations

from .render import (
    render_cover_letter_for_posting,
    render_for_posting,
    render_master_pdf,
    render_resume_html,
)

__all__ = [
    "render_cover_letter_for_posting",
    "render_for_posting",
    "render_master_pdf",
    "render_resume_html",
]
