"""Preset pool résumés — the small set of pre-built, archetype-specific
résumé + cover-letter pairs the operator maintains instead of LLM-tailoring
every application.

Each pool lives at `resumes/<slug>/{resume,cover-letter}.md` (outside the
`profile/` ingestion path, so it never pollutes the profile vector). The
operator queues a posting at draft_mode "preset:<slug>", which attaches the
pool résumé verbatim — $0, no LLM.

This module is the single source of truth for the pool catalog (slug → label
+ blurb). Render/IO helpers live in `render.py`; this module just maps slugs
to human-facing metadata and validates which presets actually exist on disk.
"""

from __future__ import annotations

from dataclasses import dataclass

from .render import (
    PRESET_MODE_PREFIX,
    DEFAULT_POOL_DIR,
    is_preset_mode,
    preset_resume_md_path,
    preset_slug,
)


@dataclass(frozen=True, slots=True)
class Preset:
    slug: str
    label: str       # short button label, e.g. "Graphics & 3D"
    blurb: str       # one-line description shown under the button

    @property
    def mode(self) -> str:
        """The draft_mode value stored on the application."""
        return f"{PRESET_MODE_PREFIX}{self.slug}"


# Order = display order in the UI.
# autonomy-robotics and graphics-3d retired 2026-06-14 (superseded by
# design-engineer; sources moved to resumes/inactive/). Removed from the catalog.
PRESETS: tuple[Preset, ...] = (
    Preset(
        slug="applied-ai-ml",
        label="Applied AI / ML",
        blurb="LLM/RAG, computer vision, and production ML engineering.",
    ),
    Preset(
        slug="fullstack-product",
        label="Full-Stack / Product",
        blurb="React/Next.js + Python backends. Broadest-net, highest volume.",
    ),
    Preset(
        slug="design-engineer",
        label="Design Engineer",
        blurb="Interaction & motion craft — design engineer, UX engineer, creative frontend.",
    ),
)

_BY_SLUG: dict[str, Preset] = {p.slug: p for p in PRESETS}
_BY_MODE: dict[str, Preset] = {p.mode: p for p in PRESETS}


def all_presets() -> tuple[Preset, ...]:
    return PRESETS


def get_by_slug(slug: str) -> Preset | None:
    return _BY_SLUG.get(slug)


def get_by_mode(mode: str | None) -> Preset | None:
    """Resolve a draft_mode like 'preset:graphics-3d' to its Preset."""
    return _BY_MODE.get(mode or "")


def is_valid_preset_mode(mode: str | None) -> bool:
    """True only for preset modes whose pool is in the catalog AND on disk."""
    if not is_preset_mode(mode):
        return False
    slug = preset_slug(mode)
    return slug in _BY_SLUG and preset_resume_md_path(slug, pool_dir=DEFAULT_POOL_DIR).exists()


def preset_label(mode: str | None) -> str:
    """Human label for a preset draft_mode, falling back to the raw mode."""
    p = get_by_mode(mode)
    return p.label if p else (mode or "")
